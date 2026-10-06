"""Shared fixtures.

Parser tests use real pages captured from NetNutrition and dining.ncsu.edu on
2026-09-28 (tests/fixtures/), so they run offline. The captures are trimmed to
the HTML the parser reads; when re-capturing after a site change, trim again
(no scripts, API keys, analytics, or staff contact details in the repo).

Database tests need TEST_DATABASE_URL (see proj_2/.env.example) and skip without it.
The test database is created if missing, rebuilt from the Alembic migrations once per
session (so the migrations are tested too), and emptied before each test.
"""

import os
from pathlib import Path

import psycopg
import pytest
from sqlalchemy import make_url, text

from db.migrate import upgrade
from db.models import Base
from db.session import make_engine, make_session_factory, sqlalchemy_url

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_html():
    return lambda name: (FIXTURES / name).read_text(encoding="utf-8")


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
