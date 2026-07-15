"""app/schemas/user.py — Request/response models for /api/v1/users/*.

Sprint 8, Subsystem 4.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CreateUserRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    role: str = Field(
        ...,
        description=(
            "owner | admin | project_manager | foreman | safety_officer | "
            "client. system_admin cannot be granted at creation — see "
            "AUTHORIZATION_ARCHITECTURE.md role hierarchy."
        ),
    )


class UpdateProfileRequest(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)


class AssignRoleRequest(BaseModel):
    role: str = Field(..., description="The new role to assign to this user.")


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    email: str
    first_name: str
    last_name: str
    role: str
    is_active: bool
    created_at: datetime


class UserListMeta(BaseModel):
    total: int
    limit: int
    offset: int
