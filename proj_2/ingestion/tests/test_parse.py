"""Parser tests against real pages captured from NetNutrition and dining.ncsu.edu on 2026-09-28."""

from datetime import date

import pytest

from ingestion import parse


def test_units_lists_all_24_locations(fixture_html):
    units = parse.parse_units(fixture_html("nn_home.html"))
    assert len(units) == 24
    assert units[0] == parse.UnitRef(1, "Fountain Dining Hall")
    assert units[-1] == parse.UnitRef(24, "The Terrace")


def test_menu_list_has_dates_and_meals(fixture_html):
    ml = parse.parse_menu_list(fixture_html("nn_unit_menu_list.html"))
    assert ml.description.startswith("Our largest all-you-care-to-eat")
    assert len(ml.menus) == 28  # 7 days x Breakfast/Lunch/Dinner/Daily
    assert ml.menus[1] == parse.MenuRef(10063261, date(2026, 9, 28), "Lunch")
    assert {m.meal for m in ml.menus} == {"Breakfast", "Lunch", "Dinner", "Daily"}
    assert not ml.no_menus_notice


def test_menu_list_recognizes_the_no_menus_notice():
    ml = parse.parse_menu_list("<div>There are no menus available for this location.</div>")
    assert ml.menus == [] and ml.no_menus_notice


def test_menu_list_rejects_an_unexpected_date_header():
    html = "<section class='card'><header>Sometime soon</header></section>"
    with pytest.raises(ValueError, match="unexpected menu date header"):
        parse.parse_menu_list(html)


def test_menu_items_keep_course_serving_and_traits(fixture_html):
    items = parse.parse_menu_items(fixture_html("nn_menu_items.html"))
    assert len(items) == 89  # primary + alternate striped rows
    bananas = items[0]
    assert (bananas.name, bananas.course, bananas.serving_size) == ("Bananas", "Extras", "SERVING")
    assert bananas.traits == ["Halal (U)", "Vegan", "Vegetarian"]
    cheddar = next(i for i in items if i.name == "Cheddar Cheese")
    assert cheddar.course == "Deli" and "Contains Dairy" in cheddar.traits
    assert all(i.name and i.detail_oid for i in items)


def test_label_parses_nutrients_ingredients_and_contains(fixture_html):
    label = parse.parse_label(fixture_html("nn_label_pita.html"))
    assert label.name == "Pita"
    assert label.serving_size == "Serving (2 pieces) (43g)"
    assert label.nutrients["Calories"] == "110"
    assert label.nutrients["Protein"] == "4g"
    assert label.nutrients["Dietary Fiber"] == "< 1g"
    assert label.contains == ["Contains Gluten"]
    assert label.ingredients.startswith("Pita Bread (Wheat Flour")


def test_label_reports_site_flagged_missing_values(fixture_html):
    label = parse.parse_label(fixture_html("nn_label_pita.html"))
    assert label.nutrients["Cholesterol"] == "NA"
    assert label.incomplete == ["Cholesterol", "Potassium"]


def test_empty_label_has_no_name():
    # What an expired session or error page parses to: the guard in run.py rejects it.
    assert parse.parse_label("").name is None


def test_location_hours_split_meal_periods(fixture_html):
    hours = parse.parse_location_hours(fixture_html("dining_location_case.html"))
    today = hours["today"]
    assert today.date_label == "Monday, Sep. 28"
    assert today.windows == [(7 * 60, 10 * 60), (11 * 60, 13 * 60 + 30)]
    assert not today.closed


def test_location_hours_empty_when_page_has_no_hours_boxes():
    assert parse.parse_location_hours("<html><body>Checking your browser...</body></html>") == {}


def test_time_ranges_handle_midnight_and_closed():
    assert parse.parse_time_ranges("8:00am - 12:00am") == [(480, 1440)]
    assert parse.parse_time_ranges("11am - 2pm") == [(660, 840)]
    assert parse.parse_time_ranges("Closed all day") == []


def test_hours_label_must_match_weekday_and_day():
    assert parse.hours_label_matches("Monday, Sep. 28", date(2026, 9, 28))
    assert not parse.hours_label_matches("Tuesday, Sep. 29", date(2026, 9, 28))
    assert not parse.hours_label_matches("Monday, Sep. 8", date(2026, 9, 28))
    assert not parse.hours_label_matches("", date(2026, 9, 28))
