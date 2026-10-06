"""Tables.

Single writer per table (proj_1b report, Figure 1):
    ingestion/  writes locations, hours_days, menus, menu_items, nutrition, ingest_runs
    backend/    reads those; writes only crowd_reports (added with the crowd feature)

Unknown stays unknown: a NULL nutrient or a missing label means "not published",
never zero or safe.
"""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Location(Base):
    """A NetNutrition dining unit. Writer: ingestion."""

    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)  # NetNutrition unitOid
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    dining_slug: Mapped[str | None] = mapped_column(String(100))  # dining.ncsu.edu/location/<slug>/
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    menus: Mapped[list["Menu"]] = relationship(back_populates="location")


class HoursDay(Base):
    """Hours for one location on one date, from dining.ncsu.edu. Writer: ingestion.

    status is 'open', 'closed' (the site said "Closed all day"), or 'unknown'.
    windows is a list of [open_minute, close_minute] after midnight; a close at or
    past 1440 means the location closes at or after midnight.
    """

    __tablename__ = "hours_days"

    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id", ondelete="CASCADE"), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    status: Mapped[str] = mapped_column(String(10))
    windows: Mapped[list] = mapped_column(JSONB, default=list)
    raw_text: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Menu(Base):
    """One meal on one day at one location. Writer: ingestion."""

    __tablename__ = "menus"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)  # NetNutrition menuOid
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    meal: Mapped[str] = mapped_column(String(50))  # Breakfast / Lunch / Dinner / Daily / ...
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # NULL = listed, items not scraped

    location: Mapped[Location] = relationship(back_populates="menus")
    items: Mapped[list["MenuItem"]] = relationship(
        back_populates="menu", cascade="all, delete-orphan", passive_deletes=True
    )


class Nutrition(Base):
    """One nutrition label. Writer: ingestion.

    key is "<location_id>|<name>|<serving size>" (lowercased): the same dish at the
    same location is fetched once and re-fetched when older than the cache limit.
    Scoped per location because two halls can serve different recipes under one name.
    """

    __tablename__ = "nutrition"

    key: Mapped[str] = mapped_column(String(500), primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id", ondelete="CASCADE"), index=True)
    source_detail_oid: Mapped[int] = mapped_column(Integer)
    serving_size: Mapped[str | None] = mapped_column(String(200))
    calories: Mapped[float | None] = mapped_column(Float)
    protein_g: Mapped[float | None] = mapped_column(Float)
    fat_g: Mapped[float | None] = mapped_column(Float)
    carbs_g: Mapped[float | None] = mapped_column(Float)
    sodium_mg: Mapped[float | None] = mapped_column(Float)
    nutrients_raw: Mapped[dict] = mapped_column(JSONB, default=dict)  # every row as printed, "Cholesterol": "NA"
    ingredients: Mapped[str | None] = mapped_column(Text)
    contains: Mapped[list] = mapped_column(JSONB, default=list)  # the label's "Contains:" names, as printed
    missing_fields: Mapped[list] = mapped_column(JSONB, default=list)  # flagged Incomplete or unparseable
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MenuItem(Base):
    """One dish on one menu. Writer: ingestion (replaced wholesale on each scrape).

    allergens = the item's icon traits plus its label's "Contains:" list.
    unrecognized_traits holds any icon or "Contains:" name we have no key for; the
    filter engine must treat a non-empty list as "data incomplete", not as safe.
    nutrition_key is NULL when no label was fetched or it failed verification.
    """

    __tablename__ = "menu_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    menu_id: Mapped[int] = mapped_column(ForeignKey("menus.id", ondelete="CASCADE"), index=True)
    detail_oid: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(300))
    course: Mapped[str | None] = mapped_column(String(200))  # station, e.g. "Deli"
    serving_size: Mapped[str | None] = mapped_column(String(200))
    traits_raw: Mapped[list] = mapped_column(JSONB, default=list)  # icon titles as published
    allergens: Mapped[list] = mapped_column(JSONB, default=list)  # normalized keys, see normalize.py
    diets: Mapped[list] = mapped_column(JSONB, default=list)  # halal / sustainable / vegan / vegetarian
    unrecognized_traits: Mapped[list] = mapped_column(JSONB, default=list)
    nutrition_key: Mapped[str | None] = mapped_column(ForeignKey("nutrition.key", ondelete="SET NULL"))

    menu: Mapped[Menu] = relationship(back_populates="items")
    nutrition: Mapped[Nutrition | None] = relationship()


class IngestRun(Base):
    """One run of the ingestion job: status, options, stats, errors. Writer: ingestion.

    The API can read the latest row to show how fresh the data is.
    """

    __tablename__ = "ingest_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20))  # running / ok / partial / failed
    options: Mapped[dict] = mapped_column(JSONB, default=dict)
    stats: Mapped[dict] = mapped_column(JSONB, default=dict)
    errors: Mapped[list] = mapped_column(JSONB, default=list)
