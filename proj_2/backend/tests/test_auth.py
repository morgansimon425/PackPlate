"""Password hashing, account rules, and the failed-login limiter (no database)."""

from app.services import passwords
from app.services.auth import (
    LoginLimiter,
    new_token,
    normalize_username,
    password_problem,
    token_hash,
    username_problem,
)


def test_hash_verifies_only_the_right_password():
    stored = passwords.hash_password("correct horse")
    assert stored.startswith("scrypt$")
    assert "correct horse" not in stored
    assert passwords.verify_password("correct horse", stored)
    assert not passwords.verify_password("correct horsE", stored)
    assert not passwords.verify_password("", stored)


def test_same_password_hashes_differently():
    # A fresh salt each time, so equal passwords don't show up as equal hashes.
    assert passwords.hash_password("same pass") != passwords.hash_password("same pass")


def test_malformed_hashes_never_verify():
    for stored in ("", "plain", "bcrypt$1$2$3$aa$bb", "scrypt$x$8$1$aa$bb", "scrypt$"):
        assert not passwords.verify_password("anything", stored)


def test_needs_rehash_when_cost_changes(monkeypatch):
    stored = passwords.hash_password("pw123456")
    assert not passwords.needs_rehash(stored)
    monkeypatch.setattr(passwords, "N", 2**15)
    assert passwords.needs_rehash(stored)
    assert passwords.verify_password("pw123456", stored)  # old hashes still work


def test_usernames_are_case_insensitive_and_limited():
    assert normalize_username("  Mr_Wolf ") == "mr_wolf"
    assert username_problem("mr_wolf") is None
    for bad in ("ab", "a" * 31, "has space", "émile", "dash-name", ""):
        assert username_problem(bad) is not None


def test_password_rules():
    assert password_problem("longenough", "wolf") is None
    assert password_problem("short", "wolf") is not None
    assert password_problem("x" * 129, "wolf") is not None
    assert password_problem("WolfPack1", "wolfpack1") is not None  # same as username


def test_tokens_are_random_and_stored_hashed():
    a, b = new_token(), new_token()
    assert a != b and len(a) >= 40
    assert token_hash(a) == token_hash(a) != a
    assert len(token_hash(a)) == 64


def test_limiter_blocks_after_limit_and_recovers():
    now = [0.0]
    limiter = LoginLimiter(limit=3, window=60, clock=lambda: now[0])
    key = ("1.2.3.4", "wolf")
    for _ in range(3):
        assert limiter.retry_after(key) == 0
        limiter.failed(key)
        now[0] += 1
    assert limiter.retry_after(key) == 57  # first failure at t=0 ages out at t=60
    assert limiter.retry_after(("1.2.3.4", "other")) == 0  # per username
    now[0] = 60
    assert limiter.retry_after(key) == 0


def test_limiter_forgets_after_success():
    limiter = LoginLimiter(limit=2, window=60, clock=lambda: 0.0)
    key = ("1.2.3.4", "wolf")
    limiter.failed(key)
    limiter.succeeded(key)
    limiter.failed(key)
    assert limiter.retry_after(key) == 0
