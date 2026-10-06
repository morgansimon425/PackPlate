"""Normalize + label: turn the site's wording into stable keys.

The allergen and diet keys defined here are what backend/app/services/filter_engine.py
filters on, so changes to them need both owners. Nothing here invents data: unknown
stays unknown (None), and names we don't recognize are kept and flagged, never dropped.
"""

import re

from ingestion.parse import ItemRow, Label

# Every trait NC State publishes (NetNutrition's trait filter list, [data-traitoid]).
ALLERGEN_TRAITS = {
    "Contains Dairy": "dairy",
    "Contains Gluten": "gluten",
    "Contains Nuts": "nuts",  # the source lumps peanuts and tree nuts together
    "Contains Pork": "pork",
    "Contains Seafood": "seafood",  # the source lumps fish and shellfish together
    "Contains Sesame": "sesame",
    "Eggs": "egg",
    "Soy": "soy",
}
DIET_TRAITS = {
    "Halal (U)": "halal",
    "Sustainable": "sustainable",
    "Vegan": "vegan",
    "Vegetarian": "vegetarian",
}
ALLERGEN_KEYS = sorted(set(ALLERGEN_TRAITS.values()))
DIET_KEYS = sorted(set(DIET_TRAITS.values()))

# NetNutrition unitOid -> dining.ncsu.edu/location/<slug>/ (hours live on the dining site).
# Hand-maintained by matching NetNutrition's unit names to the a.location-tile links on
# https://dining.ncsu.edu/locations/. None = no hours page found.
UNIT_TO_DINING_SLUG = {
    1: "fountain",
    2: "clark",
    3: "case",
    4: "university-towers-dh",
    5: "one-earth",
    6: "oval",
    7: "brickyard-pizza",
    8: "smoothie-u",
    9: "tuffys",
    10: "los-lobos",
    11: "jasons-deli",
    12: None,  # Talley 1887 Bistro
    13: "starbucks",
    14: "hill-of-beans",
    15: "common-grounds",
    16: "creature-comforts",
    17: "pcj-koch",
    18: "pcj-talley",
    19: "elements",
    20: "social-fabric",
    21: "the-exchange",
    22: "la-farm",
    23: "wolves-den",
    24: "terrace",
}


def split_traits(traits: list[str]) -> tuple[set[str], set[str], list[str]]:
    """Icon titles -> (allergen keys, diet keys, unrecognized titles)."""
    allergens, diets, unknown = set(), set(), []
    for t in traits:
        if t in ALLERGEN_TRAITS:
            allergens.add(ALLERGEN_TRAITS[t])
        elif t in DIET_TRAITS:
            diets.add(DIET_TRAITS[t])
        else:
            unknown.append(t)
    return allergens, diets, unknown


def split_contains(contains: list[str]) -> tuple[set[str], list[str]]:
    """A label's "Contains:" names -> (allergen keys, unrecognized names)."""
    allergens, unknown = set(), []
    for c in contains:
        if c in ALLERGEN_TRAITS:
            allergens.add(ALLERGEN_TRAITS[c])
        else:
            unknown.append(c)
    return allergens, unknown


def label_item(row: ItemRow, contains: list[str] | None) -> dict:
    """Allergens, diets, and unrecognized names for one item.

    allergens = icon traits plus the label's "Contains:" list (None = no label).
    """
    allergens, diets, unknown = split_traits(row.traits)
    if contains is not None:
        extra, unknown_contains = split_contains(contains)
        allergens |= extra
        unknown += [c for c in unknown_contains if c not in unknown]
    return {"allergens": sorted(allergens), "diets": sorted(diets), "unrecognized_traits": unknown}


_AMOUNT = re.compile(r"^(<)?\s*(\d+(?:\.\d+)?)\s*(mg|g|%)?$", re.I)


def parse_amount(raw: str | None) -> float | None:
    """'4g' -> 4.0, '200mg' -> 200.0, '< 1g' -> 0.0, 'NA' / '' -> None. Never guesses."""
    if raw is None:
        return None
    m = _AMOUNT.match(raw.strip())
    if not m:
        return None
    if m.group(1):  # "< 1g": below the reporting threshold
        return 0.0
    return float(m.group(2))


# Columns the filter engine uses for goals; a missing one makes goal checks "data incomplete".
KEY_NUTRIENTS = {
    "calories": "Calories",
    "protein_g": "Protein",
    "fat_g": "Total Fat",
    "carbs_g": "Total Carbohydrate",
    "sodium_mg": "Sodium",
}


def normalize_label(label: Label) -> dict:
    values = {col: parse_amount(label.nutrients.get(name)) for col, name in KEY_NUTRIENTS.items()}
    missing = sorted(set(label.incomplete) | {
        name for col, name in KEY_NUTRIENTS.items() if values[col] is None
    })
    return {
        **values,
        "serving_size": label.serving_size,
        "nutrients_raw": label.nutrients,
        "ingredients": label.ingredients,
        "contains": label.contains,
        "missing_fields": missing,
    }


def _norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip().casefold()


def nutrition_key(location_id: int, name: str, serving_size: str | None) -> str:
    """Cache key for a label. Assumes the same name and serving at one location is the
    same recipe; scoped per location because halls can differ under one name."""
    return f"{location_id}|{_norm(name)}|{_norm(serving_size)}"


def same_dish(label_name: str | None, item_name: str) -> bool:
    """Safety guard: a label is only attached to the item whose name it carries."""
    return bool(label_name) and _norm(label_name) == _norm(item_name)


def item_signature(rows) -> list[tuple]:
    """Comparable summary of a menu's items, used to count menus that changed between runs.
    Accepts parse.ItemRow or db.models.MenuItem objects."""
    def traits(r):
        return r.traits if isinstance(r, ItemRow) else r.traits_raw

    return sorted((r.name, r.course or "", r.serving_size or "", tuple(traits(r) or [])) for r in rows)
