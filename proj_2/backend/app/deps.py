"""Shared FastAPI dependencies.

The engine is created on first use, not at import, so the app (and /health)
still starts when DATABASE_URL is unset or the database is down.

Accounts: a route that needs a signed-in user takes
`user: User = Depends(current_user)` (401 when signed out); one that works
either way takes `user: User | None = Depends(optional_user)`.
"""

from functools import lru_cache

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.repositories import users as users_repo
from app.services.auth import SESSION_COOKIE, token_hash
from app.services.hours import campus_time
from db.models import User
from db.session import make_engine, make_session_factory


@lru_cache
def get_engine():
    """The database engine, created on first use and then reused."""
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


def optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    """The signed-in account for this request, or None when signed out."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    return users_repo.user_for_session(db, token_hash(token), campus_time())


def _not_logged_in() -> HTTPException:
    return HTTPException(status_code=401, detail="you need to log in")


def _has_session_cookie(request: Request):
    # Runs before optional_user (FastAPI resolves dependencies in order), so a
    # logged-out request gets its 401 without opening a database session.
    if not request.cookies.get(SESSION_COOKIE):
        raise _not_logged_in()


def current_user(
    _: None = Depends(_has_session_cookie),
    user: User | None = Depends(optional_user),
) -> User:
    """The signed-in account. 401 when signed out or the session expired."""
    if user is None:
        raise _not_logged_in()
    return user
