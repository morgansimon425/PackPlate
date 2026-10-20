"""Filter routes against the test database."""

from datetime import date

import pytest

TUE = date(2026, 10, 6)
NOON = "2026-10-06T12:00:00-04:00"
NUTS = {"name": "Sam", "avoid": ["nuts"]}
VEGAN = {"name": "Ana", "diets": ["vegan"]}


@pytest.fixture
def fountain(seed):
    """Fountain, open 7am-9pm Tuesday, with a labelled vegan pita, a nut bar, and an unlabelled salad."""
    seed.location(1, "Fountain Dining Hall", "fountain")
    seed.hours(1, TUE, windows=[(420, 1260)])
    seed.menu(11, 1, TUE, "Lunch")
    seed.menu(12, 1, TUE, "Breakfast")
    seed.nutrition("1|pita|1 each", protein_g=6, calories=170, sodium_mg=320)
    seed.nutrition(
        "1|nut bar|1 each",
        protein_g=8,
        calories=250,
        sodium_mg=90,
        contains=["Contains Nuts"],
    )
    seed.item(
        12, "Pita", nutrition_key="1|pita|1 each", allergens=["gluten"], diets=["vegan"]
    )
    seed.item(
        12,
        "Nut Bar",
        nutrition_key="1|nut bar|1 each",
        allergens=["nuts"],
        diets=["vegetarian"],
    )
    seed.item(11, "Garden Salad", diets=["vegan"])


def post_menus(client, profiles, day="2026-10-06", location_id=1):
    return client.post(
        f"/filters/locations/{location_id}/menus",
        params={"date": day},
        json={"profiles": profiles},
    )


def test_location_menus_checked_per_profile(client, fountain):
    response = post_menus(client, [NUTS, VEGAN])
    assert response.status_code == 200
    menus = response.json()
    assert [m["meal"] for m in menus] == ["Breakfast", "Lunch"]
    pita, bar = menus[0]["items"]
    [salad] = menus[1]["items"]

    assert (
        pita["name"] == "Pita" and pita["nutrition"]["protein_g"] == 6
    )  # the full item is there
    assert pita["results"] == [
        {"verdict": "fits", "reasons": []},
        {"verdict": "fits", "reasons": []},
    ]
    assert bar["results"] == [
        {"verdict": "conflicts", "reasons": ["contains nuts"]},
        {"verdict": "incomplete", "reasons": ["not labeled vegan"]},
    ]
    assert salad["results"][0] == {
        "verdict": "incomplete",
        "reasons": ["no nutrition label: allergens come from icons only"],
    }
    assert salad["results"][1]["verdict"] == "fits"


def test_location_menus_404_and_empty_day(client, fountain):
    assert post_menus(client, [NUTS], location_id=99).status_code == 404
    assert post_menus(client, [NUTS], day="2026-10-09").json() == []


@pytest.mark.parametrize(
    "body",
    [
        {"profiles": []},  # nobody
        {"profiles": [{"avoid": ["peanuts"]}]},  # not a key we know: never ignore it
        {"profiles": [{"allergens": ["nuts"]}]},  # misnamed field: never ignore it
        {"profiles": [{"diets": ["kosher"]}]},
        {"profiles": [{"min_protein_g": -1}]},
        {"profiles": [{}] * 11},  # too many
        {"profiles": [{}], "extra": 1},
    ],
)
def test_bad_profiles_are_422(client, fountain, body):
    assert client.post("/filters/group", json=body).status_code == 422
    assert client.post("/filters/locations/1/menus", json=body).status_code == 422


def test_group_ranks_where_everyone_fits_first(client, seed, fountain):
    seed.location(2, "Case Dining Hall", "case")
    seed.hours(2, TUE, windows=[(420, 600)])  # closed by noon
    seed.menu(21, 2, TUE, "Lunch")
    seed.nutrition("2|tofu|1 each", location_id=2, protein_g=20)
    seed.item(21, "Tofu", nutrition_key="2|tofu|1 each", diets=["vegan"])
    seed.location(3, "Atrium", None)  # no menu today, hours unknown
    seed.menu(31, 3, date(2026, 10, 7), "Lunch")
    seed.item(31, "Pizza")
    seed.menu(13, 1, date(2026, 10, 7), "Lunch")  # another day: not counted
    seed.item(13, "Tomorrow's Soup", diets=["vegan"])

    response = client.post(
        "/filters/group",
        params={"at": NOON},
        json={"profiles": [NUTS, {**VEGAN, "min_protein_g": 15}]},
    )
    assert response.status_code == 200
    body = response.json()
    # Only Case has something for both: Fountain's vegan options are under 15g protein.
    assert [loc["name"] for loc in body] == [
        "Case Dining Hall",
        "Fountain Dining Hall",
        "Atrium",
    ]

    case, fountain_, atrium = body
    assert case["everyone_fits"] is True and case["is_open"] is False
    assert case["profiles"] == [
        {"name": "Sam", "fits": 1, "incomplete": 0, "conflicts": 0},
        {"name": "Ana", "fits": 1, "incomplete": 0, "conflicts": 0},
    ]
    assert fountain_["everyone_fits"] is False
    assert (
        fountain_["is_open"] is True
        and fountain_["closes_at"] == "2026-10-06T21:00:00-04:00"
    )
    assert fountain_["items_checked"] == 3
    assert fountain_["profiles"][0] == {
        "name": "Sam",
        "fits": 1,
        "incomplete": 1,
        "conflicts": 1,
    }
    assert atrium == {
        "id": 3,
        "name": "Atrium",
        "is_open": None,
        "closes_at": None,
        "opens_next_at": None,
        "items_checked": 0,
        "everyone_fits": False,
        "profiles": [
            {"name": "Sam", "fits": 0, "incomplete": 0, "conflicts": 0},
            {"name": "Ana", "fits": 0, "incomplete": 0, "conflicts": 0},
        ],
    }


def test_group_puts_open_locations_before_closed_ones(client, seed, fountain):
    seed.location(2, "Case Dining Hall", "case")
    seed.hours(2, TUE, windows=[(420, 600)])
    seed.menu(21, 2, TUE, "Lunch")
    seed.nutrition("2|pita|1 each", location_id=2)
    seed.item(21, "Pita", nutrition_key="2|pita|1 each")
    body = client.post(
        "/filters/group", params={"at": NOON}, json={"profiles": [NUTS]}
    ).json()
    assert [(loc["name"], loc["everyone_fits"], loc["is_open"]) for loc in body] == [
        ("Fountain Dining Hall", True, True),
        ("Case Dining Hall", True, False),
    ]
