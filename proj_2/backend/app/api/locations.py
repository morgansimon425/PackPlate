"""Routes for dining locations: hours, menus, nutrition.

Every time-dependent route takes an optional `at` (ISO datetime, default now,
campus time if no offset) so tests and demos don't depend on the clock.
"""

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.deps import get_db
from app.repositories import locations as locations_repo
from app.repositories import menus as menus_repo
from app.schemas.locations import (
    HoursDay, LocationDetail, LocationSummary, Menu, MenuItem, MenuSummary, Period,
)
from app.services.hours import campus_time, open_state, periods
from app.services.menus import menu_sort_key

DINING_LOCATION_URL = "https://dining.ncsu.edu/location/{slug}/"
DAYS_SHOWN = 7

router = APIRouter(prefix="/locations", tags=["locations"])


def _hours_day(day: date, row) -> HoursDay:
    if row is None:
        return HoursDay(date=day, status="unknown", periods=[], raw_text=None)
    return HoursDay(
        date=day,
        status=row.status,
        periods=[Period(opens_at=o, closes_at=c) for o, c in periods(row.date, row.windows)],
        raw_text=row.raw_text,
    )


def _summary(location, hours: dict, at: datetime) -> dict:
    today = at.date()
    todays = hours.get((location.id, today))
    state = open_state(at, todays, hours.get((location.id, today - timedelta(days=1))))
    return {
        "id": location.id,
        "name": location.name,
        "description": location.description,
        "dining_url": DINING_LOCATION_URL.format(slug=location.dining_slug) if location.dining_slug else None,
        "is_open": state.is_open,
        "closes_at": state.closes_at,
        "opens_next_at": state.opens_next_at,
        "today": _hours_day(today, todays),
    }


def _menu_summary(menu) -> dict:
    return {"id": menu.id, "date": menu.date, "meal": menu.meal, "scraped": menu.fetched_at is not None}


def _get_location_or_404(db: Session, location_id: int):
    location = locations_repo.get_location(db, location_id)
    if location is None:
        raise HTTPException(status_code=404, detail=f"location {location_id} not found")
    return location


@router.get("", response_model=list[LocationSummary])
def list_locations(at: datetime | None = None, db: Session = Depends(get_db)):
    """Every location, with today's hours and whether it is open at `at`."""
    at = campus_time(at)
    hours = locations_repo.hours_between(db, at.date() - timedelta(days=1), at.date())
    return [_summary(loc, hours, at) for loc in locations_repo.list_locations(db)]


@router.get("/{location_id}", response_model=LocationDetail)
def get_location(location_id: int, at: datetime | None = None, db: Session = Depends(get_db)):
    """One location: open status, hours for the next 7 days, and the menus listed from today on."""
    location = _get_location_or_404(db, location_id)
    at = campus_time(at)
    days = [at.date() + timedelta(days=i) for i in range(DAYS_SHOWN)]
    hours = locations_repo.hours_between(db, days[0] - timedelta(days=1), days[-1], location_id)
    menus = sorted(menus_repo.menus_from(db, location_id, days[0]), key=menu_sort_key)
    return {
        **_summary(location, hours, at),
        "hours": [_hours_day(day, hours.get((location_id, day))) for day in days],
        "menus": [_menu_summary(m) for m in menus],
    }


@router.get("/{location_id}/menus", response_model=list[Menu])
def get_menus(location_id: int, on: date | None = Query(None, alias="date"),
              db: Session = Depends(get_db)):
    """Every menu at a location on `date` (default today), with all items at once."""
    _get_location_or_404(db, location_id)
    day = on or campus_time().date()
    menus = sorted(menus_repo.menus_on(db, location_id, day), key=menu_sort_key)
    return [
        {
            **_menu_summary(menu),
            "items": [MenuItem.model_validate(item, from_attributes=True)
                      for item in sorted(menu.items, key=lambda i: i.id)],
        }
        for menu in menus
    ]
