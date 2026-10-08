from ingestion import normalize
from ingestion.parse import ItemRow, Label


def test_split_traits_maps_site_wording_to_keys():
    allergens, diets, unknown = normalize.split_traits(
        ["Contains Dairy", "Eggs", "Halal (U)", "Vegetarian", "Mystery Icon"]
    )
    assert allergens == {"dairy", "egg"}
    assert diets == {"halal", "vegetarian"}
    assert unknown == ["Mystery Icon"]


def test_label_item_merges_icons_with_contains_and_keeps_unknown_names():
    row = ItemRow(1, "Shrimp Pasta", "Entree", "1 cup", ["Contains Gluten", "Vegetarian"])
    out = normalize.label_item(row, ["Contains Dairy", "Contains Gluten", "Contains Shellfish"])
    assert out["allergens"] == ["dairy", "gluten"]
    assert out["diets"] == ["vegetarian"]
    # A "Contains:" name we have no key for must stay visible, never silently dropped.
    assert out["unrecognized_traits"] == ["Contains Shellfish"]


def test_label_item_without_label_uses_icons_only():
    row = ItemRow(1, "Pita", None, None, ["Contains Gluten"])
    assert normalize.label_item(row, None)["allergens"] == ["gluten"]


def test_parse_amount_never_guesses():
    assert normalize.parse_amount("4g") == 4.0
    assert normalize.parse_amount("200mg") == 200.0
    assert normalize.parse_amount("< 1g") == 0.0
    assert normalize.parse_amount("NA") is None
    assert normalize.parse_amount("") is None
    assert normalize.parse_amount("about 4g") is None


def test_normalize_label_lists_missing_key_fields():
    label = Label(name="X", serving_size="1 cup", ingredients="rice", contains=[],
                  nutrients={"Calories": "200", "Protein": "NA", "Total Fat": "1g",
                             "Total Carbohydrate": "40g", "Sodium": "5mg"},
                  incomplete=["Protein"])
    data = normalize.normalize_label(label)
    assert data["calories"] == 200.0
    assert data["protein_g"] is None
    assert data["missing_fields"] == ["Protein"]


def test_normalize_label_flags_absent_key_nutrients():
    label = Label(name="X", serving_size=None, ingredients=None, contains=[],
                  nutrients={"Calories": "200"})
    assert normalize.normalize_label(label)["missing_fields"] == [
        "Protein", "Sodium", "Total Carbohydrate", "Total Fat"]


def test_nutrition_key_is_scoped_per_location():
    assert normalize.nutrition_key(1, " Cheese  Pizza", "1 Slice") == "1|cheese pizza|1 slice"
    assert normalize.nutrition_key(1, "Cheese Pizza", "1 slice") != normalize.nutrition_key(7, "Cheese Pizza", "1 slice")


def test_same_dish_tolerates_case_and_spacing_only():
    assert normalize.same_dish("Pita", "pita ")
    assert not normalize.same_dish("Pita", "Pita Chips")
    assert not normalize.same_dish(None, "Pita")


def test_every_unit_has_an_hours_mapping_entry():
    assert set(normalize.UNIT_TO_DINING_SLUG) == set(range(1, 25))
