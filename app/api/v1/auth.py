"""
app/api/v1/auth.py — POST /api/v1/auth/login.

Sprint 7 scope only (NEXT_SPRINT.md §3): login against an existing,
pre-seeded User row. No registration, no password reset, no user
management. See app/core/dev_seed.py for the one demo account this backend
ships with.

Business logic (verify credentials, issue token) intentionally lives here
rather than in a separate AuthService — this is a five-line lookup + a
password check + a token encode, all using functions that already exist in
app/core/security.py and database/repositories/company.py. Introducing a
service class would wrap three function calls in a fourth function for no
behavioral benefit. Compare to app/api/v1/daily_logs.py and audio.py,
which DO have a service layer, because pipeline orchestration is genuinely
multi-step business logic.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_app_settings, get_db
from app.core.config import Settings
from app.core.security import create_access_token, verify_password
from app.schemas.auth import LoginRequest, LoginResponseData
from app.schemas.envelope import APIResponse, success_response
from database.repositories.company import UserRepository

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/login",
    response_model=APIResponse[LoginResponseData],
    summary="Log in and receive a JWT access token",
    description=(
        "Verifies email + password against the users table and returns a "
        "Bearer access token. Sprint 7 provides exactly one working "
        "account for local testing — see docs/BACKEND_STARTUP.md."
    ),
)
def login(
    body: LoginRequest,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> APIResponse[LoginResponseData]:
    repo = UserRepository(session)
    user = repo.get_by_email(body.email)

    # Same error for "no such user" and "wrong password" — do not reveal
    # which case occurred (standard practice: avoids account enumeration).
    if user is None or not user.is_active or not verify_password(
        body.password, user.hashed_password or ""
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )

    token = create_access_token(
        subject=str(user.id),
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
        expires_minutes=settings.jwt_access_token_expire_minutes,
        extra_claims={
            "company_id": str(user.company_id),
            "role": user.role,
            "email": user.email,
        },
    )

    return success_response(
        LoginResponseData(
            access_token=token,
            expires_in_minutes=settings.jwt_access_token_expire_minutes,
            user_id=str(user.id),
            company_id=str(user.company_id),
            role=user.role,
            email=user.email,
        ),
        message="Login successful.",
    )
