"""Password hashing with scrypt from the standard library (no extra dependency).

A stored hash looks like "scrypt$16384$8$1$<salt hex>$<hash hex>", so the cost
parameters can be raised later without breaking existing accounts:
needs_rehash() says when a hash was made with older settings.
"""

import hashlib
import hmac
import secrets

# OWASP's minimum for scrypt (N=2^17 is their stronger option; this keeps a
# login under ~100 ms on a laptop and inside scrypt's default 32 MiB memory cap).
N, R, P = 2**14, 8, 1
SALT_BYTES = 16
KEY_BYTES = 32


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=KEY_BYTES
    )


def hash_password(password: str) -> str:
    """A salted scrypt hash of `password`, safe to store."""
    salt = secrets.token_bytes(SALT_BYTES)
    key = _derive(password, salt, N, R, P)
    return f"scrypt${N}${R}${P}${salt.hex()}${key.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Whether `password` matches `stored`. False for a malformed hash."""
    try:
        scheme, n, r, p, salt, key = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = bytes.fromhex(key)
        actual = _derive(password, bytes.fromhex(salt), int(n), int(r), int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def needs_rehash(stored: str) -> bool:
    """True if `stored` wasn't made with the current settings."""
    return not stored.startswith(f"scrypt${N}${R}${P}$")


# Checked against on a login for an unknown username, so a wrong username takes
# as long as a wrong password and response times don't reveal which accounts exist.
DUMMY_HASH = hash_password(secrets.token_hex(16))
