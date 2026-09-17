"""
app/tasks/alert_tasks.py — Celery Beat periodic task: proactive alert
notifications (Sprint 19).

Sprint 14's budget_variance.status and Sprint 15's safety_proactive_warnings
are both real, correct, already-computed alert conditions that were never
pushed anywhere before this sprint -- both sprints' own "Decided, not
built" sections cited "no scheduler or notification infrastructure" as the
reason to stop at a computed field. This task closes that gap using
entirely existing infrastructure: Celery Beat (ships with the already-
pinned `celery` package, see celery_app.py's beat_schedule), the real
compute_budget_variance()/safety-warning functions from Sprint 14/15
(reused unchanged, not reimplemented), and the real EmailSender (Sprint 9).

Why this iterates every active project across every company directly
(not through TenantScopedRepository's per-request scoping): this is a
background sweep, not a request on behalf of one authenticated user --
there is no "current user" to scope to. Each project's own company_id is
used to build a TenantContext for calling the existing _scoped()
repository methods (reusing their real, tested query logic) and to find
that company's real alert recipients -- the cross-tenant iteration itself
happens in this task's own loop, which is the legitimate place for it
(the same way a management command or a data migration script would
iterate across tenants), not inside the repository layer.
"""
from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from celery_app import celery_app

logger = logging.getLogger("app.tasks.alerts")


def _get_alert_recipients(session: Session, company_id) -> list[str]:
    """Every active, staff-role user's email in this company -- the same
    role set AnalyticsPanel.tsx's STAFF_ONLY_ANALYTICS_ROLES already
    gates the underlying data to (ADR-056): an alert recipient list wider
    than who can already see the data it's about would be a real
    information-disclosure mismatch, not a bigger blast radius by
    design.
    """
    from database.models.company import User

    staff_roles = (
        "owner", "admin", "project_manager", "safety_officer", "foreman",
        "system_admin",
    )
    stmt = (
        select(User.email)
        .where(User.company_id == company_id)
        .where(User.is_active.is_(True))
        .where(User.role.in_(staff_roles))
    )
    return [row[0] for row in session.execute(stmt).all()]


def _check_project_budget_alert(session: Session, project, email_sender) -> None:
    from database.repositories.daily_log import DailyLogRepository
    from database.repositories.tenant import TenantContext
    from app.services.alert_service import should_send_budget_alert, utc_now
    from app.services.cost_service import build_cost_trend, compute_budget_variance
    from database.models.alerts import ProjectAlertSent

    tenant = TenantContext(company_id=project.company_id, user_id=project.id)
    log_repo = DailyLogRepository(session)
    cost_rows = log_repo.get_daily_cost_trend_scoped(project.id, tenant=tenant)
    cost_trend = build_cost_trend(cost_rows)
    total_spend = cost_trend[-1].cumulative_spend_to_date_usd if cost_trend else 0.0
    variance = compute_budget_variance(
        contract_value_usd=(
            float(project.contract_value_usd)
            if project.contract_value_usd is not None
            else None
        ),
        total_spend_to_date_usd=total_spend,
    )

    existing = session.execute(
        select(ProjectAlertSent).where(
            ProjectAlertSent.project_id == project.id,
            ProjectAlertSent.alert_type == "budget_variance",
        )
    ).scalar_one_or_none()

    decision = should_send_budget_alert(
        current_status=variance.status,
        last_sent_status=existing.last_status_value if existing else None,
        last_sent_at=existing.last_sent_at if existing else None,
        now=utc_now(),
    )
    if not decision.should_send:
        return

    recipients = _get_alert_recipients(session, project.company_id)
    subject = f"Budget alert: {project.name} is {variance.status.replace('_', ' ')}"
    body = (
        f"Project: {project.name}\n"
        f"Status: {variance.status}\n"
        f"Spend to date: ${variance.total_spend_to_date_usd:,.2f}\n"
        f"Contract value: ${variance.contract_value_usd:,.2f}\n"
        if variance.contract_value_usd is not None
        else f"Project: {project.name}\nStatus: {variance.status}\n"
    )
    for email in recipients:
        email_sender.send(to=email, subject=subject, body=body)

    if existing is not None:
        existing.last_status_value = decision.new_status_value
        existing.last_sent_at = utc_now()
    else:
        session.add(
            ProjectAlertSent(
                project_id=project.id,
                alert_type="budget_variance",
                last_status_value=decision.new_status_value,
                last_sent_at=utc_now(),
            )
        )
    logger.info(
        "alert_tasks: sent budget_variance alert project_id=%s status=%s recipients=%d",
        project.id, variance.status, len(recipients),
    )


def _check_project_safety_alert(session: Session, project, email_sender) -> None:
    from database.repositories.daily_log import DailyLogRepository
    from database.repositories.tenant import TenantContext
    from app.services.alert_service import should_send_safety_alert, utc_now
    from app.services.safety_trend_service import compute_unresolved_hazard_warnings
    from database.models.alerts import ProjectAlertSent

    tenant = TenantContext(company_id=project.company_id, user_id=project.id)
    log_repo = DailyLogRepository(session)
    hazards_with_dates = log_repo.get_unresolved_hazards_scoped(
        project.id, tenant=tenant
    )
    warnings = compute_unresolved_hazard_warnings(
        hazards_with_dates, as_of=date.today()
    )
    has_hazards = len(warnings) > 0

    existing = session.execute(
        select(ProjectAlertSent).where(
            ProjectAlertSent.project_id == project.id,
            ProjectAlertSent.alert_type == "safety_warning",
        )
    ).scalar_one_or_none()

    decision = should_send_safety_alert(
        has_unresolved_hazards=has_hazards,
        last_sent_status=existing.last_status_value if existing else None,
        last_sent_at=existing.last_sent_at if existing else None,
        now=utc_now(),
    )
    if not decision.should_send:
        return

    recipients = _get_alert_recipients(session, project.company_id)
    subject = f"Safety alert: {project.name} has unresolved hazards"
    body = (
        f"Project: {project.name}\n"
        f"Unresolved hazards: {len(warnings)}\n"
        + "\n".join(
            f"- {w.hazard_type} ({w.severity}, open {w.days_open}d): {w.description}"
            for w in warnings
        )
    )
    for email in recipients:
        email_sender.send(to=email, subject=subject, body=body)

    if existing is not None:
        existing.last_status_value = decision.new_status_value
        existing.last_sent_at = utc_now()
    else:
        session.add(
            ProjectAlertSent(
                project_id=project.id,
                alert_type="safety_warning",
                last_status_value=decision.new_status_value,
                last_sent_at=utc_now(),
            )
        )
    logger.info(
        "alert_tasks: sent safety_warning alert project_id=%s hazard_count=%d recipients=%d",
        project.id, len(warnings), len(recipients),
    )


@celery_app.task(name="app.tasks.alert_tasks.check_project_alerts_task")
def check_project_alerts_task() -> None:
    """Celery Beat entry point — checks every active project's budget and
    safety status, sends real alert emails for whatever should fire per
    app/services/alert_service.py's dedup decision, and records what was
    sent. See celery_app.py's beat_schedule for the check interval.
    """
    from database.models.project import Project
    from database.session import get_session
    from app.services.email_sender import build_email_sender
    from app.core.config import get_settings

    settings = get_settings()
    email_sender = build_email_sender(settings)

    with get_session() as session:
        projects = (
            session.execute(
                select(Project)
                .where(Project.deleted_at.is_(None))
                .where(Project.status == "active")
            )
            .scalars()
            .all()
        )
        logger.info("alert_tasks: checking %d active project(s)", len(projects))
        for project in projects:
            try:
                _check_project_budget_alert(session, project, email_sender)
                _check_project_safety_alert(session, project, email_sender)
            except Exception:
                # One project's alert check failing must not stop the
                # sweep from checking every other project -- matching
                # safe_log_event()'s fail-open posture (ADR-040) applied
                # here at the per-project level of this task.
                logger.exception(
                    "alert_tasks: failed checking project_id=%s", project.id
                )
        session.commit()
