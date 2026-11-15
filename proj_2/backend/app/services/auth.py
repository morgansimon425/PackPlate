"""Account rules: what a valid username and password are, and session tokens.

Sessions are opaque random tokens kept in an HttpOnly cookie; the database
stores only their SHA-256 (see db.models.AuthSession). No JWTs: a session can
be revoked by deleting its row, and nothing about the user is in the token.
"""

import hashlib
import os
import re
import secrets
import threading
import time
from datetime import timedelta

USERNAME_PATTERN = re.compile(r"^[a-z0-9_]{3,30}$")
PASSWORD_MIN = 8
PASSWORD_MAX = 128  # scrypt is happy with more; this just bounds request cost

SESSION_COOKIE = "packplate_session"
SESSION_LIFETIME = timedelta(days=int(os.getenv("SESSION_DAYS", "30")))


def normalize_username(username: str) -> str:
    """Usernames are case-insensitive: stored and looked up lowercased."""
    return username.strip().lower()


def username_problem(username: str) -> str | None:
    """Why `username` (already normalized) can't be used, or None if it can."""
    if not USERNAME_PATTERN.fullmatch(username):
        return "username must be 3-30 characters: letters, numbers, or _"
    return None


def password_problem(password: str, username: str) -> str | None:
    """Why `password` is too weak to accept, or None if it's fine."""
    if len(password) < PASSWORD_MIN:
        return f"password must be at least {PASSWORD_MIN} characters"
    if len(password) > PASSWORD_MAX:
        return f"password must be at most {PASSWORD_MAX} characters"
    if password.strip().lower() == username:
        return "password can't be the same as your username"
    return None


def new_token() -> str:
    """A fresh session token for the cookie (256 bits, URL-safe)."""
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    """What the database stores for `token`."""
    return hashlib.sha256(token.encode("ascii", errors="replace")).hexdigest()


class LoginLimiter:
    """Slows password guessing: after `limit` failed logins for one username from
    one client within `window` seconds, further tries are refused until the
    oldest failure ages out. In memory only, like the crowd throttle; the API
    is a single process, so it resets on restart.
    """

    def __init__(self, limit: int = 10, window: float = 15 * 60, clock=time.monotonic):
        self.limit = limit
        self.window = window
        self.clock = clock
        self._failures: dict[tuple, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key, now: float) -> list[float]:
        recent = [t for t in self._failures.get(key, []) if now - t < self.window]
        if recent:
            self._failures[key] = recent
        else:
            self._failures.pop(key, None)
        return recent

    def retry_after(self, key) -> float:
        """Seconds until `key` may try again; 0 if it may try now."""
        with self._lock:
            now = self.clock()
            recent = self._recent(key, now)
            if len(recent) < self.limit:
                return 0
            return self.window - (now - recent[-self.limit])

    def failed(self, key):
        """Record a failed login for `key`."""
        with self._lock:
            now = self.clock()
            self._failures[key] = [*self._recent(key, now), now]

    def succeeded(self, key):
        """Forget `key`'s failures after a correct password."""
        with self._lock:
            self._failures.pop(key, None)
