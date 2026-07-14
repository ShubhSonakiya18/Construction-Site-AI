"""
app/core/security.py — Password hashing and JWT token utilities.

Scope:
    Sprint 7 (frozen, unmodified below): password hashing, access-token
    encode/decode. Supports POST /api/v1/auth/login.
    Sprint 8 (added below, additive only): opaque refresh-token generation
    and hashing. Supports POST /api/v1/auth/refresh, /logout, /logout-all.
    See docs/AUTHENTICATION_ARCHITECTURE.md for the full token lifecycle.

Why these are plain functions, not a class:
    Both password hashing and JWT encode/decode are pure transformations —
    input in, output out, no shared state, no I/O. A class would add
    ceremony without benefit. This also means database/seed/ code can hash
    a password at seed time (see database/seed/sample_data.py) by importing
    just hash_password(), without importing FastAPI or touching a request.

Why passlib + bcrypt (not hashlib/pyjwt directly):
    bcrypt is the standard for password storage — includes a work factor
    (cost) and a per-hash salt automatically, so this module never handles
    salts manually. passlib's CryptContext also gives a clean upgrade path
    if a stronger scheme is added later (deprecated="auto" would re-hash on
    next login) without changing calling code.

KNOWN COMPATIBILITY CONSTRAINT:
    passlib 1.7.4 (last released 2020, unmaintained) crashes against
    bcrypt>=4.1 — its version-detection probe reads bcrypt.__about__,
    which newer bcrypt releases removed. requirements-dev.txt pins
    bcrypt==4.0.1 explicitly for this reason. Do not upgrade bcrypt without
    re-running tests/test_core_security.py first.

Access tokens vs. refresh tokens — two different mechanisms, deliberately:
    Access tokens (Sprint 7, unchanged) are self-contained signed JWTs —
    the server verifies them with zero I/O (just a signature check), which
    is why they're short-lived (default 60 min): there is no way to revoke
    one before it expires without maintaining a blacklist of every access
    token ever issued, which defeats the point of a stateless token.
    Refresh tokens (Sprint 8, new) are the opposite: opaque random strings
    with NO embedded claims and NO signature to verify. Their entire
    security property comes from being unguessable (32 bytes of
    os.urandom, per secrets.token_urlsafe) plus a server-side lookup
    against database/models/auth.py:UserSession, which is what makes them
    revocable — logout, logout-all-devices, and password-change-invalidates-
    sessions are all just UPDATE user_sessions SET revoked_at = now().
    A JWT refresh token would need the exact same server-side table to be
    revocable, so making it a JWT would add signature overhead for no
    actual benefit — an opaque token is simpler and just as secure here.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Refresh tokens are 32 bytes of CSPRNG output, base64url-encoded — same
# entropy class as a JWT signing key, far more than needed to resist
# brute-force guessing (2^256 possibilities).
REFRESH_TOKEN_BYTES = 32


# ── Password hashing ──────────────────────────────────────────────────────────

def hash_password(plain_password: str) -> str:
    """Return a bcrypt hash of plain_password. Never store the plaintext."""
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Return True if plain_password matches the given bcrypt hash.

    Returns False (does not raise) for a malformed/empty hash — e.g. a User
    row whose hashed_password is still NULL (unset, pre-Sprint-7 seed data)
    fails verification instead of crashing the login endpoint.
    """
    if not hashed_password:
        return False
    try:
        return _pwd_context.verify(plain_password, hashed_password)
    except (ValueError, TypeError):
        return False


# ── JWT access tokens ─────────────────────────────────────────────────────────

def create_access_token(
    subject: str,
    *,
    secret_key: str,
    algorithm: str = "HS256",
    expires_minutes: int = 60,
    extra_claims: Optional[dict[str, Any]] = None,
) -> str:
    """Encode a signed JWT access token.

    Args:
        subject: The `sub` claim — this backend uses the User.id (str(UUID)).
        secret_key: HMAC signing secret (from Settings.jwt_secret_key).
        algorithm: JWT signing algorithm (from Settings.jwt_algorithm).
        expires_minutes: Token lifetime (from Settings.jwt_access_token_expire_minutes).
        extra_claims: Additional claims merged into the payload — this backend
            embeds company_id and role so every request can be scoped to a
            tenant without an extra DB lookup per request.
    """
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, secret_key, algorithm=algorithm)


def decode_access_token(
    token: str, *, secret_key: str, algorithm: str = "HS256"
) -> Optional[dict[str, Any]]:
    """Decode and verify a JWT access token.

    Returns the claims dict on success, or None if the token is expired,
    malformed, or has an invalid signature. Callers (see app/api/dependencies.py)
    treat None as "unauthenticated" and raise HTTP 401 — this function itself
    never raises for expected failure modes, matching the ExtractionResult /
    SpeechProcessingResult convention used throughout Sprints 3-5.
    """
    try:
        return jwt.decode(token, secret_key, algorithms=[algorithm])
    except JWTError:
        return None


# ── Refresh tokens (Sprint 8) ────────────────────────────────────────────────

def generate_refresh_token() -> str:
    """Generate a new opaque refresh token (the raw value sent to the client
    exactly once, at issue time — never stored anywhere in this form).

    See module docstring for why this is a random string, not a JWT.
    """
    return secrets.token_urlsafe(REFRESH_TOKEN_BYTES)


def hash_refresh_token(raw_token: str) -> str:
    """Return the SHA-256 hex digest of a raw refresh token.

    This, not the raw token, is what UserSession.refresh_token_hash stores
    and what get_by_token_hash() looks up by. SHA-256 (not bcrypt) is
    correct here — see module docstring: we're hashing a high-entropy
    32-byte random value to make database exfiltration non-exploitable,
    not defending against low-entropy human-guessable input, so bcrypt's
    deliberate slowness buys nothing and would only slow down every
    refresh request for no security benefit.
    """
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
