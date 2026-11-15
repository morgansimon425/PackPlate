"""Account routes and the session cookie, against the test database."""

from datetime import timedelta

from fastapi import Depends
from sqlalchemy import inspect, select, update

from app.api.auth import COOKIE_SECURE
from app.deps import current_user, optional_user
from app.main import app
from app.services.auth import SESSION_COOKIE
from app.services.hours import campus_time
from db.models import AuthSession, User

WOLF = {"username": "Mr_Wolf", "password": "howl at the moon"}


def register(client, creds=WOLF):
    return client.post("/auth/register", json=creds)


def test_register_logs_in_and_stores_only_a_hash(client, db):
    response = register(client)
    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "mr_wolf"
    assert set(body) == {"id", "username", "open_to_chat", "created_at"}
    assert body["open_to_chat"] is False  # off until the user turns it on

    cookie = response.headers["set-cookie"]
    assert f"{SESSION_COOKIE}=" in cookie
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie
    assert ("Secure" in cookie) == COOKIE_SECURE

    assert client.get("/auth/me").json()["username"] == "mr_wolf"

    [user] = db.scalars(select(User)).all()
    assert WOLF["password"] not in user.password_hash
    # No email, real name, or diet: only what an account needs.
    assert {c.name for c in inspect(User).columns} == {
        "id",
        "username",
        "password_hash",
        "open_to_chat",
        "created_at",
    }
    # The session table holds a hash of the cookie, not the cookie.
    [session] = db.scalars(select(AuthSession)).all()
    assert session.token_hash != client.cookies[SESSION_COOKIE]


def test_register_rejects_bad_input(client):
    assert (
        register(client, {"username": "ab", "password": "longenough"}).status_code
        == 400
    )
    assert (
        register(client, {"username": "wolf", "password": "short"}).status_code == 400
    )
    assert register(client, {"username": "wolf"}).status_code == 422
    assert (
        register(
            client, {"username": "wolf", "password": "longenough", "admin": True}
        ).status_code
        == 422
    )


def test_usernames_are_unique_ignoring_case(client):
    assert register(client).status_code == 201
    again = register(client, {"username": "MR_WOLF", "password": "another one!"})
    assert again.status_code == 409


def test_logout_then_login(client):
    register(client)
    assert client.post("/auth/logout").status_code == 204
    assert client.get("/auth/me").status_code == 401

    wrong = client.post("/auth/login", json={**WOLF, "password": "not it at all"})
    assert wrong.status_code == 401
    unknown = client.post("/auth/login", json={**WOLF, "username": "nobody"})
    assert unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]  # doesn't say which

    ok = client.post("/auth/login", json={**WOLF, "username": "MR_wolf"})
    assert ok.status_code == 200
    assert client.get("/auth/me").json()["username"] == "mr_wolf"


def test_logout_revokes_the_session_server_side(client, db):
    register(client)
    token = client.cookies[SESSION_COOKIE]
    client.post("/auth/logout")
    # Replaying the old cookie doesn't work: the row is gone.
    client.cookies.set(SESSION_COOKIE, token)
    assert client.get("/auth/me").status_code == 401
    assert db.scalars(select(AuthSession)).all() == []


def test_login_replaces_the_old_session(client, db):
    register(client)
    client.post("/auth/login", json=WOLF)
    assert len(db.scalars(select(AuthSession)).all()) == 1


def test_expired_and_forged_sessions_are_rejected(client, db):
    register(client)
    db.execute(update(AuthSession).values(expires_at=campus_time() - timedelta(1)))
    db.commit()
    assert client.get("/auth/me").status_code == 401
    client.cookies.set(SESSION_COOKIE, "made-up-token")
    assert client.get("/auth/me").status_code == 401


def test_too_many_failed_logins(client):
    register(client)
    client.post("/auth/logout")
    for _ in range(10):
        assert (
            client.post(
                "/auth/login", json={**WOLF, "password": "wrong guess"}
            ).status_code
            == 401
        )
    blocked = client.post("/auth/login", json=WOLF)  # even the right password
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0


def test_delete_account(client, db):
    register(client)
    assert (
        client.request("DELETE", "/auth/me", json={"password": "wrong one"}).status_code
        == 401
    )
    assert (
        client.request(
            "DELETE", "/auth/me", json={"password": WOLF["password"]}
        ).status_code
        == 204
    )
    assert client.get("/auth/me").status_code == 401
    assert db.scalars(select(User)).all() == []
    assert db.scalars(select(AuthSession)).all() == []
    assert client.post("/auth/login", json=WOLF).status_code == 401


def test_other_features_can_require_a_login(client):
    """The dependencies M4 chat and M5 preferences will use."""

    @app.get("/_test/needs-login")
    def needs_login(user: User = Depends(current_user)):
        return {"id": user.id}

    @app.get("/_test/maybe-login")
    def maybe_login(user: User | None = Depends(optional_user)):
        return {"username": user.username if user else None}

    try:
        assert client.get("/_test/needs-login").status_code == 401
        assert client.get("/_test/maybe-login").json() == {"username": None}
        user_id = register(client).json()["id"]
        assert client.get("/_test/needs-login").json() == {"id": user_id}
        assert client.get("/_test/maybe-login").json() == {"username": "mr_wolf"}
    finally:
        app.router.routes[:] = [
            r
            for r in app.router.routes
            if not getattr(r, "path", "").startswith("/_test")
        ]


def test_existing_features_still_work_logged_out(client, seed):
    seed.location(1)
    assert client.get("/locations").status_code == 200
    assert client.post("/crowd/1", json={"level": "crowded"}).status_code == 201


def test_open_to_chat_setting(client, db):
    assert client.patch("/auth/me", json={"open_to_chat": True}).status_code == 401
    register(client)
    on = client.patch("/auth/me", json={"open_to_chat": True})
    assert on.status_code == 200 and on.json()["open_to_chat"] is True
    assert client.get("/auth/me").json()["open_to_chat"] is True
    assert db.scalars(select(User)).one().open_to_chat is True
    off = client.patch("/auth/me", json={"open_to_chat": False})
    assert off.json()["open_to_chat"] is False
    for bad in ({}, {"open_to_chat": "maybe"}, {"open_to_chat": True, "username": "x"}):
        assert client.patch("/auth/me", json=bad).status_code == 422


def test_logged_out_requests_need_no_database():
    """A request with no session cookie is a 401 before any database work, so
    it works (and stays cheap) even when the database isn't there."""
    from fastapi.testclient import TestClient

    assert TestClient(app).get("/auth/me").status_code == 401
