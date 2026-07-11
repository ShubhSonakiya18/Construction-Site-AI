"""
database/seed/sample_data.py — Seed one complete sample company with realistic data.

Creates a deterministic, reproducible dataset for local development and testing.
All UUIDs are fixed so the same records appear on every run.

What is seeded:
    1 Company  — "Apex Residential Construction LLC"
    1 User     — owner account (no password, Sprint 8 will add auth)
    3 Workers  — foreman + 2 crew members
    1 Project  — "Johnson Residence - 123 Oak Street"
    1 Site     — the physical address
    3 ProjectWorkers — assignments
    1 DailyLog — one approved framing-stage log with full child data

Idempotent: checks for existing records before inserting.

Usage:
    from database.seed.sample_data import seed_sample_data
    from database.seed.reference_data import seed_all_reference_data

    with get_session() as session:
        seed_all_reference_data(session)  # must run first
        seed_sample_data(session)

Sprint 7 note — dev-only demo login:
    This module seeds a placeholder DEV_ADMIN_ID User row with
    hashed_password=None. database/ has no dependency on app/ and must
    never import password-hashing code — see docs/BACKEND_ARCHITECTURE.md
    ("Why the database layer stays framework-independent") for the full
    rationale. The password hash is set afterward by
    app.core.dev_seed.ensure_dev_admin_password(), which is the one place
    in this codebase where the application layer reaches back into
    already-seeded data. Run `python -m app.core.dev_seed` after the normal
    seed scripts to make POST /api/v1/auth/login work locally.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models.company import Company, User
from database.models.daily_log import DailyLog
from database.models.log_items import (
    LogDelay,
    LogHazard,
    LogMaterialDelivered,
    LogMaterialRequired,
    LogMaterialUsed,
    LogSafetyIncident,
    LogTradeOnSite,
    LogWorkItem,
)
from database.models.project import Project, ProjectWorker, Site
from database.models.worker import Worker

# ── Fixed UUIDs (deterministic across runs) ───────────────────────────────────
COMPANY_ID   = uuid.UUID("aaaaaaaa-0001-4000-8000-000000000001")
OWNER_ID     = uuid.UUID("aaaaaaaa-0002-4000-8000-000000000002")
FOREMAN_ID   = uuid.UUID("aaaaaaaa-0003-4000-8000-000000000003")
WORKER_1_ID  = uuid.UUID("aaaaaaaa-0004-4000-8000-000000000004")
WORKER_2_ID  = uuid.UUID("aaaaaaaa-0005-4000-8000-000000000005")
PROJECT_ID   = uuid.UUID("aaaaaaaa-0006-4000-8000-000000000006")
SITE_ID      = uuid.UUID("aaaaaaaa-0007-4000-8000-000000000007")
DAILY_LOG_ID = uuid.UUID("aaaaaaaa-0008-4000-8000-000000000008")
DEV_ADMIN_ID = uuid.UUID("aaaaaaaa-0009-4000-8000-000000000009")


def seed_sample_data(session: Session) -> dict[str, int]:
    """Seed sample data for local development. Returns inserted-count per entity.

    Prerequisites:
        seed_all_reference_data() must have been called first so that
        trade codes referenced in log records are valid.
    """
    counts: dict[str, int] = {}

    # ── Company ───────────────────────────────────────────────────────────────
    existing_company = session.get(Company, COMPANY_ID)
    if existing_company is None:
        company = Company(
            id=COMPANY_ID,
            name="Apex Residential Construction LLC",
            slug="apex-residential",
            contact_email="info@apexresidential.example.com",
            phone="(512) 555-0100",
            address="4801 S Congress Ave, Suite 300",
            city="Austin",
            state="TX",
            zip_code="78745",
            country="USA",
            is_active=True,
            subscription_tier="professional",
        )
        session.add(company)
        session.flush()
        counts["companies"] = 1
    else:
        counts["companies"] = 0

    # ── Owner User ────────────────────────────────────────────────────────────
    existing_user = session.get(User, OWNER_ID)
    if existing_user is None:
        owner = User(
            id=OWNER_ID,
            company_id=COMPANY_ID,
            email="owner@apexresidential.example.com",
            hashed_password=None,  # Sprint 8 will set this
            first_name="Marcus",
            last_name="Apex",
            role="owner",
            is_active=True,
        )
        session.add(owner)
        session.flush()
        counts["users"] = 1
    else:
        counts["users"] = 0

    # ── Dev-only demo login placeholder (Sprint 7 — see module docstring) ─────
    # hashed_password is set afterward by app.core.dev_seed — this module
    # never imports password-hashing code (database/ has no dependency on app/).
    existing_admin = session.get(User, DEV_ADMIN_ID)
    if existing_admin is None:
        dev_admin = User(
            id=DEV_ADMIN_ID,
            company_id=COMPANY_ID,
            email="admin@example.com",
            hashed_password=None,
            first_name="Dev",
            last_name="Admin",
            role="owner",
            is_active=True,
        )
        session.add(dev_admin)
        session.flush()
        counts["dev_admin_users"] = 1
    else:
        counts["dev_admin_users"] = 0

    # ── Workers ───────────────────────────────────────────────────────────────
    workers_inserted = 0
    worker_data = [
        {
            "id": FOREMAN_ID,
            "company_id": COMPANY_ID,
            "first_name": "David",
            "last_name": "Rivera",
            "role": "foreman",
            "phone": "(512) 555-0201",
            "email": "d.rivera@apexresidential.example.com",
            "is_active": True,
        },
        {
            "id": WORKER_1_ID,
            "company_id": COMPANY_ID,
            "first_name": "James",
            "last_name": "Thompson",
            "role": "laborer",
            "phone": "(512) 555-0202",
            "is_active": True,
        },
        {
            "id": WORKER_2_ID,
            "company_id": COMPANY_ID,
            "first_name": "Maria",
            "last_name": "Gonzalez",
            "role": "laborer",
            "phone": "(512) 555-0203",
            "is_active": True,
        },
    ]
    for wd in worker_data:
        existing = session.get(Worker, wd["id"])
        if existing is None:
            session.add(Worker(**wd))
            workers_inserted += 1
    session.flush()
    counts["workers"] = workers_inserted

    # ── Project ───────────────────────────────────────────────────────────────
    existing_project = session.get(Project, PROJECT_ID)
    if existing_project is None:
        project = Project(
            id=PROJECT_ID,
            company_id=COMPANY_ID,
            name="Johnson Residence — 123 Oak Street",
            project_type="residential_single_family",
            status="active",
            client_name="Robert & Linda Johnson",
            client_contact_email="rjohnson@example.com",
            client_contact_phone="(512) 555-0300",
            contractor_company="Apex Residential Construction LLC",
            project_size_sqft=2850.0,
            project_start_date=date(2026, 3, 10),
            planned_completion_date=date(2026, 9, 15),
            contract_value_usd=425000.00,
            permit_number="2026-B-00847",
            created_by_id=OWNER_ID,
        )
        session.add(project)
        session.flush()
        counts["projects"] = 1
    else:
        counts["projects"] = 0

    # ── Site ──────────────────────────────────────────────────────────────────
    existing_site = session.get(Site, SITE_ID)
    if existing_site is None:
        site = Site(
            id=SITE_ID,
            project_id=PROJECT_ID,
            address="123 Oak Street",
            city="Austin",
            state="TX",
            zip_code="78701",
            country="USA",
            latitude=30.267153,
            longitude=-97.743061,
            is_primary=True,
            notes="Corner lot. Street parking available on Oak St and 2nd Ave.",
        )
        session.add(site)
        session.flush()
        counts["sites"] = 1
    else:
        counts["sites"] = 0

    # ── ProjectWorker assignments ─────────────────────────────────────────────
    pw_inserted = 0
    assignments = [
        {
            "project_id": PROJECT_ID,
            "worker_id": FOREMAN_ID,
            "role_on_project": "foreman",
            "start_date": date(2026, 3, 10),
            "is_active": True,
        },
        {
            "project_id": PROJECT_ID,
            "worker_id": WORKER_1_ID,
            "role_on_project": "laborer",
            "start_date": date(2026, 3, 10),
            "is_active": True,
        },
        {
            "project_id": PROJECT_ID,
            "worker_id": WORKER_2_ID,
            "role_on_project": "laborer",
            "start_date": date(2026, 3, 10),
            "is_active": True,
        },
    ]
    for asgn in assignments:
        exists = session.execute(
            select(ProjectWorker)
            .where(ProjectWorker.project_id == asgn["project_id"])
            .where(ProjectWorker.worker_id == asgn["worker_id"])
        ).scalar_one_or_none()
        if exists is None:
            session.add(ProjectWorker(**asgn))
            pw_inserted += 1
    session.flush()
    counts["project_workers"] = pw_inserted

    # ── Daily Log (one complete framing-stage log) ────────────────────────────
    existing_log = session.get(DailyLog, DAILY_LOG_ID)
    if existing_log is None:
        log = DailyLog(
            id=DAILY_LOG_ID,
            project_id=PROJECT_ID,
            site_id=SITE_ID,
            foreman_id=FOREMAN_ID,
            log_date=date(2026, 5, 14),
            log_source="voice_recording",
            review_status="approved",
            reviewed_by_id=OWNER_ID,
            reviewed_at=datetime(2026, 5, 14, 20, 30, 0, tzinfo=timezone.utc),
            current_stage="framing",
            active_stages=["framing"],
            stage_completion_percent=45.0,
            overall_project_completion_percent=28.0,
            weather={
                "morning_condition": "sunny",
                "afternoon_condition": "partly_cloudy",
                "temperature_high_celsius": 29,
                "temperature_low_celsius": 18,
                "humidity_percent": 52,
                "wind_speed_kmh": 15,
                "precipitation_mm": 0,
                "work_stopped_due_to_weather": False,
                "weather_impact_level": "none",
                "weather_notes": None,
            },
            total_workers_present=7,
            total_workers_scheduled=8,
            total_man_hours_worked=53.5,
            late_arrivals=[
                {
                    "worker_identifier": "Carlos M.",
                    "trade": "framing_carpenter",
                    "minutes_late": 25,
                    "reason": "Car trouble"
                }
            ],
            absences=[
                {
                    "worker_identifier": "Steve B.",
                    "trade": "framing_carpenter",
                    "reason": "Sick day",
                    "expected_return_date": "2026-05-15"
                }
            ],
            visitors=None,
            workforce_notes="Short one framer today but team kept pace.",
            safety_meeting_conducted=True,
            safety_meeting_duration_minutes=15,
            safety_meeting_topics=["Fall protection at second-floor deck openings", "Proper use of nail guns", "Hydration reminder — temperature reaching 29°C"],
            ppe_compliance_observed="full_compliance",
            ppe_required_today=["hard_hat", "high_vis_vest", "safety_glasses", "steel_toe_boots", "fall_protection_harness"],
            safety_notes=None,
            shortage_flags=None,
            tomorrow_plan={
                "planned_tasks": [
                    {
                        "task_description": "Complete second floor east wall framing",
                        "trade": "framing_carpenter",
                        "priority": "high",
                        "workers_needed": 4,
                        "estimated_hours": 8.0,
                        "prerequisites": ["Second floor deck OSB complete"],
                        "notes": None,
                    }
                ],
                "workers_expected": 8,
                "materials_to_order": [
                    {
                        "material_name": "2x6 SPF Studs 8ft",
                        "quantity": 120,
                        "unit": "each",
                        "supplier": "ABC Lumber",
                        "order_by_time": "By 6 AM for 7 AM delivery"
                    }
                ],
                "equipment_needed": ["Framing nail gun", "Extension cords"],
                "subcontractors_scheduled": [],
                "inspections_scheduled": [],
                "plan_notes": "Push to complete second floor framing by end of week.",
            },
            client_communication={
                "client_contacted_today": True,
                "contact_method": "phone_call",
                "topics_discussed": ["Framing progress", "Window rough opening sizes"],
                "client_concerns": [
                    {
                        "concern_description": "Client wants to add a window in the master bedroom north wall.",
                        "priority": "medium",
                        "action_required": "Review structural impact with engineer before framing north wall.",
                        "resolved": False,
                    }
                ],
                "change_orders": [],
                "communication_notes": "Client was pleased with progress. Will visit site Saturday.",
            },
            attachments=None,
            financials={
                "daily_labor_cost_usd": 2887.50,
                "daily_material_cost_usd": 1240.00,
                "daily_equipment_cost_usd": 150.00,
            },
            created_by_id=OWNER_ID,
        )
        session.add(log)
        session.flush()

        # ── Child records for the sample log ──────────────────────────────────
        session.add_all([
            LogTradeOnSite(
                daily_log_id=DAILY_LOG_ID,
                trade="framing_carpenter",
                workers_count=5,
                foreman_name="David Rivera",
                hours_worked=8.5,
            ),
            LogTradeOnSite(
                daily_log_id=DAILY_LOG_ID,
                trade="general_labor",
                workers_count=2,
                hours_worked=8.0,
            ),
            LogWorkItem(
                daily_log_id=DAILY_LOG_ID,
                task_description="Completed first floor wall framing including all exterior walls and interior bearing walls",
                trade="framing_carpenter",
                location_on_site="First floor",
                quantity_completed=1800.0,
                unit_of_measure="sq_feet",
                task_completion_percent=100.0,
            ),
            LogWorkItem(
                daily_log_id=DAILY_LOG_ID,
                task_description="Installed 3/4 inch OSB subfloor on second floor deck",
                trade="framing_carpenter",
                location_on_site="Second floor",
                quantity_completed=1400.0,
                unit_of_measure="sq_feet",
                task_completion_percent=100.0,
            ),
            LogWorkItem(
                daily_log_id=DAILY_LOG_ID,
                task_description="Began second floor south and west wall framing",
                trade="framing_carpenter",
                location_on_site="Second floor",
                quantity_completed=60.0,
                unit_of_measure="linear_feet",
                task_completion_percent=35.0,
            ),
            LogMaterialUsed(
                daily_log_id=DAILY_LOG_ID,
                material_name="2x6 SPF Studs 8ft",
                category="lumber",
                quantity_used=240.0,
                unit="each",
                unit_cost_usd=6.85,
                supplier="ABC Lumber",
            ),
            LogMaterialUsed(
                daily_log_id=DAILY_LOG_ID,
                material_name="3/4 in Tongue-and-Groove OSB Subfloor",
                category="lumber",
                quantity_used=52.0,
                unit="sheets",
                unit_cost_usd=42.00,
                supplier="ABC Lumber",
            ),
            LogMaterialDelivered(
                daily_log_id=DAILY_LOG_ID,
                material_name="LVL Beam 3.5x9.5in x 20ft",
                quantity_delivered=6.0,
                unit="each",
                supplier="ABC Lumber",
                delivery_condition="good",
                purchase_order_number="PO-2026-0412",
            ),
            LogMaterialRequired(
                daily_log_id=DAILY_LOG_ID,
                material_name="2x6 SPF Studs 8ft",
                quantity_needed=120.0,
                unit="each",
                urgency="high",
                notes="Needed for second floor east wall — order today for AM delivery",
            ),
            LogHazard(
                daily_log_id=DAILY_LOG_ID,
                hazard_type="fall_risk",
                location="Second floor deck openings",
                description="Three stairwell openings on second floor deck are currently unguarded.",
                severity="high",
                corrective_action="Install temporary covers and safety tape around all openings by end of day.",
                corrective_action_completed=True,
            ),
        ])
        session.flush()
        counts["daily_logs"] = 1
        counts["log_children"] = 10  # approximate child records inserted
    else:
        counts["daily_logs"] = 0
        counts["log_children"] = 0

    return counts
