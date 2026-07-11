"""
app/core/dev_seed.py — Development-only bootstrap for the demo login account.

Why this file exists (and why the hashing does not live in database/seed/):
    database/ is Sprint 6, frozen, and framework-independent by design — it
    must be usable from any future consumer (a CLI tool, a different web
    framework, a data-migration script, Alembic itself) without dragging in
    app/'s dependencies (FastAPI, passlib, python-jose, pydantic-settings).
    Importing app.core.security from database/seed/ would invert that: the
    lower layer (database/) would depend on the higher layer (app/), which
    is backwards and makes database/ harder to reuse or test in isolation.

    See docs/BACKEND_ARCHITECTURE.md, "Why the database layer stays
    framework-independent," for the full architectural rationale and the
    migration strategy if this ever needs to generalize beyond one demo user.

What this script does:
    1. Calls the existing Sprint 6 seed functions (seed_all_reference_data,
       seed_sample_data) exactly as verify_sprint6.py and the manual setup
       docs already do — no seed logic is duplicated here.
    2. Looks up the DEV_ADMIN_ID user that seed_sample_data() just created
       with hashed_password=None.
    3. Hashes the configured dev password (via app.core.security, which is
       allowed to depend on database/ — this is app/ code) and writes it
       onto that one row.

Scope boundary (Sprint 7, NEXT_SPRINT.md §3):
    Exactly one demo user. No registration endpoint. No password reset. No
    general user-management. This script is not a template for provisioning
    real users — Sprint 8 will define that properly.

THIS ACCOUNT IS FOR LOCAL DEVELOPMENT ONLY. Do not run this script against
a production database, and never commit real credentials to .env.

Usage:
    python -m app.core.dev_seed
"""
from __future__ import annotations

import logging

from database.config import DatabaseConfig
from database.models.company import User
from database.seed.reference_data import seed_all_reference_data
from database.seed.sample_data import DEV_ADMIN_ID, seed_sample_data
from database.session import get_engine, get_session

from app.core.config import get_settings
from app.core.security import hash_password

logger = logging.getLogger(__name__)


def ensure_dev_admin_password() -> None:
    """Set the dev-only demo user's password hash, if not already set.

    Idempotent: does nothing if hashed_password is already populated (e.g.
    on a second run) or if the DEV_ADMIN_ID row does not exist yet (run the
    seed scripts first).
    """
    settings = get_settings()
    engine = get_engine(DatabaseConfig.from_env())

    with get_session(engine) as session:
        user = session.get(User, DEV_ADMIN_ID)
        if user is None:
            logger.warning(
                "Dev admin user (id=%s) not found — run seed_sample_data() first.",
                DEV_ADMIN_ID,
            )
            return
        if user.hashed_password is not None:
            logger.info("Dev admin password already set — nothing to do.")
            return

        user.email = settings.dev_seed_admin_email
        user.hashed_password = hash_password(settings.dev_seed_admin_password)
        session.flush()
        logger.info(
            "Dev admin password set for %s (id=%s). "
            "DEVELOPMENT USE ONLY — do not run against production.",
            user.email,
            user.id,
        )


def bootstrap_dev_environment() -> None:
    """Run the full Sprint 6 seed + Sprint 7 dev-login bootstrap in one call.

    Equivalent to running the manual seed steps from docs/WORKING_STATE.md
    followed by ensure_dev_admin_password().
    """
    engine = get_engine(DatabaseConfig.from_env())
    with get_session(engine) as session:
        seed_all_reference_data(session)
    with get_session(engine) as session:
        seed_sample_data(session)
    ensure_dev_admin_password()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    bootstrap_dev_environment()
