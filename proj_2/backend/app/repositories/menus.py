"""Queries for menus, their items, and nutrition labels. Read-only."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from db.models import Menu, MenuItem


def menus_from(db: Session, location_id: int, start: date) -> list[Menu]:
    """A location's menus dated `start` or later, without their items."""
    return list(db.scalars(
        select(Menu).where(Menu.location_id == location_id, Menu.date >= start)
    ))


def menus_on(db: Session, location_id: int, day: date) -> list[Menu]:
    """A location's menus on `day`, with items and their nutrition labels loaded."""
    return list(db.scalars(
        select(Menu)
        .where(Menu.location_id == location_id, Menu.date == day)
        .options(selectinload(Menu.items).selectinload(MenuItem.nutrition))
    ))
