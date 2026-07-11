"""app/schemas/auth.py — Request/response models for POST /api/v1/auth/login.

Sprint 7 scope only: login. No registration, no password-reset schemas —
those are out of scope per NEXT_SPRINT.md §3 and will be defined in Sprint 8.
"""
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)


class LoginResponseData(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    user_id: str
    company_id: str
    role: str
    email: str
