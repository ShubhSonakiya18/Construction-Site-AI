"""
tests/test_app_dev_seed.py — Tests for app/core/dev_seed.py.

Verifies the dev-only demo user bootstrap: seeds via the existing Sprint 6
seed functions, then confirms ensure_dev_admin_password() hashes and sets
the password on the DEV_ADMIN_ID row, is idempotent, and produces a hash
that app.core.security.verify_password() accepts.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from database.base import Base
from database.models.company import User
from database.seed.reference_data import seed_all_reference_data
from database.seed.sample_data import DEV_ADMIN_ID, seed_sample_data

from app.core.security import verify_password
from database.session import reset_engine


@pytest.fixture(autouse=True)
def _reset_session_factory():
    """database.session caches a module-level _SessionFactory bound to
    whatever engine get_session() first saw. Without this reset, test 2's
    monkeypatched engine is ignored because get_session() reuses test 1's
    cached factory (and test 1's now-disposed engine)."""
    reset_engine()
    yield
    reset_engine()


@pytest.fixture
def engine():
    # StaticPool: dev_seed.ensure_dev_admin_password() opens its own
    # session via get_session(engine), a second connection from the same
    # engine. Without StaticPool, sqlite:///:memory: gives each connection
    # a separate, empty in-memory database — the second connection would
    # not see data seeded_session already committed on the first.
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
def seeded_session(engine):
    with Session(engine) as session:
        seed_all_reference_data(session)
        seed_sample_data(session)
        session.commit()
        yield session


class TestDevSeedPlaceholder:
    def test_dev_admin_seeded_with_null_password(self, seeded_session):
        """database/seed/sample_data.py seeds the row with no password —
        app/core/dev_seed.py is responsible for setting it."""
        user = seeded_session.get(User, DEV_ADMIN_ID)
        assert user is not None
        assert user.hashed_password is None
        assert user.email == "admin@example.com"
        assert user.role == "owner"


class TestEnsureDevAdminPassword:
    def test_sets_password_hash(self, engine, seeded_session, monkeypatch):
        from app.core import dev_seed

        monkeypatch.setattr(
            dev_seed, "get_engine", lambda config=None: engine
        )

        dev_seed.ensure_dev_admin_password()

        with Session(engine) as session:
            user = session.get(User, DEV_ADMIN_ID)
            assert user.hashed_password is not None
            assert verify_password("Admin@123", user.hashed_password) is True

    def test_idempotent_second_call_does_not_error(self, engine, seeded_session, monkeypatch):
        from app.core import dev_seed

        monkeypatch.setattr(
            dev_seed, "get_engine", lambda config=None: engine
        )

        dev_seed.ensure_dev_admin_password()
        with Session(engine) as session:
            first_hash = session.get(User, DEV_ADMIN_ID).hashed_password

        dev_seed.ensure_dev_admin_password()  # should be a no-op
        with Session(engine) as session:
            second_hash = session.get(User, DEV_ADMIN_ID).hashed_password

        assert first_hash == second_hash

    def test_missing_user_logs_warning_not_raise(self, engine, monkeypatch):
        """If seed_sample_data() was never run, ensure_dev_admin_password()
        must not crash — it should log and return."""
        from app.core import dev_seed

        monkeypatch.setattr(
            dev_seed, "get_engine", lambda config=None: engine
        )
        dev_seed.ensure_dev_admin_password()  # no DEV_ADMIN_ID row exists yet
