"""Shared FastAPI dependencies.

The engine is created on first use, not at import, so the app (and /health)
still starts when DATABASE_URL is unset or the database is down.
"""

from functools import lru_cache

from db.session import make_engine, make_session_factory


@lru_cache
def get_engine():
    return make_engine()


@lru_cache
def _session_factory():
    return make_session_factory(get_engine())


def get_db():
    """One session per request, closed when the request ends."""
    session = _session_factory()()
    try:
        yield session
    finally:
        session.close()
