"""Tables.

Single writer per table (proj_1b report, Figure 1):
    ingestion/  writes locations, hours_days, menus, menu_items, nutrition, ingest_runs,
                label_reviews
    backend/    reads those; writes crowd_reports, users, auth_sessions, and the
                chat tables (chat_models.py)

Unknown stays unknown: a NULL nutrient or a missing label means "not published",
never zero or safe.
"""

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    false,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for every table below. Its metadata lists them all, for Alembic."""

    pass


class Location(Base):
    """A NetNutrition dining unit. Writer: ingestion."""

    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=False
    )  # NetNutrition unitOid
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    dining_slug: Mapped[str | None] = mapped_column(
        String(100)
    )  # dining.ncsu.edu/location/<slug>/
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    menus: Mapped[list["Menu"]] = relationship(back_populates="location")


class HoursDay(Base):
    """Hours for one location on one date, from dining.ncsu.edu. Writer: ingestion.

    status is 'open', 'closed' (the site said "Closed all day"), or 'unknown'.
    windows is a list of [open_minute, close_minute] after midnight; a close at or
    past 1440 means the location closes at or after midnight.
    """

    __tablename__ = "hours_days"

    location_id: Mapped[int] = mapped_column(
        ForeignKey("locations.id", ondelete="CASCADE"), primary_key=True
    )
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    status: Mapped[str] = mapped_column(String(10))
    windows: Mapped[list] = mapped_column(JSONB, default=list)
    raw_text: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Menu(Base):
    """One meal on one day at one location. Writer: ingestion."""

    __tablename__ = "menus"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=False
    )  # NetNutrition menuOid
    location_id: Mapped[int] = mapped_column(
        ForeignKey("locations.id", ondelete="CASCADE"), index=True
    )
    date: Mapped[date] = mapped_column(Date, index=True)
    meal: Mapped[str] = mapped_column(
        String(50)
    )  # Breakfast / Lunch / Dinner / Daily / ...
    fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )  # NULL = listed, items not scraped

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
    location_id: Mapped[int] = mapped_column(
        ForeignKey("locations.id", ondelete="CASCADE"), index=True
    )
    source_detail_oid: Mapped[int] = mapped_column(Integer)
    serving_size: Mapped[str | None] = mapped_column(String(200))
    calories: Mapped[float | None] = mapped_column(Float)
    protein_g: Mapped[float | None] = mapped_column(Float)
    fat_g: Mapped[float | None] = mapped_column(Float)
    carbs_g: Mapped[float | None] = mapped_column(Float)
    sodium_mg: Mapped[float | None] = mapped_column(Float)
    nutrients_raw: Mapped[dict] = mapped_column(
        JSONB, default=dict
    )  # every row as printed, "Cholesterol": "NA"
    ingredients: Mapped[str | None] = mapped_column(Text)
    contains: Mapped[list] = mapped_column(
        JSONB, default=list
    )  # the label's "Contains:" names, as printed
    missing_fields: Mapped[list] = mapped_column(
        JSONB, default=list
    )  # flagged Incomplete or unparseable
    ingredient_flags: Mapped[dict] = mapped_column(
        JSONB, default=dict
    )  # possible allergens the ingredients mention, {"dairy": ["whey"]}; never confirmed
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
    menu_id: Mapped[int] = mapped_column(
        ForeignKey("menus.id", ondelete="CASCADE"), index=True
    )
    detail_oid: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(300))
    course: Mapped[str | None] = mapped_column(String(200))  # station, e.g. "Deli"
    serving_size: Mapped[str | None] = mapped_column(String(200))
    traits_raw: Mapped[list] = mapped_column(
        JSONB, default=list
    )  # icon titles as published
    allergens: Mapped[list] = mapped_column(
        JSONB, default=list
    )  # normalized keys, see normalize.py
    diets: Mapped[list] = mapped_column(
        JSONB, default=list
    )  # halal / sustainable / vegan / vegetarian
    unrecognized_traits: Mapped[list] = mapped_column(JSONB, default=list)
    nutrition_key: Mapped[str | None] = mapped_column(
        ForeignKey("nutrition.key", ondelete="SET NULL")
    )

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


CROWD_LEVELS = ("not_busy", "moderate", "crowded")


class CrowdReport(Base):
    """One student's report of how busy a location is. Writer: backend (the API).

    Append-only: the API never updates a row, and the crowd level is computed from
    recent rows on read, so two reports at once can't race. Nothing about the
    reporter is stored.
    """

    __tablename__ = "crowd_reports"
    __table_args__ = (
        CheckConstraint(
            "level IN ('not_busy', 'moderate', 'crowded')",
            name="ck_crowd_reports_level",
        ),
        Index("ix_crowd_reports_location_id_created_at", "location_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    location_id: Mapped[int] = mapped_column(
        ForeignKey("locations.id", ondelete="CASCADE")
    )
    level: Mapped[str] = mapped_column(String(20))  # one of CROWD_LEVELS
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LabelReview(Base):
    """A diet tag that NC State's own ingredients contradict, for a person to decide.
    Writer: ingestion (the scraper adds pending rows; the review command decides).

    A dish is a location plus its name (NetNutrition gives it a new item id on
    every menu). ingredients_hash pins the decision to the ingredient text it was
    made on: if NC State changes the ingredients, a new review is needed.
    Approved rows tell the API to remove `tags` from the dish; NC State's own
    data in menu_items is never changed.
    """

    __tablename__ = "label_reviews"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_label_reviews_status",
        ),
        Index(
            "uq_label_reviews_dish_ingredients",
            "location_id",
            "dish",
            "ingredients_hash",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    location_id: Mapped[int] = mapped_column(
        ForeignKey("locations.id", ondelete="CASCADE")
    )
    dish: Mapped[str] = mapped_column(String(300))  # item name, lowercased
    item_name: Mapped[str] = mapped_column(String(300))  # as NC State shows it
    tags: Mapped[list] = mapped_column(JSONB)  # contradicted diet tags, ["vegan"]
    words: Mapped[list] = mapped_column(JSONB)  # ingredient words, ["chicken"]
    ingredients_hash: Mapped[str] = mapped_column(String(64))  # sha256 of the text
    status: Mapped[str] = mapped_column(String(10), default="pending")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[str | None] = mapped_column(String(100))
    reason: Mapped[str | None] = mapped_column(Text)


class User(Base):
    """A PackPlate account. Writer: backend (the API).

    Only a username, a password hash, and the Open to Chat setting are stored:
    no email, no real name, and no dietary profile (that stays in the browser).
    open_to_chat (off by default) is whether the user appears in chat's list of
    people to invite. username is stored
    lowercased, so "Wolf" and "wolf" are the same account. Other features
    (chat, preferences) should reference users.id with ON DELETE CASCADE, so
    deleting an account deletes everything tied to it.
    """

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("username = lower(username)", name="ck_users_username_lower"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(30), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))  # see services/passwords
    open_to_chat: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    sessions: Mapped[list["AuthSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


class AuthSession(Base):
    """One signed-in browser. Writer: backend (the API).

    The browser holds a random token in an HttpOnly cookie; only its SHA-256 is
    stored here, so a leaked table can't be used to sign in. Logging out deletes
    the row; a row past expires_at is treated as missing.
    """

    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="sessions")


# M4's chat tables live in their own file; importing it here puts them on
# Base.metadata wherever the models are used (Alembic, the tests). At the bottom
# because chat_models imports Base from this module.
from db import chat_models  # noqa: E402, F401
