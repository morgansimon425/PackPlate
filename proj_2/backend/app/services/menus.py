"""Menu ordering. Every menu for a day is shown at once; meals are not filtered by time."""

# NetNutrition's meal names in the order a day runs. Anything else sorts after, by name.
MEAL_ORDER = ["breakfast", "brunch", "lunch", "dinner", "late night", "daily"]


def menu_sort_key(menu):
    meal = menu.meal.casefold()
    rank = MEAL_ORDER.index(meal) if meal in MEAL_ORDER else len(MEAL_ORDER)
    return (menu.date, rank, meal, menu.id)
