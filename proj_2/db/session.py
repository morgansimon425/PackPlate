"""Engine and sessions, configured from the DATABASE_URL environment variable."""

import os

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def sqlalchemy_url(url: str) -> str:
    """Use the psycopg 3 driver for plain postgresql:// URLs.

    .env.example uses postgresql://..., which psycopg.connect() accepts as-is but
    SQLAlchemy would map to psycopg2, which we don't install.
    """
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url.removeprefix(prefix)
    return url


def database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set (see proj_2/.env.example)")
    return sqlalchemy_url(url)


def make_engine(url: str | None = None) -> Engine:
    return create_engine(sqlalchemy_url(url) if url else database_url(), pool_pre_ping=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
