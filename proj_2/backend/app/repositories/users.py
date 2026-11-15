"""Queries for accounts and sign-in sessions."""

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.models import AuthSession, User


def get_by_username(db: Session, username: str) -> User | None:
    """The account with this (normalized) username, if any."""
    return db.scalar(select(User).where(User.username == username))


def get_by_id(db: Session, user_id: int) -> User | None:
    """The account with this id, if any."""
    return db.get(User, user_id)


def create_user(db: Session, username: str, password_hash: str) -> User | None:
    """Store a new account. None if the username is already taken."""
    user = User(username=username, password_hash=password_hash)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:  # two sign-ups for one name at once: the database decides
        db.rollback()
        return None
    return user


def set_password_hash(db: Session, user: User, password_hash: str):
    """Replace the account's password hash (e.g. after raising the cost)."""
    user.password_hash = password_hash
    db.commit()


def set_open_to_chat(db: Session, user: User, value: bool):
    """Turn the account's Open to Chat setting on or off."""
    user.open_to_chat = value
    db.commit()


def delete_user(db: Session, user: User):
    """Delete the account; its sessions (and anything else keyed on it) cascade."""
    db.delete(user)
    db.commit()


def add_session(db: Session, user_id: int, token_hash: str, expires_at: datetime):
    """Record a signed-in browser."""
    db.add(AuthSession(token_hash=token_hash, user_id=user_id, expires_at=expires_at))
    db.commit()


def user_for_session(db: Session, token_hash: str, now: datetime) -> User | None:
    """The account a session token belongs to, or None if unknown or expired."""
    return db.scalar(
        select(User)
        .join(AuthSession, AuthSession.user_id == User.id)
        .where(AuthSession.token_hash == token_hash, AuthSession.expires_at > now)
    )


def delete_session(db: Session, token_hash: str):
    """Sign one browser out. Does nothing if the session is already gone."""
    db.execute(delete(AuthSession).where(AuthSession.token_hash == token_hash))
    db.commit()


def delete_expired_sessions(db: Session, now: datetime) -> int:
    """Remove expired sessions; returns how many. Called on login to keep the table small."""
    result = db.execute(delete(AuthSession).where(AuthSession.expires_at <= now))
    db.commit()
    return result.rowcount
