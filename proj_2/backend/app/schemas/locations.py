"""Response models for locations, hours, and menus.

Unknown stays unknown: null means "not published" or "not scraped", never
zero, closed, or safe.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class Period(BaseModel):
    opens_at: datetime
    closes_at: datetime


class HoursDay(BaseModel):
    date: date
    status: Literal["open", "closed", "unknown"]   # unknown = no hours published or scraped
    periods: list[Period]
    raw_text: str | None    # as shown on dining.ncsu.edu


class LocationSummary(BaseModel):
    id: int
    name: str
    description: str | None
    dining_url: str | None   # the location's dining.ncsu.edu page, if we know it
    is_open: bool | None     # null = today's hours are unknown
    closes_at: datetime | None
    opens_next_at: datetime | None   # next opening later today
    today: HoursDay


class MenuSummary(BaseModel):
    id: int
    date: date
    meal: str
    scraped: bool    # false = listed by NetNutrition, items not scraped yet


class LocationDetail(LocationSummary):
    hours: list[HoursDay]    # today and the next 6 days
    menus: list[MenuSummary]  # today onward


class Nutrition(BaseModel):
    serving_size: str | None
    calories: float | None
    protein_g: float | None
    fat_g: float | None
    carbs_g: float | None
    sodium_mg: float | None
    ingredients: str | None
    contains: list[str]       # the label's "Contains:" names, as printed
    missing_fields: list[str]  # nutrients the label doesn't give
    fetched_at: datetime


class MenuItem(BaseModel):
    id: int
    name: str
    course: str | None         # station, e.g. "Grill Stations"
    serving_size: str | None
    allergens: list[str]       # icon traits plus the label's "Contains:" list
    diets: list[str]
    unrecognized_traits: list[str]  # names we have no key for: treat as data incomplete
    nutrition: Nutrition | None     # null = no label, so allergens come from icons only


class Menu(MenuSummary):
    items: list[MenuItem]
