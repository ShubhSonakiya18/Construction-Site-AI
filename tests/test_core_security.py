"""
tests/test_core_security.py — Tests for app/core/security.py.

Covers password hashing (bcrypt via passlib) and JWT encode/decode
(python-jose) as pure functions, with no FastAPI or database dependency.
"""
from __future__ import annotations

import time

import pytest

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


# ── Password hashing ──────────────────────────────────────────────────────────

class TestPasswordHashing:
    def test_hash_is_not_plaintext(self):
        hashed = hash_password("Admin@123")
        assert hashed != "Admin@123"
        assert hashed.startswith("$2b$")  # bcrypt identifier

    def test_verify_correct_password(self):
        hashed = hash_password("Admin@123")
        assert verify_password("Admin@123", hashed) is True

    def test_verify_wrong_password(self):
        hashed = hash_password("Admin@123")
        assert verify_password("WrongPassword", hashed) is False

    def test_verify_against_null_hash_returns_false_not_raise(self):
        """A User row with hashed_password=NULL (pre-Sprint-7 seed data)
        must fail verification cleanly, not crash the login endpoint."""
        assert verify_password("anything", "") is False
        assert verify_password("anything", None) is False  # type: ignore[arg-type]

    def test_verify_against_malformed_hash_returns_false_not_raise(self):
        assert verify_password("anything", "not-a-real-bcrypt-hash") is False

    def test_same_password_produces_different_hashes(self):
        """bcrypt salts each hash — two hashes of the same password differ,
        but both still verify against the same plaintext."""
        h1 = hash_password("Admin@123")
        h2 = hash_password("Admin@123")
        assert h1 != h2
        assert verify_password("Admin@123", h1) is True
        assert verify_password("Admin@123", h2) is True


# ── JWT tokens ─────────────────────────────────────────────────────────────────

SECRET = "test-secret-key-not-for-production"


class TestJWTTokens:
    def test_create_and_decode_round_trip(self):
        token = create_access_token(
            "user-123", secret_key=SECRET, expires_minutes=60
        )
        claims = decode_access_token(token, secret_key=SECRET)
        assert claims is not None
        assert claims["sub"] == "user-123"

    def test_extra_claims_embedded(self):
        token = create_access_token(
            "user-123",
            secret_key=SECRET,
            extra_claims={"company_id": "company-abc", "role": "owner"},
        )
        claims = decode_access_token(token, secret_key=SECRET)
        assert claims["company_id"] == "company-abc"
        assert claims["role"] == "owner"

    def test_decode_with_wrong_secret_returns_none(self):
        token = create_access_token("user-123", secret_key=SECRET)
        claims = decode_access_token(token, secret_key="a-different-secret")
        assert claims is None

    def test_decode_malformed_token_returns_none(self):
        assert decode_access_token("not.a.jwt", secret_key=SECRET) is None
        assert decode_access_token("", secret_key=SECRET) is None

    def test_expired_token_returns_none(self):
        token = create_access_token(
            "user-123", secret_key=SECRET, expires_minutes=-1
        )
        assert decode_access_token(token, secret_key=SECRET) is None

    def test_algorithm_mismatch_returns_none(self):
        token = create_access_token(
            "user-123", secret_key=SECRET, algorithm="HS256"
        )
        claims = decode_access_token(token, secret_key=SECRET, algorithm="HS384")
        assert claims is None
