"""Queries for locations and their hours. Read-only: ingestion writes these tables."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import HoursDay, Location


def list_locations(db: Session) -> list[Location]:
    return list(db.scalars(select(Location).order_by(Location.name)))


def get_location(db: Session, location_id: int) -> Location | None:
    return db.get(Location, location_id)


def hours_between(db: Session, start: date, end: date,
                  location_id: int | None = None) -> dict[tuple[int, date], HoursDay]:
    """Stored hours rows from start to end inclusive, keyed by (location_id, date)."""
    query = select(HoursDay).where(HoursDay.date.between(start, end))
    if location_id is not None:
        query = query.where(HoursDay.location_id == location_id)
    return {(row.location_id, row.date): row for row in db.scalars(query)}
