"""
app/services/user_service.py — User management orchestration.

Sprint 8, Subsystem 4. Same service-layer rationale as AuthService
(app/services/auth_service.py) and pipeline_service.py: creating a user
is genuinely multi-step (email-uniqueness check across the whole system —
User.email is globally unique per database/models/company.py — + password
hash + tenant assignment + audit log), and role assignment carries real
business rules (hierarchy, self-assignment block, last-admin protection)
that do not belong duplicated across multiple router handlers.

Every method here assumes the caller (a router) has already verified the
actor holds the relevant Permission via require_permission() — this
service does NOT re-check permissions, it enforces business rules that
sit BELOW the permission layer (e.g. "you have USER_ASSIGN_ROLE, but you
still can't promote someone above your own rank").
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.permissions import can_assign_role
from app.core.security import hash_password
from app.services.audit_helpers import safe_log_event
from database.models.company import User
from database.repositories.auth import UserSessionRepository
from database.repositories.company import UserRepository
from database.repositories.generation import AuditLogRepository
from database.repositories.tenant import TenantContext

logger = logging.getLogger("app.users")

_LAST_ADMIN_ROLES = frozenset({"owner", "admin"})


class UserService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._sessions = UserSessionRepository(session)
        self._audit = AuditLogRepository(session)

    # ── Create ────────────────────────────────────────────────────────────

    def create_user(
        self,
        *,
        tenant: TenantContext,
        actor_id: UUID,
        email: str,
        password: str,
        first_name: str,
        last_name: str,
        role: str,
        request_id: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> User:
        """Create a new user within the actor's company.

        Raises HTTPException(409) if the email is already registered
        (User.email is globally unique across ALL companies, not just
        this one — see database/models/company.py User docstring; this
        is a real cross-tenant constraint at the schema level, so the
        conflict check is correctly unscoped even though everything else
        in this service is tenant-scoped).
        """
        if self._users.email_exists(email):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email already exists.",
            )

        user = User(
            company_id=tenant.company_id,
            email=email,
            hashed_password=hash_password(password),
            first_name=first_name,
            last_name=last_name,
            role=role,
            is_active=True,
            created_by_id=actor_id,
        )
        self._users.create(user)

        safe_log_event(
            self._audit, "user.created",
            entity_type="user", entity_id=user.id,
            actor_id=actor_id, target_user_id=user.id, company_id=tenant.company_id,
            ip_address=ip_address, request_id=request_id, success=True,
            new_values={"email": email, "role": role},
        )
        return user

    # ── Read (tenant-scoped) ─────────────────────────────────────────────

    def get_user_scoped(self, user_id: UUID, *, tenant: TenantContext) -> Optional[User]:
        """Return a user only if they belong to tenant.company_id — the
        User equivalent of DailyLogRepository.get_with_children_scoped().
        UserRepository has no *_scoped() method of its own (User has a
        direct company_id column, so no join is needed — this one-line
        filter lives here rather than adding a full TenantScopedRepository
        subclass for a single simple comparison)."""
        user = self._users.get_by_id(user_id)
        if user is None or user.company_id != tenant.company_id:
            return None
        return user

    # ── Update ────────────────────────────────────────────────────────────

    def update_profile(
        self,
        *,
        user: User,
        actor_id: UUID,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> User:
        """Update a user's own editable profile fields. Deliberately does
        NOT accept role or email here — those go through
        assign_role()/a dedicated flow respectively, each with their own
        business rules, not silently through a generic profile update."""
        old_values = {"first_name": user.first_name, "last_name": user.last_name}
        if first_name is not None:
            user.first_name = first_name
        if last_name is not None:
            user.last_name = last_name
        self._users.update(user)

        safe_log_event(
            self._audit, "user.profile_updated",
            entity_type="user", entity_id=user.id,
            actor_id=actor_id, target_user_id=user.id, company_id=user.company_id,
            request_id=request_id, success=True,
            old_values=old_values,
            new_values={"first_name": user.first_name, "last_name": user.last_name},
        )
        return user

    # ── Deactivate / restore ─────────────────────────────────────────────

    def deactivate_user(
        self, *, user: User, actor_id: UUID, request_id: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> User:
        """Soft-delete a user and revoke every active session they hold —
        a deactivated user's still-valid tokens must stop working
        immediately, not linger until natural expiry (same posture as
        AuthService.change_password())."""
        self._guard_last_admin(user, action="deactivate")

        self._users.soft_delete(user)
        user.is_active = False
        self._session.flush()
        revoked = self._sessions.revoke_all_for_user(user.id, reason="user_deactivated")

        safe_log_event(
            self._audit, "user.deactivated",
            entity_type="user", entity_id=user.id,
            actor_id=actor_id, target_user_id=user.id, company_id=user.company_id,
            ip_address=ip_address, request_id=request_id, success=True,
            metadata={"sessions_revoked": revoked},
        )
        return user

    def restore_user(
        self, *, user: User, actor_id: UUID, request_id: Optional[str] = None,
    ) -> User:
        """Un-delete a soft-deleted user. Does NOT automatically restore
        is_active — a user could have been deactivated (is_active=False)
        without being soft-deleted, and restore() only reverses deletion;
        see the router for how the two states compose."""
        self._users.restore(user)
        self._session.flush()

        safe_log_event(
            self._audit, "user.restored",
            entity_type="user", entity_id=user.id,
            actor_id=actor_id, target_user_id=user.id, company_id=user.company_id,
            request_id=request_id, success=True,
        )
        return user

    # ── Role assignment ───────────────────────────────────────────────────

    def assign_role(
        self,
        *,
        target_user: User,
        new_role: str,
        actor_id: UUID,
        actor_role: str,
        request_id: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> User:
        """Change target_user's role, enforcing every explicit
        requirement from this subsystem's design checkpoint:

        1. Self-assignment is always rejected, regardless of the actor's
           own permission level — a user can never change their own role.
        2. The actor cannot assign a role ranked above their own
           (app.core.permissions.can_assign_role) — a company admin
           cannot create a system_admin, a project_manager cannot grant
           admin, etc.
        3. Demoting/removing the LAST owner-or-admin in a company is
           rejected — a company can never be left with zero users capable
           of administering it.

        Raises HTTPException(403) for (1) and (2), HTTPException(409) for
        (3) — 409 because it's a state conflict (this specific operation
        is fine in general, just not right now, given current company
        state), matching this codebase's existing ValueError->409
        convention for business-rule violations.
        """
        if target_user.id == actor_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You cannot change your own role.",
            )

        if not can_assign_role(actor_role=actor_role, target_role=new_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{actor_role}' is not permitted to assign role '{new_role}'.",
            )

        old_role = target_user.role
        if old_role in _LAST_ADMIN_ROLES and new_role not in _LAST_ADMIN_ROLES:
            self._guard_last_admin(target_user, action="demote")

        target_user.role = new_role
        self._users.update(target_user)

        safe_log_event(
            self._audit, "user.role_changed",
            entity_type="user", entity_id=target_user.id,
            actor_id=actor_id, target_user_id=target_user.id, company_id=target_user.company_id,
            ip_address=ip_address, request_id=request_id, success=True,
            old_values={"role": old_role},
            new_values={"role": new_role},
        )
        logger.info(
            "user.assign_role: actor=%s target=%s %s -> %s",
            actor_id, target_user.id, old_role, new_role,
        )
        return target_user

    # ── Internal ──────────────────────────────────────────────────────────

    def _guard_last_admin(self, user: User, *, action: str) -> None:
        """Raise HTTPException(409) if `user` is the last remaining
        owner-or-admin in their company — used by both deactivate_user()
        and assign_role() (when demoting away from owner/admin), since
        both operations have the identical failure mode: the company
        would be left with no one able to administer it."""
        if user.role not in _LAST_ADMIN_ROLES:
            return
        remaining_admins = self._users.list_by_company(user.company_id, limit=10_000)
        admin_count = sum(
            1 for u in remaining_admins
            if u.role in _LAST_ADMIN_ROLES and u.is_active and u.id != user.id
        )
        if admin_count == 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Cannot {action} the last owner/admin in this company — "
                    "assign another owner or admin first."
                ),
            )
