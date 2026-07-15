"""tests/test_multi_tenant_isolation.py — Cross-tenant access denial tests.

Sprint 8, Subsystem 3 (Multi-Tenancy Scoping). Proves that an authenticated
user at Company A cannot read, list, or write Company B's resources — the
gap docs/ROADMAP.md named explicitly: "No endpoint should rely on
client-supplied company IDs." See database/repositories/tenant.py for the
enforcement mechanism these tests exercise (TenantScopedRepository,
TenantContext) and app/core/permissions.py for the system_admin bypass
tested separately below.

The seeded sample company (database/seed/sample_data.py, COMPANY_ID) is
"Company A" throughout. A second company, its own project, and its own
daily log are built directly in fixtures here as "Company B" — the seed
module only ships one company by design.
"""
from __future__ import annotations

import uuid
from datetime import date

from app.core.security import create_access_token
from database.seed.sample_data import COMPANY_ID, DAILY_LOG_ID, PROJECT_ID

pytest_plugins = ["tests.conftest_api"]


def _make_user_and_token(seeded_session, test_settings, *, company_id, role: str, email: str):
    from database.models.company import User

    user = User(
        company_id=company_id,
        email=email,
        first_name="Tenant",
        last_name="Test",
        role=role,
        is_active=True,
    )
    seeded_session.add(user)
    seeded_session.flush()
    seeded_session.commit()

    token = create_access_token(
        subject=str(user.id),
        secret_key=test_settings.jwt_secret_key,
        extra_claims={"company_id": str(company_id), "role": role, "email": email},
    )
    return user, token


def _make_company_b_with_project_and_log(seeded_session):
    """Build a fully separate company, project, and approved daily log —
    Company B, isolated from the seeded Company A (COMPANY_ID)."""
    from database.models.company import Company
    from database.models.daily_log import DailyLog
    from database.models.project import Project

    company_b = Company(name="Company B Construction", slug="company-b-construction")
    seeded_session.add(company_b)
    seeded_session.flush()

    project_b = Project(
        company_id=company_b.id, name="Company B Project", status="active"
    )
    seeded_session.add(project_b)
    seeded_session.flush()

    log_b = DailyLog(
        project_id=project_b.id,
        log_date=date(2026, 7, 1),
        current_stage="framing",
        total_workers_present=4,
        review_status="draft",
    )
    seeded_session.add(log_b)
    seeded_session.flush()
    seeded_session.commit()

    return company_b, project_b, log_b


class TestDailyLogCrossTenantDenial:
    def test_company_a_owner_cannot_read_company_b_log(self, api_client, seeded_session, test_settings):
        _company_b, _project_b, log_b = _make_company_b_with_project_and_log(seeded_session)
        _user, token = _make_user_and_token(
            seeded_session, test_settings, company_id=COMPANY_ID, role="owner",
            email="companya-owner@example.com",
        )
        response = api_client.get(
            f"/api/v1/daily-logs/{log_b.id}", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 404

    def test_company_a_owner_can_read_own_companys_log(self, api_client, seeded_session, test_settings):
        """Sanity check: the fix doesn't over-block same-tenant access."""
        _user, token = _make_user_and_token(
            seeded_session, test_settings, company_id=COMPANY_ID, role="owner",
            email="companya-owner-2@example.com",
        )
        response = api_client.get(
            f"/api/v1/daily-logs/{DAILY_LOG_ID}", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200

    def test_company_a_cannot_submit_company_bs_log(self, api_client, seeded_session, test_settings):
        _company_b, _project_b, log_b = _make_company_b_with_project_and_log(seeded_session)
        _user, token = _make_user_and_token(
            seeded_session, test_settings, company_id=COMPANY_ID, role="foreman",
            email="companya-foreman@example.com",
        )
        response = api_client.post(
            f"/api/v1/daily-logs/{log_b.id}/submit",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404

    def test_company_a_cannot_approve_company_bs_log(self, api_client, seeded_session, test_settings):
        _company_b, _project_b, log_b = _make_company_b_with_project_and_log(seeded_session)
        _user, token = _make_user_and_token(
            seeded_session, test_settings, company_id=COMPANY_ID, role="owner",
            email="companya-owner-3@example.com",
        )
        response = api_client.post(
            f"/api/v1/daily-logs/{log_b.id}/approve",
            json={"notes": "cross-tenant attempt"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404

    def test_company_a_cannot_trigger_generation_on_company_bs_log(
        self, api_client, seeded_session, test_settings
    ):
        _company_b, _project_b, log_b = _make_company_b_with_project_and_log(seeded_session)
        _user, token = _make_user_and_token(
            seeded_session, test_settings, company_id=COMPANY_ID, role="owner",
            email="companya-owner-4@example.com",
        )
        response = api_client.post(
            f"/api/v1/daily-logs/{log_b.id}/generate",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404

    def test_company_a_cannot_list_company_bs_generation_outputs(
        self, api_client, seeded_session, test_settings
    ):
        _company_b, _project_b, log_b = _make_company_b_with_project_and_log(seeded_session)
        _user, token = _make_user_and_token(
            seeded_session, test_settings, company_id=COMPANY_ID, role="owner",
            email="companya-owner-5@example.com",
        )
        response = api_client.get(
            f"/api/v1/daily-logs/{log_b.id}/outputs",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404


class TestProjectCrossTenantDenial:
    def test_company_a_cannot_list_company_bs_project_logs(self, api_client, seeded_session, test_settings):
        _company_b, project_b, _log_b = _make_company_b_with_project_and_log(seeded_session)
        _user, token = _make_user_and_token(
            seeded_session, test_settings, company_id=COMPANY_ID, role="owner",
            email="companya-owner-6@example.com",
        )
        response = api_client.get(
            f"/api/v1/projects/{project_b.id}/daily-logs",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404

    def test_company_a_can_list_own_project_logs(self, api_client, seeded_session, test_settings):
        """Sanity check against over-blocking."""
        _user, token = _make_user_and_token(
            seeded_session, test_settings, company_id=COMPANY_ID, role="owner",
            email="companya-owner-7@example.com",
        )
        response = api_client.get(
            f"/api/v1/projects/{PROJECT_ID}/daily-logs",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200


class TestAudioUploadCrossTenantDenial:
    def test_cannot_upload_audio_against_another_companys_project(
        self, api_client, seeded_session, test_settings
    ):
        """The Sprint 7/8 project_id-existence pre-check (app/api/v1/audio.py)
        must be tenant-scoped — otherwise a real cross-tenant project_id
        would pass the 'exists' check and let a caller attach a recording
        to a project outside their company."""
        import io

        _company_b, project_b, _log_b = _make_company_b_with_project_and_log(seeded_session)
        _user, token = _make_user_and_token(
            seeded_session, test_settings, company_id=COMPANY_ID, role="foreman",
            email="companya-foreman-2@example.com",
        )
        response = api_client.post(
            "/api/v1/audio/upload",
            files={"file": ("recording.wav", io.BytesIO(b"RIFF____WAVEfmt "), "audio/wav")},
            data={"project_id": str(project_b.id)},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404

    def test_can_upload_audio_against_own_companys_project(self, api_client, seeded_session, test_settings):
        """Sanity check against over-blocking."""
        import io

        _user, token = _make_user_and_token(
            seeded_session, test_settings, company_id=COMPANY_ID, role="foreman",
            email="companya-foreman-3@example.com",
        )
        response = api_client.post(
            "/api/v1/audio/upload",
            files={"file": ("recording.wav", io.BytesIO(b"RIFF____WAVEfmt "), "audio/wav")},
            data={"project_id": str(PROJECT_ID)},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 202


class TestAudioStatusCrossTenantDenial:
    def test_company_a_cannot_poll_company_bs_audio_status(self, api_client, seeded_session, test_settings):
        from database.models.audio import AudioFile

        _company_b, project_b, _log_b = _make_company_b_with_project_and_log(seeded_session)
        audio_b = AudioFile(
            project_id=project_b.id,
            original_filename="companyb.wav",
            file_path="/fake/companyb.wav",
            processing_status="pending",
        )
        seeded_session.add(audio_b)
        seeded_session.flush()
        seeded_session.commit()

        _user, token = _make_user_and_token(
            seeded_session, test_settings, company_id=COMPANY_ID, role="owner",
            email="companya-owner-8@example.com",
        )
        response = api_client.get(
            f"/api/v1/audio/{audio_b.id}/status",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404

    def test_uploader_can_poll_own_unassigned_audio_status(self, api_client, seeded_session, test_settings):
        """An AudioFile with project_id=None (uploaded before project
        assignment) has no company to scope against — the uploader
        themself must still be able to poll it. See
        AudioRepository.get_by_id_scoped()'s docstring."""
        from database.models.audio import AudioFile

        user, token = _make_user_and_token(
            seeded_session, test_settings, company_id=COMPANY_ID, role="foreman",
            email="companya-foreman-4@example.com",
        )
        audio_unassigned = AudioFile(
            project_id=None,
            uploaded_by_id=user.id,
            original_filename="unassigned.wav",
            file_path="/fake/unassigned.wav",
            processing_status="pending",
        )
        seeded_session.add(audio_unassigned)
        seeded_session.flush()
        seeded_session.commit()

        response = api_client.get(
            f"/api/v1/audio/{audio_unassigned.id}/status",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200

    def test_other_user_cannot_poll_someone_elses_unassigned_audio(
        self, api_client, seeded_session, test_settings
    ):
        """The uploader-only fallback for project_id=None must not become
        a company-wide free-for-all — a different user, even same
        company, cannot see it."""
        from database.models.audio import AudioFile

        uploader, _uploader_token = _make_user_and_token(
            seeded_session, test_settings, company_id=COMPANY_ID, role="foreman",
            email="uploader@example.com",
        )
        audio_unassigned = AudioFile(
            project_id=None,
            uploaded_by_id=uploader.id,
            original_filename="unassigned2.wav",
            file_path="/fake/unassigned2.wav",
            processing_status="pending",
        )
        seeded_session.add(audio_unassigned)
        seeded_session.flush()
        seeded_session.commit()

        _other_user, other_token = _make_user_and_token(
            seeded_session, test_settings, company_id=COMPANY_ID, role="owner",
            email="not-the-uploader@example.com",
        )
        response = api_client.get(
            f"/api/v1/audio/{audio_unassigned.id}/status",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        assert response.status_code == 404


class TestSystemAdminCrossTenantBypass:
    def test_system_admin_get_by_id_cross_tenant_returns_resource_from_any_company(
        self, seeded_session
    ):
        """Unit-level check of the repository bypass method itself —
        no HTTP route currently exposes this (Subsystem 3 wires the
        repository primitive; a dedicated system_admin API surface is
        out of scope here and deferred to a future subsystem/sprint).
        Confirms the bypass actually works and is a genuinely different
        method, not a disguised company_id=None."""
        from database.repositories.project import ProjectRepository
        from database.repositories.tenant import TenantContext

        _company_b, project_b, _log_b = _make_company_b_with_project_and_log(seeded_session)

        # A TenantContext whose company_id is Company A, requesting a
        # Company B project via the explicit cross-tenant method.
        admin_tenant = TenantContext(company_id=COMPANY_ID, user_id=uuid.uuid4())
        repo = ProjectRepository(seeded_session)

        normal_result = repo.get_by_id_scoped(project_b.id, tenant=admin_tenant)
        assert normal_result is None  # normal scoped method still blocks it

        bypass_result = repo.get_by_id_cross_tenant(
            project_b.id, tenant=admin_tenant, request_id="test-request-id"
        )
        assert bypass_result is not None
        assert bypass_result.id == project_b.id

    def test_system_admin_bypass_writes_an_audit_log_entry(self, seeded_session):
        """Every cross-tenant bypass call must produce an AuditLog row —
        see database/repositories/tenant.py:_audit_cross_tenant_access()."""
        from database.repositories.generation import AuditLogRepository
        from database.repositories.project import ProjectRepository
        from database.repositories.tenant import TenantContext

        _company_b, project_b, _log_b = _make_company_b_with_project_and_log(seeded_session)
        admin_tenant = TenantContext(company_id=COMPANY_ID, user_id=uuid.uuid4())

        before_count = len(
            AuditLogRepository(seeded_session).list_for_entity("project", project_b.id)
        )
        ProjectRepository(seeded_session).get_by_id_cross_tenant(
            project_b.id, tenant=admin_tenant, request_id="test-request-id-2"
        )
        after = AuditLogRepository(seeded_session).list_for_entity("project", project_b.id)

        assert len(after) == before_count + 1
        entry = after[0]
        assert entry.event_type == "system_admin.cross_tenant_access"
        assert entry.actor_id == admin_tenant.user_id
        assert entry.company_id == project_b.company_id
        assert entry.success is True
        # Sprint 8, Subsystem 6: request_id moved from event_metadata to a
        # first-class column — see database/models/generation.py AuditLog
        # class docstring for why structured columns were introduced.
        assert entry.request_id == "test-request-id-2"
        assert entry.event_metadata["action"] == "get_by_id_cross_tenant"
