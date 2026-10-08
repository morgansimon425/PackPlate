"""Locations and menus routes against the test database."""

from datetime import date

TUE, WED, MON = date(2026, 10, 6), date(2026, 10, 7), date(2026, 10, 5)
NOON = "2026-10-06T12:00:00-04:00"


def test_list_locations_with_open_status(client, seed):
    seed.location(1, "Fountain Dining Hall", "fountain")
    seed.location(2, "Case Dining Hall", "case")
    seed.location(12, "Talley - 1887 Bistro", None)
    seed.hours(1, TUE, windows=[(420, 1260)], raw_text="7:00am - 9:00pm")
    seed.hours(2, TUE, windows=[(420, 600), (660, 810)])

    response = client.get("/locations", params={"at": NOON})
    assert response.status_code == 200
    by_id = {loc["id"]: loc for loc in response.json()}
    assert [loc["name"] for loc in response.json()] == sorted(loc["name"] for loc in response.json())

    fountain = by_id[1]
    assert fountain["is_open"] is True
    assert fountain["closes_at"] == "2026-10-06T21:00:00-04:00"
    assert fountain["dining_url"] == "https://dining.ncsu.edu/location/fountain/"
    assert fountain["today"] == {
        "date": "2026-10-06", "status": "open", "raw_text": "7:00am - 9:00pm",
        "periods": [{"opens_at": "2026-10-06T07:00:00-04:00", "closes_at": "2026-10-06T21:00:00-04:00"}],
    }
    assert by_id[2]["is_open"] is True and by_id[2]["closes_at"] == "2026-10-06T13:30:00-04:00"

    # No hours stored and no hours page: unknown, not closed.
    bistro = by_id[12]
    assert bistro["is_open"] is None
    assert bistro["dining_url"] is None
    assert bistro["today"]["status"] == "unknown"


def test_list_uses_yesterdays_window_after_midnight(client, seed):
    seed.location(1)
    seed.hours(1, MON, windows=[(420, 1500)])
    seed.hours(1, TUE, status="closed", raw_text="Closed all day")
    [loc] = client.get("/locations", params={"at": "2026-10-06T00:30:00-04:00"}).json()
    assert loc["is_open"] is True
    assert loc["closes_at"] == "2026-10-06T01:00:00-04:00"


def test_location_detail_has_a_week_of_hours_and_upcoming_menus(client, seed):
    seed.location(1, description="All you care to eat.")
    seed.hours(1, TUE, windows=[(420, 1260)])
    seed.hours(1, WED, status="closed")
    seed.menu(10, 1, MON, "Lunch")                     # past: not listed
    seed.menu(11, 1, TUE, "Dinner")
    seed.menu(12, 1, TUE, "Breakfast")
    seed.menu(13, 1, TUE, "Daily", scraped=False)
    seed.menu(14, 1, WED, "Lunch")

    detail = client.get("/locations/1", params={"at": NOON}).json()
    assert detail["description"] == "All you care to eat."
    assert [h["date"] for h in detail["hours"]][:2] == ["2026-10-06", "2026-10-07"]
    assert len(detail["hours"]) == 7
    assert [h["status"] for h in detail["hours"]] == ["open", "closed"] + ["unknown"] * 5
    assert [(m["date"], m["meal"], m["scraped"]) for m in detail["menus"]] == [
        ("2026-10-06", "Breakfast", True),
        ("2026-10-06", "Dinner", True),
        ("2026-10-06", "Daily", False),
        ("2026-10-07", "Lunch", True),
    ]


def test_unknown_location_is_404(client, seed):
    assert client.get("/locations/99").status_code == 404
    assert client.get("/locations/99/menus").status_code == 404


def test_all_menus_for_a_day_with_items_and_nutrition(client, seed):
    seed.location(1)
    seed.menu(11, 1, TUE, "Lunch")
    seed.menu(12, 1, TUE, "Breakfast")
    seed.menu(14, 1, WED, "Lunch")
    seed.nutrition("1|pita|1 each", calories=170, protein_g=6, fat_g=1, carbs_g=34, sodium_mg=320,
                   serving_size="1 each", ingredients="flour, water", contains=["Contains Gluten"],
                   missing_fields=["Potassium"])
    seed.item(12, "Pita", nutrition_key="1|pita|1 each", allergens=["gluten"], diets=["vegan"],
              course="Bread", serving_size="1 each")
    seed.item(12, "Mystery Bar", unrecognized=["Contains Shellfish"])
    seed.item(11, "Grilled Chicken", allergens=[], course="Grill")

    menus = client.get("/locations/1/menus", params={"date": "2026-10-06"}).json()
    assert [m["meal"] for m in menus] == ["Breakfast", "Lunch"]
    breakfast = menus[0]
    assert [i["name"] for i in breakfast["items"]] == ["Pita", "Mystery Bar"]

    pita = breakfast["items"][0]
    assert pita["allergens"] == ["gluten"] and pita["diets"] == ["vegan"]
    assert pita["course"] == "Bread"
    assert pita["nutrition"]["protein_g"] == 6
    assert pita["nutrition"]["contains"] == ["Contains Gluten"]
    assert pita["nutrition"]["missing_fields"] == ["Potassium"]

    mystery = breakfast["items"][1]
    assert mystery["nutrition"] is None   # no label: allergens are icons only
    assert mystery["unrecognized_traits"] == ["Contains Shellfish"]


def test_day_without_menus_is_empty(client, seed):
    seed.location(1)
    assert client.get("/locations/1/menus", params={"date": "2026-10-09"}).json() == []


def test_bad_date_is_422(client, seed):
    seed.location(1)
    assert client.get("/locations/1/menus", params={"date": "tuesday"}).status_code == 422
