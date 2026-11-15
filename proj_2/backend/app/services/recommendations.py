
"""Rule-based meal recommendations for PackPlate M5."""

from typing import Literal

from app.services.filter_engine import is_placeholder

from app.services.filter_engine import (
    Profile, FITS, check, is_placeholder, nutrition_unavailable
)


NutritionGoal = Literal[
    "high_protein",
    "lower_calories",
    "lower_sodium",
]

GOAL_FIELDS = {
    "high_protein": "protein_g",
    "lower_calories": "calories",
    "lower_sodium": "sodium_mg",
}

NUTRIENT_NAMES = {
    "protein_g": "Protein",
    "calories": "Calories",
    "sodium_mg": "Sodium",
}


def rank_meals(items: list, goal: NutritionGoal) -> list:
    """Return meals ranked by the selected nutrition goal.

    Excludes meals with missing or unreliable nutrition data.
    """
    if goal not in GOAL_FIELDS:
        raise ValueError(f"Unsupported nutrition goal: {goal}")

    field = GOAL_FIELDS[goal]
    eligible = []

    for item in items:
        nutrition = item.nutrition

        if nutrition is None:
            continue

        if nutrition_unavailable(nutrition, item.name):
            continue

        # Exclude placeholder nutrition labels.
        if is_placeholder(nutrition, getattr(item, "name", "")):
            continue

        # Exclude meals with flagged or missing nutrient values.
        missing = getattr(nutrition, "missing_fields", None) or []

        if NUTRIENT_NAMES[field] in missing:
            continue

        value = getattr(nutrition, field, None)

        if value is None:
            continue

        eligible.append(item)

    # Higher protein is better; lower calories/sodium are better.
    descending = goal == "high_protein"

    return sorted(
        eligible,
        key=lambda item: (
            -getattr(item.nutrition, field)
            if descending
            else getattr(item.nutrition, field),
            item.name.casefold(),
            item.id,
        ),
    )


def recommend_meals(
    items: list,
    goal: NutritionGoal,
    profile: Profile,
) -> list:
    """Return compatible meals ranked by the user's nutrition goal."""

    compatible = []

    for item in items:
        result = check(item, profile)

        # Never recommend conflicting or unverified meals.
        if result.verdict != FITS:
            continue

        compatible.append(item)

    return rank_meals(compatible, goal)
