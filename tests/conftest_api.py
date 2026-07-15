"""
tests/conftest_api.py — Shared fixtures for app/ API tests.

Not named conftest.py deliberately: this module's fixtures (test_settings,
api_client, seeded_session) are specific to tests/test_api_*.py and are
imported explicitly (`from tests.conftest_api import ...` is unnecessary —
pytest fixtures in a file named conftest.py auto-apply to the whole
directory tree; naming this conftest_api.py and having each test_api_*.py
declare `pytest_plugins = ["tests.conftest_api"]` keeps these DB-backed,
app-building fixtures from being collected/instantiated for the other 700+
Sprint 1-6 tests that have nothing to do with the API layer).

WHY SQLite in-memory + StaticPool (not the live PostgreSQL this session
manually verified against):
    Same rationale as every Sprint 6 test: zero infrastructure, sub-second
    setup, portable CI. StaticPool is required (not just create_all on a
    fresh engine) because a FastAPI TestClient request and this fixture's
    setup code are different logical connections — plain sqlite:///:memory:
    gives each connection an empty, separate database. See
    tests/test_app_dev_seed.py for the same lesson learned earlier this
    session.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.core.config import Settings
from app.core.rate_limit import MemoryRateLimiter, get_rate_limiter
from app.create_app import create_app
from database.base import Base
from database.seed.reference_data import seed_all_reference_data
from database.seed.sample_data import seed_sample_data

TEST_JWT_SECRET = "test-secret-key-for-api-tests-only"


@pytest.fixture
def test_engine():
    eng = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def seeded_session(test_engine):
    """Seed reference + sample data (including the dev-admin placeholder
    row) into the in-memory DB, then hand back a Session for assertions."""
    with Session(test_engine) as session:
        seed_all_reference_data(session)
        seed_sample_data(session)
        session.commit()
        yield session


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        environment="testing",
        jwt_secret_key=TEST_JWT_SECRET,
        cors_allow_origins_raw="*",
        _env_file=None,  # do not read the real .env — fully isolated
    )


@pytest.fixture
def api_client(test_engine, seeded_session, test_settings):
    """A TestClient wired to the in-memory, pre-seeded database.

    Overrides get_db so every request in a test uses test_engine instead
    of the real DATABASE_URL — the app under test never touches
    PostgreSQL.
    """
    app = create_app(settings=test_settings)

    def _override_get_db():
        session_factory = sessionmaker(bind=test_engine, expire_on_commit=False)
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db

    # Sprint 8, Subsystem 5: app/core/rate_limit.py's get_rate_limiter()
    # returns a process-wide singleton by design (see that module's
    # docstring) — correct for the real app, but WRONG for tests, where
    # many test functions in the same pytest process would otherwise
    # share one rate-limit bucket and spuriously 429 each other out
    # (confirmed: this exact failure mode when this override was first
    # added). Each api_client gets its own fresh MemoryRateLimiter,
    # matching the same per-test-isolation the get_db override already
    # provides for the database.
    #
    # The instance is constructed ONCE, outside the override function,
    # and that same instance is returned on every call — a lambda that
    # constructed `MemoryRateLimiter()` inline would build a brand-new,
    # empty limiter on every single request (FastAPI calls dependency
    # overrides fresh per-request unless told otherwise), silently
    # defeating rate limiting entirely within a test. This bug was caught
    # by test_api_security_hardening.py's rate-limit tests failing with
    # "limit never reached" until this was fixed.
    test_rate_limiter = MemoryRateLimiter()
    app.dependency_overrides[get_rate_limiter] = lambda: test_rate_limiter

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
def dev_admin_password_hash(seeded_session):
    """Set the dev-admin user's password hash directly in the seeded
    session — mirrors what app.core.dev_seed.ensure_dev_admin_password()
    does against a real DB, without importing that script's engine-based
    plumbing into a test that already has a Session in hand."""
    from app.core.security import hash_password
    from database.models.company import User
    from database.seed.sample_data import DEV_ADMIN_ID

    user = seeded_session.get(User, DEV_ADMIN_ID)
    user.hashed_password = hash_password("Admin@123")
    seeded_session.flush()
    seeded_session.commit()
    return "Admin@123"


@pytest.fixture
def auth_token(api_client, dev_admin_password_hash):
    """Log in as the dev-admin and return a valid Bearer token, for tests
    that need to hit a protected endpoint without re-testing login itself."""
    response = api_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": dev_admin_password_hash},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["access_token"]


@pytest.fixture
def auth_headers(auth_token) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth_token}"}
