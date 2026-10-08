"""Shared fixtures.

Database tests need TEST_DATABASE_URL (see proj_2/.env.example) and skip without
it. As in ingestion/tests/conftest.py, the test database is created if missing,
rebuilt from the Alembic migrations once per session, and emptied before each
test. Tests insert rows directly, standing in for the ingestion job.
"""

import os
from datetime import date, datetime, timezone

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import make_url, text

from app.deps import get_db
from app.main import app
from db.migrate import upgrade
from db.models import Base, HoursDay, IngestRun, Location, Menu, MenuItem, Nutrition
from db.session import make_engine, make_session_factory, sqlalchemy_url

SCRAPED = datetime(2026, 10, 6, 8, 0, tzinfo=timezone.utc)


def _create_database_if_missing(url: str):
    target = make_url(sqlalchemy_url(url))
    admin = target.set(drivername="postgresql", database="postgres").render_as_string(hide_password=False)
    with psycopg.connect(admin, autocommit=True, connect_timeout=3) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target.database,)).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{target.database}"')


@pytest.fixture(scope="session")
def pg_engine():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    try:
        _create_database_if_missing(url)
    except psycopg.OperationalError as e:
        pytest.skip(f"test database unreachable: {e}")
    engine = make_engine(url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    with engine.begin() as conn:
        upgrade(conn)
    yield engine
    engine.dispose()


@pytest.fixture
def db(pg_engine):
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with pg_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    session = make_session_factory(pg_engine)()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def client(db):
    """The API, reading from the test database."""
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


class Seed:
    """Insert rows the way ingestion would, with sensible defaults."""

    def __init__(self, db):
        self.db = db

    def location(self, id=1, name="Fountain Dining Hall", slug="fountain", description=None):
        self.db.add(Location(id=id, name=name, dining_slug=slug, description=description, updated_at=SCRAPED))
        self.db.commit()

    def hours(self, location_id, day: date, status="open", windows=(), raw_text=None):
        self.db.add(HoursDay(location_id=location_id, date=day, status=status,
                             windows=[list(w) for w in windows], raw_text=raw_text, fetched_at=SCRAPED))
        self.db.commit()

    def menu(self, id, location_id, day: date, meal, scraped=True):
        self.db.add(Menu(id=id, location_id=location_id, date=day, meal=meal,
                         fetched_at=SCRAPED if scraped else None))
        self.db.commit()

    def nutrition(self, key, location_id=1, **values):
        self.db.add(Nutrition(key=key, location_id=location_id, source_detail_oid=1, fetched_at=SCRAPED,
                              nutrients_raw={}, contains=values.pop("contains", []),
                              missing_fields=values.pop("missing_fields", []), **values))
        self.db.commit()

    def item(self, menu_id, name, nutrition_key=None, allergens=(), diets=(), unrecognized=(), **values):
        self.db.add(MenuItem(menu_id=menu_id, detail_oid=1, name=name, traits_raw=[],
                             allergens=list(allergens), diets=list(diets),
                             unrecognized_traits=list(unrecognized), nutrition_key=nutrition_key, **values))
        self.db.commit()

    def run(self, status="ok", finished_at=SCRAPED):
        self.db.add(IngestRun(started_at=finished_at, finished_at=finished_at, status=status,
                              options={}, stats={}, errors=[]))
        self.db.commit()


@pytest.fixture
def seed(db):
    return Seed(db)
