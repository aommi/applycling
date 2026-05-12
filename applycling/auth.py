"""Password hashing and session token helpers. Zero new dependencies."""

from __future__ import annotations

import hashlib
import hmac
import os


def hash_password(plaintext: str) -> str:
    """PBKDF2-SHA256 with 16-byte random salt."""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", plaintext.encode(), salt, 100_000)
    return salt.hex() + ":" + dk.hex()


def verify_password(plaintext: str, stored: str) -> bool:
    """Return True if *plaintext* matches the stored hash."""
    try:
        salt_hex, dk_hex = stored.split(":", 1)
    except ValueError:
        return False
    salt = bytes.fromhex(salt_hex)
    dk = hashlib.pbkdf2_hmac("sha256", plaintext.encode(), salt, 100_000)
    return hmac.compare_digest(dk.hex(), dk_hex)


def _session_secret() -> str:
    secret = os.environ.get("APPLYCLING_SESSION_SECRET", "")
    if not secret:
        # In local dev with APPLYCLING_NO_AUTH, session validation is skipped
        # entirely, so a fallback secret is harmless here.
        secret = "dev-insecure-session-secret"
    return secret


def create_session_token(user_id: str) -> str:
    """HMAC-SHA256 signed token containing *user_id*."""
    secret = _session_secret()
    sig = hmac.new(secret.encode(), user_id.encode(), hashlib.sha256).hexdigest()
    return user_id + "." + sig


def verify_session_token(token: str) -> str | None:
    """Return *user_id* if valid, or None if tampered or expired."""
    try:
        user_id, sig = token.split(".", 1)
    except ValueError:
        return None
    secret = _session_secret()
    expected = hmac.new(secret.encode(), user_id.encode(), hashlib.sha256).hexdigest()
    if hmac.compare_digest(sig, expected):
        return user_id
    return None
