"""
tests/test_db_seed.py — Seed script tests.

WHY seed tests matter:
    Seed scripts run in production to populate reference data and bootstrap
    the system. A seed that silently inserts 23 trades when 25 are expected
    will cause extraction failures when the AI tries to classify a trade code
    that doesn't exist in the database.

What we verify:
    1. Exact record counts — every enum value the AI generates must exist
    2. Idempotency — running twice must not create duplicates (safe to re-run)
    3. Code values — spot-check that specific codes the AI uses are present
    4. Sample data integrity — foreign keys resolve, relationships work
"""
import uuid
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.base import Base
from database.models import (
    Trade, ConstructionStage, MaterialCategory, PPEType,
    Company, User, Worker, Project, Site, ProjectWorker, DailyLog,
    LogTradeOnSite, LogWorkItem, LogMaterialUsed, LogHazard,
)
from database.seed.reference_data import seed_all_reference_data, TRADES, CONSTRUCTION_STAGES, MATERIAL_CATEGORIES, PPE_TYPES
from database.seed.sample_data import seed_sample_data, COMPANY_ID, OWNER_ID, PROJECT_ID, SITE_ID


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
    Base.metadata.drop_all(engine)
    engine.dispose()


# ── Reference data count tests ────────────────────────────────────────────────

class TestReferenceDataSeed:
    def test_seed_inserts_correct_trade_count(self, session):
        counts = seed_all_reference_data(session)
        assert counts["trades"] == len(TRADES)

    def test_seed_inserts_correct_stage_count(self, session):
        counts = seed_all_reference_data(session)
        assert counts["construction_stages"] == len(CONSTRUCTION_STAGES)

    def test_seed_inserts_correct_material_category_count(self, session):
        counts = seed_all_reference_data(session)
        assert counts["material_categories"] == len(MATERIAL_CATEGORIES)

    def test_seed_inserts_correct_ppe_type_count(self, session):
        counts = seed_all_reference_data(session)
        assert counts["ppe_types"] == len(PPE_TYPES)

    def test_seed_is_idempotent_trades(self, session):
        seed_all_reference_data(session)
        session.commit()
        seed_all_reference_data(session)
        session.commit()

        count = session.query(Trade).count()
        assert count == len(TRADES), "Running seed twice must not create duplicates"

    def test_seed_is_idempotent_stages(self, session):
        seed_all_reference_data(session)
        session.commit()
        seed_all_reference_data(session)
        session.commit()

        count = session.query(ConstructionStage).count()
        assert count == len(CONSTRUCTION_STAGES)

    def test_seed_is_idempotent_materials(self, session):
        seed_all_reference_data(session)
        session.commit()
        seed_all_reference_data(session)
        session.commit()

        count = session.query(MaterialCategory).count()
        assert count == len(MATERIAL_CATEGORIES)

    def test_seed_is_idempotent_ppe(self, session):
        seed_all_reference_data(session)
        session.commit()
        seed_all_reference_data(session)
        session.commit()

        count = session.query(PPEType).count()
        assert count == len(PPE_TYPES)


class TestReferenceDataValues:
    """Spot-check specific codes that the AI extraction pipeline uses."""

    def test_framing_carpenter_trade_code_present(self, session):
        seed_all_reference_data(session)
        t = session.query(Trade).filter_by(code="framing_carpenter").first()
        assert t is not None, "framing_carpenter trade code must exist for AI classification"

    def test_electrician_trade_code_present(self, session):
        seed_all_reference_data(session)
        t = session.query(Trade).filter_by(code="electrician").first()
        assert t is not None

    def test_plumber_trade_code_present(self, session):
        seed_all_reference_data(session)
        t = session.query(Trade).filter_by(code="plumber").first()
        assert t is not None

    def test_foundation_stage_present(self, session):
        seed_all_reference_data(session)
        s = session.query(ConstructionStage).filter_by(code="foundation").first()
        assert s is not None

    def test_framing_stage_present(self, session):
        seed_all_reference_data(session)
        s = session.query(ConstructionStage).filter_by(code="framing").first()
        assert s is not None

    def test_concrete_material_category_present(self, session):
        seed_all_reference_data(session)
        mc = session.query(MaterialCategory).filter_by(code="concrete").first()
        assert mc is not None

    def test_hard_hat_ppe_type_present(self, session):
        seed_all_reference_data(session)
        ppe = session.query(PPEType).filter_by(code="hard_hat").first()
        assert ppe is not None

    def test_all_trades_have_display_names(self, session):
        seed_all_reference_data(session)
        trades = session.query(Trade).all()
        for t in trades:
            assert t.display_name, f"Trade {t.code} must have a display_name"

    def test_construction_stages_have_sequence_order(self, session):
        seed_all_reference_data(session)
        stages = session.query(ConstructionStage).all()
        orders = [s.sequence_order for s in stages]
        # All orders must be positive integers
        assert all(o > 0 for o in orders)
        # Orders must be unique
        assert len(set(orders)) == len(orders), "sequence_order values must be unique"

    def test_all_trades_are_active_by_default(self, session):
        seed_all_reference_data(session)
        inactive = session.query(Trade).filter_by(is_active=False).count()
        assert inactive == 0, "All seeded trades should be active"


# ── Sample data tests ─────────────────────────────────────────────────────────

class TestSampleDataSeed:
    def test_sample_data_creates_company(self, session):
        seed_all_reference_data(session)
        seed_sample_data(session)

        company = session.get(Company, COMPANY_ID)
        assert company is not None
        assert company.slug == "apex-residential"

    def test_sample_data_creates_user(self, session):
        seed_all_reference_data(session)
        seed_sample_data(session)

        user = session.get(User, OWNER_ID)
        assert user is not None
        assert user.company_id == COMPANY_ID

    def test_sample_data_creates_project(self, session):
        seed_all_reference_data(session)
        seed_sample_data(session)

        project = session.get(Project, PROJECT_ID)
        assert project is not None
        assert project.company_id == COMPANY_ID

    def test_sample_data_creates_site(self, session):
        seed_all_reference_data(session)
        seed_sample_data(session)

        site = session.get(Site, SITE_ID)
        assert site is not None
        assert site.project_id == PROJECT_ID
        assert site.is_primary is True

    def test_sample_data_creates_workers(self, session):
        seed_all_reference_data(session)
        seed_sample_data(session)

        workers = session.query(Worker).filter_by(company_id=COMPANY_ID).all()
        assert len(workers) >= 3

    def test_sample_data_assigns_workers_to_project(self, session):
        seed_all_reference_data(session)
        seed_sample_data(session)

        assignments = session.query(ProjectWorker).filter_by(project_id=PROJECT_ID).all()
        assert len(assignments) >= 3

    def test_sample_data_creates_approved_daily_log(self, session):
        seed_all_reference_data(session)
        seed_sample_data(session)

        logs = session.query(DailyLog).filter_by(project_id=PROJECT_ID).all()
        assert len(logs) >= 1

        approved = [l for l in logs if l.review_status == "approved"]
        assert len(approved) >= 1

    def test_sample_daily_log_has_child_records(self, session):
        seed_all_reference_data(session)
        seed_sample_data(session)

        log = session.query(DailyLog).filter_by(project_id=PROJECT_ID, review_status="approved").first()
        assert log is not None

        trades = session.query(LogTradeOnSite).filter_by(daily_log_id=log.id).all()
        assert len(trades) >= 1

        work_items = session.query(LogWorkItem).filter_by(daily_log_id=log.id).all()
        assert len(work_items) >= 1

    def test_sample_data_is_idempotent(self, session):
        seed_all_reference_data(session)
        seed_sample_data(session)
        session.commit()

        # Run again — must not raise, must not duplicate
        seed_all_reference_data(session)
        seed_sample_data(session)
        session.commit()

        company_count = session.query(Company).filter_by(id=COMPANY_ID).count()
        assert company_count == 1, "Idempotent seed must not create duplicate company"

        project_count = session.query(Project).filter_by(id=PROJECT_ID).count()
        assert project_count == 1, "Idempotent seed must not create duplicate project"

    def test_sample_data_fk_integrity(self, session):
        """Verify that all FKs in sample data resolve to actual rows."""
        seed_all_reference_data(session)
        seed_sample_data(session)

        log = session.query(DailyLog).filter_by(project_id=PROJECT_ID).first()
        if log and log.foreman_id:
            foreman = session.get(Worker, log.foreman_id)
            assert foreman is not None, "foreman_id must reference a real worker"

        workers = session.query(Worker).filter_by(company_id=COMPANY_ID).all()
        for w in workers:
            assert session.get(Company, w.company_id) is not None
            if w.trade_id:
                assert session.get(Trade, w.trade_id) is not None

    def test_seed_return_value_is_dict(self, session):
        seed_all_reference_data(session)
        result = seed_sample_data(session)
        assert isinstance(result, dict)
        assert "company" in result or result is not None


# ── Combined seed integration test ────────────────────────────────────────────

class TestSeedIntegration:
    def test_full_seed_pipeline(self, session):
        """Run both seeds end-to-end and verify the system is ready for use."""
        ref_counts = seed_all_reference_data(session)
        session.commit()

        sample_result = seed_sample_data(session)
        session.commit()

        # Reference data exists
        assert session.query(Trade).count() > 0
        assert session.query(ConstructionStage).count() > 0

        # Company hierarchy exists
        assert session.query(Company).count() >= 1
        assert session.query(User).count() >= 1
        assert session.query(Project).count() >= 1
        assert session.query(DailyLog).count() >= 1
