
"""API routes for PackPlate M5 meal recommendations."""

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.deps import get_db
from app.repositories import menus as menus_repo
from app.repositories import locations as locations_repo
from app.repositories import label_reviews as reviews_repo
from app.schemas.locations import MenuItem
from app.schemas.recommendations import (
    RecommendationRequest,
    RecommendationResponse,
)
from app.services.filter_engine import Profile as DietProfile
from app.services.label_reviews import reviewed_items
from app.services.recommendations import recommend_meals
from app.services.hours import campus_time

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.post("", response_model=RecommendationResponse)
def get_recommendations(
    request: RecommendationRequest,
    db: Session = Depends(get_db),
):
    """Recommend meals across campus based on a nutrition goal."""

    day = request.date or campus_time().date()

    # Convert the API profile into the filter engine's profile.
    if request.profile is not None:
        p = request.profile
        profile = DietProfile(
            avoid=frozenset(p.avoid),
            diets=frozenset(p.diets),
            min_protein_g=p.min_protein_g,
            max_calories=p.max_calories,
            max_sodium_mg=p.max_sodium_mg,
        )
    else:
        profile = DietProfile()

    # Retrieve menus and approved label reviews.
    menus = menus_repo.all_menus_on(db, day)
    approved = reviews_repo.approved(db)

    # Map location IDs to names.
    locations = {
        loc.id: loc.name
        for loc in locations_repo.list_locations(db)
    }

    # Collect meals and preserve their location/meal information.
    items = []
    metadata = {}

    for menu in menus:
        if request.meal and menu.meal.casefold() != request.meal.casefold():
            continue

        if menu.location_id not in locations:
            continue

        for item in reviewed_items(menu, approved):
            items.append(item)
            metadata[item.id] = {
                "location_id": menu.location_id,
                "location_name": locations[menu.location_id],
                "meal": menu.meal,
            }

    # Apply dietary checks and rank meals.
    ranked = recommend_meals(items, request.goal, profile)

    field = {
        "high_protein": ("protein_g", "g of protein"),
        "lower_calories": ("calories", "calories"),
        "lower_sodium": ("sodium_mg", "mg of sodium"),
    }[request.goal]

    nutrient_field, unit = field


    # Group identical dishes at the same location.
    # Preserve all meal periods while returning each dish once.
    unique_items = []
    seen = {}

    for item in ranked:
        info = metadata[item.id]

        key = (
            info["location_id"],
            item.name.strip().casefold(),
            (item.serving_size or "").strip().casefold(),
        )

        if key in seen:
            existing = seen[key]
            meal_period = info["meal"]

            if meal_period not in existing["meal_periods"]:
                existing["meal_periods"].append(meal_period)

            continue

        entry = {
            "item": item,
            "info": info,
            "meal_periods": [info["meal"]],
        }

        seen[key] = entry
        unique_items.append(entry)

    results = []

    for rank, entry in enumerate(unique_items[:20], start=1):
        item = entry["item"]
        info = entry["info"]

        nutrition = MenuItem.model_validate(
            item, from_attributes=True
        ).nutrition

        value = getattr(nutrition, nutrient_field)

        results.append({
            "rank": rank,
            "item_id": item.id,
            "name": item.name,
            "location_id": info["location_id"],
            "location_name": info["location_name"],
            "meal": info["meal"],
            "meal_periods": entry["meal_periods"],
            "nutrition": nutrition,
            "reason": f"Provides {value:g} {unit} per listed serving.",
        })

    return {"recommendations": results}
