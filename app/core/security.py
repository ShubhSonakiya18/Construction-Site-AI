"""
app/core/security.py — Password hashing and JWT token utilities.

Scope (Sprint 7, per NEXT_SPRINT.md §3):
    Basic JWT login only. No registration, no password reset, no user
    management. These functions exist to support exactly one flow:
    POST /api/v1/auth/login verifying a password and issuing a token.

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
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


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
