"""Routes for accounts: sign up, log in, log out, who am I, settings, delete.

A successful sign-up or login sets an HttpOnly session cookie; the browser
sends it back on every request (the frontend uses credentials: "include"), and
routes read the account through app.deps.current_user / optional_user.

Only a username, a password hash, and the Open to Chat setting are stored. Dietary profiles stay in the
browser, as before.
"""

import math
import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.deps import current_user, get_db
from app.repositories import chat_rooms as chat_repo
from app.repositories import users as users_repo
from app.schemas.auth import AccountSettings, Credentials, PasswordConfirm, UserOut
from app.services.auth import (
    SESSION_COOKIE,
    SESSION_LIFETIME,
    LoginLimiter,
    new_token,
    normalize_username,
    password_problem,
    token_hash,
    username_problem,
)
from app.services.hours import campus_time
from app.services.passwords import (
    DUMMY_HASH,
    hash_password,
    needs_rehash,
    verify_password,
)
from db.models import User

# Set COOKIE_SECURE=1 when the site is served over HTTPS, so the cookie is never
# sent in the clear. Left off by default because local development is plain HTTP.
COOKIE_SECURE = os.getenv("COOKIE_SECURE") == "1"

router = APIRouter(prefix="/auth", tags=["auth"])

_limiter = LoginLimiter()


def get_login_limiter() -> LoginLimiter:
    """The shared failed-login limiter, as a dependency so tests can swap in a fresh one."""
    return _limiter


def _start_session(response: Response, db: Session, user: User):
    token = new_token()
    now = campus_time()
    users_repo.delete_expired_sessions(db, now)
    users_repo.add_session(db, user.id, token_hash(token), now + SESSION_LIFETIME)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(SESSION_LIFETIME.total_seconds()),
        httponly=True,  # page scripts can't read it, so XSS can't steal it
        samesite="lax",  # not sent on cross-site POSTs (CSRF)
        secure=COOKIE_SECURE,
        path="/",
    )


def _end_session(request: Request, response: Response, db: Session):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        users_repo.delete_session(db, token_hash(token))
    response.delete_cookie(
        SESSION_COOKIE, httponly=True, samesite="lax", secure=COOKIE_SECURE, path="/"
    )


@router.post("/register", response_model=UserOut, status_code=201)
def register(body: Credentials, response: Response, db: Session = Depends(get_db)):
    """Create an account and log in. 400 if the username or password isn't allowed,
    409 if the username is taken. Usernames are case-insensitive.
    """
    username = normalize_username(body.username)
    problem = username_problem(username) or password_problem(body.password, username)
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    user = users_repo.create_user(db, username, hash_password(body.password))
    if user is None:
        raise HTTPException(status_code=409, detail="that username is taken")
    _start_session(response, db, user)
    return user


@router.post("/login", response_model=UserOut)
def login(
    body: Credentials,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    limiter: LoginLimiter = Depends(get_login_limiter),
):
    """Log in. 401 for a wrong username or password (the message doesn't say which),
    429 after too many failed tries for one username.
    """
    username = normalize_username(body.username)
    key = (request.client.host if request.client else None, username)
    retry_after = limiter.retry_after(key)
    if retry_after:
        raise HTTPException(
            status_code=429,
            detail="too many failed logins; try again later",
            headers={"Retry-After": str(math.ceil(retry_after))},
        )
    user = users_repo.get_by_username(db, username)
    # Check a password even when the user doesn't exist, so timing doesn't say so.
    ok = verify_password(body.password, user.password_hash if user else DUMMY_HASH)
    if user is None or not ok:
        limiter.failed(key)
        raise HTTPException(status_code=401, detail="wrong username or password")
    limiter.succeeded(key)
    if needs_rehash(user.password_hash):
        users_repo.set_password_hash(db, user, hash_password(body.password))
    _end_session(request, response, db)  # don't leave an old session behind
    _start_session(response, db, user)
    return user


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    """Log this browser out. Succeeds even if it wasn't logged in."""
    _end_session(request, response, db)
    response.status_code = 204
    return response


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    """The logged-in account. 401 when logged out."""
    return user


@router.patch("/me", response_model=UserOut)
def update_me(
    body: AccountSettings,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Change the logged-in account's settings: {"open_to_chat": true | false}."""
    users_repo.set_open_to_chat(db, user, body.open_to_chat)
    return user


@router.delete("/me", status_code=204)
def delete_me(
    body: PasswordConfirm,
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Delete the logged-in account and everything tied to it. Needs the password."""
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="wrong password")
    _end_session(request, response, db)
    # Leave chat rooms properly first, so the other members' rooms stay valid.
    chat_repo.leave_all_rooms(db, user.id)
    users_repo.delete_user(db, user)
    response.status_code = 204
    return response
