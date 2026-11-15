
"""API tests for PackPlate M5 recommendations."""

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.deps import get_db

client = TestClient(app)


def fake_db():
    yield object()


def test_recommendations_empty_menus():
    """The API returns an empty list when no menus exist."""

    app.dependency_overrides[get_db] = fake_db

    try:
        with (
            patch(
                "app.api.recommendations.menus_repo.all_menus_on",
                return_value=[],
            ),
            patch(
                "app.api.recommendations.reviews_repo.approved",
                return_value={},
            ),
            patch(
                "app.api.recommendations.locations_repo.list_locations",
                return_value=[],
            ),
        ):
            response = client.post(
                "/recommendations",
                json={
                    "goal": "high_protein",
                    "date": "2026-11-16",
                },
            )

        assert response.status_code == 200
        assert response.json() == {"recommendations": []}

    finally:
        app.dependency_overrides.clear()



def test_recommendations_reject_invalid_goal():
    """An unsupported nutrition goal returns HTTP 422."""

    app.dependency_overrides[get_db] = fake_db

    try:
        response = client.post(
            "/recommendations",
            json={
                "goal": "invalid_goal",
                "date": "2026-11-16",
            },
        )

        assert response.status_code == 422

    finally:
        app.dependency_overrides.clear()



def test_recommendations_across_locations():
    """Rank meals from multiple campus dining locations."""

    from types import SimpleNamespace

    meal_a = SimpleNamespace(
        id=101,
        name="Chicken Bowl",
        course="Entree",
        serving_size="1 serving",
        allergens=[],
        diets=[],
        unrecognized_traits=[],
        nutrition=SimpleNamespace(
            key="chicken-bowl",
            serving_size="1 serving",
            calories=520,
            protein_g=38,
            fat_g=12,
            carbs_g=45,
            sodium_mg=640,
            missing_fields=[],
            ingredients="Chicken, rice",
            contains=[],
            fetched_at=datetime(2026, 11, 16, 10, 0),
            nutrients_raw={},
            ingredient_flags={},
        ),
    )

    meal_b = SimpleNamespace(
        id=102,
        name="Turkey Wrap",
        course="Entree",
        serving_size="1 serving",
        allergens=[],
        diets=[],
        unrecognized_traits=[],
        nutrition=SimpleNamespace(
            key="turkey-wrap",
            serving_size="1 serving",
            calories=430,
            protein_g=45,
            fat_g=10,
            carbs_g=35,
            sodium_mg=570,
            missing_fields=[],
            ingredients="Turkey, tortilla",
            contains=[],
            fetched_at=datetime(2026, 11, 16, 10, 0),
            nutrients_raw={},
            ingredient_flags={},
        ),
    )

    menus = [
        SimpleNamespace(
            location_id=1,
            meal="lunch",
            items=[meal_a],
        ),
        SimpleNamespace(
            location_id=2,
            meal="lunch",
            items=[meal_b],
        ),
    ]

    locations = [
        SimpleNamespace(id=1, name="Fountain Dining Hall"),
        SimpleNamespace(id=2, name="Clark Dining Hall"),
    ]

    app.dependency_overrides[get_db] = fake_db

    try:
        with (
            patch(
                "app.api.recommendations.menus_repo.all_menus_on",
                return_value=menus,
            ),
            patch(
                "app.api.recommendations.reviews_repo.approved",
                return_value={},
            ),
            patch(
                "app.api.recommendations.locations_repo.list_locations",
                return_value=locations,
            ),
        ):
            response = client.post(
                "/recommendations",
                json={
                    "goal": "high_protein",
                    "date": "2026-11-16",
                },
            )

        assert response.status_code == 200

        results = response.json()["recommendations"]

        assert len(results) == 2
        assert results[0]["name"] == "Turkey Wrap"
        assert results[0]["location_name"] == "Clark Dining Hall"
        assert results[1]["name"] == "Chicken Bowl"
        assert results[1]["location_name"] == "Fountain Dining Hall"

    finally:
        app.dependency_overrides.clear()
