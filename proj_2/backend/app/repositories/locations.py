"""Queries for locations and their hours. Read-only: ingestion writes these tables."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import HoursDay, Location, Menu, MenuItem


def list_locations(db: Session) -> list[Location]:
    """Locations that have ever had a menu with items, sorted by name.

    NetNutrition lists some cafés that never publish menus (or only long-stale
    ones). They're left out of every page. Their hours are still scraped, and a
    location appears as soon as one of its menus has items.
    """
    has_items = (
        select(Menu.location_id)
        .join(MenuItem, MenuItem.menu_id == Menu.id)
        .where(Menu.location_id == Location.id)
        .exists()
    )
    return list(db.scalars(select(Location).where(has_items).order_by(Location.name)))


def get_location(db: Session, location_id: int) -> Location | None:
    """One location by its NetNutrition unit id, or None if there's no such location."""
    return db.get(Location, location_id)


def hours_between(
    db: Session, start: date, end: date, location_id: int | None = None
) -> dict[tuple[int, date], HoursDay]:
    """Stored hours rows from start to end inclusive, keyed by (location_id, date)."""
    query = select(HoursDay).where(HoursDay.date.between(start, end))
    if location_id is not None:
        query = query.where(HoursDay.location_id == location_id)
    return {(row.location_id, row.date): row for row in db.scalars(query)}
