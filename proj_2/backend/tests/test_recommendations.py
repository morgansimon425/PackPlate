
"""Unit tests for PackPlate M5 meal recommendations."""

from types import SimpleNamespace

import pytest

from app.services.filter_engine import Profile
from app.services.recommendations import rank_meals, recommend_meals


def make_meal(
    item_id,
    name,
    protein=None,
    calories=None,
    sodium=None,
    missing_fields=None,
):
    """Create a sample meal without requiring a database."""
    nutrition = SimpleNamespace(
        protein_g=protein,
        calories=calories,
        sodium_mg=sodium,
        missing_fields=missing_fields or [],
        serving_size="1 serving",
        ingredients="Chicken, rice",
    )

    return SimpleNamespace(
        id=item_id,
        name=name,
        nutrition=nutrition,
    )


@pytest.fixture
def meals():
    return [
        make_meal(1, "Chicken Bowl", 38, 520, 640),
        make_meal(2, "Chicken Pasta", 24, 680, 890),
        make_meal(3, "Vegetable Bowl", 16, 410, 420),
    ]


def test_high_protein(meals):
    ranked = rank_meals(meals, "high_protein")
    assert [meal.id for meal in ranked] == [1, 2, 3]


def test_lower_calories(meals):
    ranked = rank_meals(meals, "lower_calories")
    assert [meal.id for meal in ranked] == [3, 1, 2]


def test_lower_sodium(meals):
    ranked = rank_meals(meals, "lower_sodium")
    assert [meal.id for meal in ranked] == [3, 1, 2]


def test_missing_nutrition():
    meal = make_meal(1, "Unknown Meal")
    ranked = rank_meals([meal], "high_protein")
    assert ranked == []


def test_flagged_nutrition():
    meal = make_meal(
        1, "Incomplete Meal",
        protein=30,
        missing_fields=["Protein"],
    )
    ranked = rank_meals([meal], "high_protein")
    assert ranked == []


def test_invalid_goal(meals):
    with pytest.raises(ValueError):
        rank_meals(meals, "invalid_goal")



def test_excludes_allergen_conflicts():
    """Meals containing an avoided allergen must not be recommended."""
    safe = make_meal(1, "Chicken Bowl", protein=38)
    unsafe = make_meal(2, "Cheese Pasta", protein=45)

    safe.allergens = []
    unsafe.allergens = ["dairy"]

    for meal in (safe, unsafe):
        meal.diets = []
        meal.unrecognized_traits = []
        meal.nutrition.ingredient_flags = {}

    profile = Profile(avoid=frozenset({"dairy"}))

    ranked = recommend_meals([unsafe, safe], "high_protein", profile)

    assert [meal.id for meal in ranked] == [1]


def test_excludes_incomplete_allergen_information():
    """Meals without enough allergen information cannot be marked compatible."""
    meal = make_meal(1, "Unknown Bowl", protein=30)

    meal.allergens = []
    meal.diets = []
    meal.unrecognized_traits = ["unknown trait"]
    meal.nutrition.ingredient_flags = {}

    profile = Profile(avoid=frozenset({"dairy"}))

    ranked = recommend_meals([meal], "high_protein", profile)

    assert ranked == []


def test_respects_nutrition_threshold():
    """Existing hard nutrition limits must apply before ranking."""
    high_calorie = make_meal(1, "Large Bowl", protein=45, calories=900)
    lower_calorie = make_meal(2, "Small Bowl", protein=30, calories=500)

    for meal in (high_calorie, lower_calorie):
        meal.allergens = []
        meal.diets = []
        meal.unrecognized_traits = []
        meal.nutrition.ingredient_flags = {}

    profile = Profile(max_calories=600)

    ranked = recommend_meals(
        [high_calorie, lower_calorie],
        "high_protein",
        profile,
    )

    assert [meal.id for meal in ranked] == [2]
