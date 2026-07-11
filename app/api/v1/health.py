"""
app/api/v1/health.py — Production health endpoints.

Four distinct endpoints, not one generic /health, because each answers a
different operational question and is polled by a different consumer:

    GET /health   -- Full diagnostic: DB reachable? Groq reachable? Returns
                     component-level detail. For humans and dashboards, not
                     hot-path polling (does real I/O: a DB query + a Groq
                     API call).

    GET /live     -- "Is the process alive and able to handle requests at
                     all?" No I/O — always returns 200 if the ASGI app is
                     running. This is what a Kubernetes livenessProbe hits:
                     if THIS fails, the orchestrator kills and restarts the
                     pod. Must never depend on the database or an external
                     API, or a transient DB blip would cause unnecessary
                     restarts.

    GET /ready    -- "Can this instance actually serve traffic right now?"
                     Checks the database connection (the one dependency
                     every endpoint needs). This is what a Kubernetes
                     readinessProbe hits: if THIS fails, the orchestrator
                     stops routing traffic to the pod but does NOT restart
                     it — the pod stays up and is re-checked, e.g. while a
                     DB failover completes.

    GET /version  -- Static build/version metadata. No I/O. Used by
                     deployment tooling to confirm which version is running
                     after a rollout, and by clients to detect a stale
                     cached response is safe to compare against.

None of these four endpoints require authentication — a load balancer or
orchestrator polling /live and /ready has no JWT to present, and /health,
/version leak no sensitive data.
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.dependencies import get_app_settings, get_db
from app.core.config import Settings
from app.schemas.envelope import APIResponse, success_response

router = APIRouter(prefix="/health", tags=["Health"])

_process_start_time = time.monotonic()


@router.get(
    "",
    response_model=APIResponse[dict],
    summary="Full diagnostic health check",
    description=(
        "Checks database connectivity and the Groq LLM engine availability. "
        "Performs real I/O — do not poll this at high frequency. For "
        "container orchestration, use /live and /ready instead."
    ),
)
def health_check(
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> APIResponse[dict]:
    components: dict[str, dict] = {}

    # ── Database ──────────────────────────────────────────────────────────────
    try:
        session.execute(text("SELECT 1"))
        components["database"] = {"status": "up"}
    except Exception as exc:  # noqa: BLE001 — health check must not raise
        components["database"] = {"status": "down", "detail": str(exc)}

    # ── Groq extraction engine ───────────────────────────────────────────────
    try:
        from extraction.engines.factory import EngineFactory

        engine = EngineFactory.create_from_config(settings.extraction_config())
        components["groq_extraction_engine"] = {
            "status": "up" if engine.is_available() else "down"
        }
    except Exception as exc:  # noqa: BLE001
        components["groq_extraction_engine"] = {"status": "down", "detail": str(exc)}

    overall_up = all(c["status"] == "up" for c in components.values())
    return success_response(
        {"status": "up" if overall_up else "degraded", "components": components},
        message="Health check completed.",
    )


@router.get(
    "/live",
    response_model=APIResponse[dict],
    summary="Liveness probe",
    description=(
        "Returns 200 if the process is running and able to handle requests. "
        "No database or external dependency check. Kubernetes: use as "
        "livenessProbe — failure triggers a pod restart."
    ),
)
def liveness() -> APIResponse[dict]:
    uptime_seconds = time.monotonic() - _process_start_time
    return success_response(
        {"status": "alive", "uptime_seconds": round(uptime_seconds, 1)},
        message="Process is alive.",
    )


@router.get(
    "/ready",
    response_model=APIResponse[dict],
    summary="Readiness probe",
    description=(
        "Returns 200 only if the database is reachable. Kubernetes: use as "
        "readinessProbe — failure stops traffic routing without restarting "
        "the pod."
    ),
)
def readiness(session: Session = Depends(get_db)) -> APIResponse[dict]:
    try:
        session.execute(text("SELECT 1"))
        db_ready = True
    except Exception:  # noqa: BLE001
        db_ready = False

    return success_response(
        {"status": "ready" if db_ready else "not_ready", "database": db_ready},
        message="Ready." if db_ready else "Not ready — database unreachable.",
    )


@router.get(
    "/version",
    response_model=APIResponse[dict],
    summary="Build/version metadata",
    description="Static metadata about the running build. No I/O.",
)
def version(settings: Settings = Depends(get_app_settings)) -> APIResponse[dict]:
    return success_response(
        {
            "app_version": settings.app_version,
            "environment": settings.environment,
            "api_version": "v1",
        },
        message="Version metadata.",
    )
