"""Write: store locations, hours, menus, items, and nutrition in Postgres.

Single writer per table: this module is the only code that writes the tables in
db/models.py marked "Writer: ingestion". The API only reads them.
Callers own the transaction: nothing here commits.
"""

from datetime import date, datetime, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from db.models import HoursDay, Location, Menu, MenuItem, Nutrition
from ingestion.normalize import (
    UNIT_TO_DINING_SLUG,
    item_signature,
    label_item,
    normalize_label,
    nutrition_key,
)
from ingestion.parse import HoursEntry, ItemRow, Label, MenuRef, UnitRef


def now() -> datetime:
    return datetime.now(timezone.utc)


def _upsert(db: Session, model, key_cols: list[str], values: dict):
    stmt = insert(model).values(**values)
    db.execute(stmt.on_conflict_do_update(
        index_elements=key_cols,
        set_={k: stmt.excluded[k] for k in values if k not in key_cols},
    ))


def upsert_location(db: Session, unit: UnitRef, description: str | None = None):
    values = {"id": unit.oid, "name": unit.name, "dining_slug": UNIT_TO_DINING_SLUG.get(unit.oid),
              "updated_at": now()}
    if description is not None:
        values["description"] = description
    _upsert(db, Location, ["id"], values)


def upsert_hours(db: Session, location_id: int, day: date, entry: HoursEntry | None):
    """entry None = we don't know (no hours page, fetch failed, or wrong date shown)."""
    if entry is None:
        status, windows, raw = "unknown", [], None
    else:
        status = "open" if entry.windows else ("closed" if entry.closed else "unknown")
        windows, raw = [list(w) for w in entry.windows], entry.raw_text
    _upsert(db, HoursDay, ["location_id", "date"], {
        "location_id": location_id, "date": day, "status": status,
        "windows": windows, "raw_text": raw, "fetched_at": now(),
    })


def upsert_menu_refs(db: Session, location_id: int, refs: list[MenuRef]):
    """Record listed menus; fetched_at stays NULL until their items are scraped."""
    for ref in refs:
        _upsert(db, Menu, ["id"], {"id": ref.oid, "location_id": location_id, "date": ref.date, "meal": ref.meal})


def delete_unlisted_menus(db: Session, location_id: int, refs: list[MenuRef]) -> int:
    """Delete this location's menus dated within the listed range that the site no longer lists.

    Only the listed date range is touched, so past menus are kept, and an empty list
    deletes nothing (we can't tell "removed" from "page didn't load").
    """
    if not refs:
        return 0
    result = db.execute(delete(Menu).where(
        Menu.location_id == location_id,
        Menu.date.between(min(r.date for r in refs), max(r.date for r in refs)),
        Menu.id.not_in([r.oid for r in refs]),
    ))
    return result.rowcount


def upsert_nutrition(db: Session, location_id: int, detail_oid: int, row: ItemRow, label: Label) -> list[str]:
    """Store a verified label under the item's cache key; returns its "Contains:" list."""
    data = normalize_label(label)
    _upsert(db, Nutrition, ["key"], {
        "key": nutrition_key(location_id, row.name, row.serving_size),
        "location_id": location_id,
        "source_detail_oid": detail_oid,
        "fetched_at": now(),
        **data,
    })
    return data["contains"]


def replace_menu_items(db: Session, menu_id: int, location_id: int, rows: list[ItemRow],
                       contains_by_key: dict[str, list[str]]) -> str:
    """Replace a menu's items. Returns 'new', 'changed', or 'same' versus the last scrape.

    contains_by_key maps nutrition keys to the "Contains:" list of a stored label;
    items whose key is absent get no nutrition link and only their icon allergens.
    """
    menu = db.execute(select(Menu.fetched_at).where(Menu.id == menu_id)).first()
    if menu is None:
        raise ValueError(f"menu {menu_id} is not recorded; call upsert_menu_refs first")
    before = None
    if menu.fetched_at is not None:
        before = item_signature(db.execute(
            select(MenuItem.name, MenuItem.course, MenuItem.serving_size, MenuItem.traits_raw)
            .where(MenuItem.menu_id == menu_id)
        ))

    db.execute(delete(MenuItem).where(MenuItem.menu_id == menu_id))
    values = []
    for r in rows:
        key = nutrition_key(location_id, r.name, r.serving_size)
        contains = contains_by_key.get(key)
        values.append({
            "menu_id": menu_id,
            "detail_oid": r.detail_oid,
            "name": r.name,
            "course": r.course,
            "serving_size": r.serving_size,
            "traits_raw": r.traits,
            "nutrition_key": key if contains is not None else None,
            **label_item(r, contains),
        })
    if values:
        db.execute(insert(MenuItem), values)
    db.execute(update(Menu).where(Menu.id == menu_id).values(fetched_at=now()))

    if before is None:
        return "new"
    return "same" if before == item_signature(rows) else "changed"
