"""
app/api/v1/users.py — User CRUD, profile, deactivate/restore, role assignment.

Sprint 8, Subsystem 4. Every route is tenant-scoped (Subsystem 3 —
UserService.get_user_scoped()) and permission-gated (Subsystem 2 —
require_permission()). Business logic (email uniqueness, role hierarchy,
last-admin protection, audit logging) lives entirely in UserService — see
that module's docstring for why this crosses the "needs a service" threshold
this codebase established with AuthService/pipeline_service.py.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_app_settings, get_db, require_permission
from app.core.config import Settings
from app.core.permissions import Permission
from app.schemas.envelope import APIResponse, PaginationMeta, success_response
from app.schemas.user import (
    AssignRoleRequest,
    CreateUserRequest,
    UpdateProfileRequest,
    UserRead,
)
from app.services.auth_service import AuthService
from app.services.user_service import UserService
from database.repositories.company import UserRepository
from database.repositories.tenant import TenantContext

router = APIRouter(prefix="/users", tags=["Users"])


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def _get_user_or_404(service: UserService, user_id: uuid.UUID, *, tenant: TenantContext):
    user = service.get_user_scoped(user_id, tenant=tenant)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found."
        )
    return user


@router.post(
    "",
    response_model=APIResponse[UserRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user in the caller's company",
)
def create_user(
    body: CreateUserRequest,
    request: Request,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission(Permission.USER_CREATE)),
) -> APIResponse[UserRead]:
    if body.role == "system_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="system_admin cannot be granted via user creation.",
        )
    tenant = TenantContext.from_current_user(user)
    service = UserService(session)
    new_user = service.create_user(
        tenant=tenant,
        actor_id=user.user_id,
        email=body.email,
        password=body.password,
        first_name=body.first_name,
        last_name=body.last_name,
        role=body.role,
        ip_address=_client_ip(request),
    )
    return success_response(
        UserRead.model_validate(new_user), message="User created."
    )


@router.get(
    "",
    response_model=APIResponse[list[UserRead]],
    summary="List users in the caller's company",
)
def list_users(
    limit: int = 100,
    offset: int = 0,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission(Permission.USER_READ)),
) -> APIResponse[list[UserRead]]:
    repo = UserRepository(session)
    users = repo.list_by_company(user.company_id, limit=limit, offset=offset)
    return success_response(
        [UserRead.model_validate(u) for u in users],
        message=f"Found {len(users)} user(s).",
        metadata=PaginationMeta(
            total=len(users), limit=limit, offset=offset, count=len(users)
        ).model_dump(),
    )


@router.get(
    "/{user_id}",
    response_model=APIResponse[UserRead],
    summary="Get a single user in the caller's company",
)
def get_user(
    user_id: uuid.UUID,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission(Permission.USER_READ)),
) -> APIResponse[UserRead]:
    tenant = TenantContext.from_current_user(user)
    service = UserService(session)
    target = _get_user_or_404(service, user_id, tenant=tenant)
    return success_response(UserRead.model_validate(target), message="User retrieved.")


@router.patch(
    "/{user_id}/profile",
    response_model=APIResponse[UserRead],
    summary="Update a user's profile (first/last name)",
)
def update_profile(
    user_id: uuid.UUID,
    body: UpdateProfileRequest,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission(Permission.USER_UPDATE)),
) -> APIResponse[UserRead]:
    tenant = TenantContext.from_current_user(user)
    service = UserService(session)
    target = _get_user_or_404(service, user_id, tenant=tenant)
    updated = service.update_profile(
        user=target, actor_id=user.user_id,
        first_name=body.first_name, last_name=body.last_name,
    )
    return success_response(UserRead.model_validate(updated), message="Profile updated.")


@router.post(
    "/{user_id}/deactivate",
    response_model=APIResponse[UserRead],
    summary="Deactivate (soft-delete) a user",
)
def deactivate_user(
    user_id: uuid.UUID,
    request: Request,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission(Permission.USER_DEACTIVATE)),
) -> APIResponse[UserRead]:
    tenant = TenantContext.from_current_user(user)
    service = UserService(session)
    target = _get_user_or_404(service, user_id, tenant=tenant)
    deactivated = service.deactivate_user(
        user=target, actor_id=user.user_id, ip_address=_client_ip(request),
    )
    return success_response(UserRead.model_validate(deactivated), message="User deactivated.")


@router.post(
    "/{user_id}/restore",
    response_model=APIResponse[UserRead],
    summary="Restore a soft-deleted user",
)
def restore_user(
    user_id: uuid.UUID,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission(Permission.USER_RESTORE)),
) -> APIResponse[UserRead]:
    tenant = TenantContext.from_current_user(user)
    # A soft-deleted user is invisible to get_user_scoped() (BaseRepository
    # excludes deleted_at IS NOT NULL by default) — restore needs the
    # include_deleted path, so this looks the user up directly rather than
    # through _get_user_or_404().
    repo = UserRepository(session)
    target = repo.get_by_id(user_id, include_deleted=True)
    if target is None or target.company_id != tenant.company_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found."
        )
    service = UserService(session)
    restored = service.restore_user(user=target, actor_id=user.user_id)
    return success_response(UserRead.model_validate(restored), message="User restored.")


@router.patch(
    "/{user_id}/role",
    response_model=APIResponse[UserRead],
    summary="Assign a new role to a user",
    description=(
        "Enforces: no self-assignment, role hierarchy (cannot assign a "
        "role above the caller's own rank), and last-owner/admin "
        "protection. See docs/AUTHORIZATION_ARCHITECTURE.md."
    ),
)
def assign_role(
    user_id: uuid.UUID,
    body: AssignRoleRequest,
    request: Request,
    session: Session = Depends(get_db),
    user: CurrentUser = Depends(require_permission(Permission.USER_ASSIGN_ROLE)),
) -> APIResponse[UserRead]:
    tenant = TenantContext.from_current_user(user)
    service = UserService(session)
    target = _get_user_or_404(service, user_id, tenant=tenant)
    updated = service.assign_role(
        target_user=target, new_role=body.role,
        actor_id=user.user_id, actor_role=user.role,
        ip_address=_client_ip(request),
    )
    return success_response(UserRead.model_validate(updated), message="Role assigned.")


@router.post(
    "/{user_id}/unlock",
    response_model=APIResponse[UserRead],
    summary="Clear an account lockout before it naturally expires",
    description=(
        "Admin unlock — resets failed_login_attempts to 0 and clears "
        "locked_until immediately. See docs/AUTHENTICATION_ARCHITECTURE.md "
        "'Account Lockout' for the full lockout lifecycle."
    ),
)
def unlock_user(
    user_id: uuid.UUID,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
    user: CurrentUser = Depends(require_permission(Permission.USER_UNLOCK)),
) -> APIResponse[UserRead]:
    tenant = TenantContext.from_current_user(user)
    user_service = UserService(session)
    target = _get_user_or_404(user_service, user_id, tenant=tenant)
    auth_service = AuthService(session, settings)
    unlocked = auth_service.unlock_user(user=target, actor_id=user.user_id)
    return success_response(UserRead.model_validate(unlocked), message="Account unlocked.")
