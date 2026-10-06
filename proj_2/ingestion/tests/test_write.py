"""Write-stage tests against the Postgres test database (skipped without TEST_DATABASE_URL)."""

from datetime import date

from sqlalchemy import select

from db.models import HoursDay, Location, Menu, MenuItem, Nutrition
from ingestion import write
from ingestion.normalize import nutrition_key
from ingestion.parse import HoursEntry, ItemRow, Label, MenuRef, UnitRef

DAY = date(2026, 9, 28)
FOUNTAIN = UnitRef(1, "Fountain Dining Hall")
PITA = ItemRow(111, "Pita", "Deli", "Serving (2 pieces) (43g)", ["Vegetarian"])
CHEESE = ItemRow(222, "Cheddar Cheese", "Deli", "1 oz", ["Contains Dairy"])


def setup_menu(db, oid=10, day=DAY):
    write.upsert_location(db, FOUNTAIN)
    write.upsert_menu_refs(db, 1, [MenuRef(oid, day, "Lunch")])


def test_location_upsert_updates_and_keeps_description(db):
    write.upsert_location(db, FOUNTAIN, "All you care to eat")
    write.upsert_location(db, UnitRef(1, "Fountain"))
    loc = db.get(Location, 1, populate_existing=True)
    assert (loc.name, loc.description, loc.dining_slug) == ("Fountain", "All you care to eat", "fountain")
    assert loc.updated_at.tzinfo is not None


def test_hours_statuses(db):
    write.upsert_location(db, FOUNTAIN)
    write.upsert_hours(db, 1, DAY, HoursEntry("Monday, Sep. 28", "7:00am - 10:00am", [(420, 600)], False))
    write.upsert_hours(db, 1, date(2026, 9, 29), HoursEntry("Tuesday, Sep. 29", "Closed all day", [], True))
    write.upsert_hours(db, 1, date(2026, 9, 30), None)
    rows = {h.date: h for h in db.scalars(select(HoursDay))}
    assert rows[DAY].status == "open" and rows[DAY].windows == [[420, 600]]
    assert rows[date(2026, 9, 29)].status == "closed"
    assert rows[date(2026, 9, 30)].status == "unknown" and rows[date(2026, 9, 30)].raw_text is None


def test_items_merge_icon_traits_with_label_contains(db, fixture_html):
    from ingestion.parse import parse_label

    setup_menu(db)
    contains = write.upsert_nutrition(db, 1, PITA.detail_oid, PITA, parse_label(fixture_html("nn_label_pita.html")))
    key = nutrition_key(1, PITA.name, PITA.serving_size)
    assert write.replace_menu_items(db, 10, 1, [PITA, CHEESE], {key: contains}) == "new"
    db.commit()

    items = {i.name: i for i in db.scalars(select(MenuItem))}
    assert items["Pita"].allergens == ["gluten"]  # icon said only Vegetarian; label added gluten
    assert items["Pita"].diets == ["vegetarian"]
    assert items["Pita"].nutrition_key == key
    assert items["Cheddar Cheese"].allergens == ["dairy"]
    assert items["Cheddar Cheese"].nutrition_key is None  # no label: the filter must say incomplete

    nut = db.get(Nutrition, key)
    assert nut.protein_g == 4.0 and nut.location_id == 1
    assert nut.missing_fields == ["Cholesterol", "Potassium"]
    assert db.get(Menu, 10).fetched_at is not None


def test_replace_reports_changed_and_same(db):
    setup_menu(db)
    write.replace_menu_items(db, 10, 1, [PITA], {})
    assert write.replace_menu_items(db, 10, 1, [PITA], {}) == "same"
    assert write.replace_menu_items(db, 10, 1, [PITA, CHEESE], {}) == "changed"
    db.commit()
    assert len(db.scalars(select(MenuItem)).all()) == 2


def test_unlisted_menus_in_listed_range_are_deleted(db):
    write.upsert_location(db, FOUNTAIN)
    old = MenuRef(1, date(2026, 9, 20), "Lunch")  # before the listed range: kept
    gone = MenuRef(2, DAY, "Brunch")  # in range, no longer listed: deleted
    keep = MenuRef(3, DAY, "Lunch")
    write.upsert_menu_refs(db, 1, [old, gone, keep])
    write.replace_menu_items(db, 2, 1, [PITA], {})
    assert write.delete_unlisted_menus(db, 1, [keep, MenuRef(4, date(2026, 10, 4), "Lunch")]) == 1
    assert write.delete_unlisted_menus(db, 1, []) == 0
    db.commit()
    assert sorted(m.id for m in db.scalars(select(Menu))) == [1, 3]
    assert db.scalars(select(MenuItem)).all() == []  # the deleted menu's items went with it
