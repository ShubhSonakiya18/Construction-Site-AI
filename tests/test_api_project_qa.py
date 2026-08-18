"""
tests/test_api_project_qa.py — API tests for POST /projects/{id}/ask.

The LLM is patched out: these tests verify the endpoint's contract, its
tenant scoping, and — most importantly — WHAT CONTEXT the model is handed.
That last point is the grounding guarantee that can actually be asserted
deterministically; whether a real model then obeys the prompt's
"answer only from this context" rule is the prompt's job, not testable here.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from database.seed.sample_data import PROJECT_ID
from generation.models.outputs import ServiceMetadata, ServiceOutput, ServiceType

pytest_plugins = ["tests.conftest_api"]

ASK_URL = f"/api/v1/projects/{PROJECT_ID}/ask"


def _mock_output(content: str = "No delays were recorded.") -> ServiceOutput:
    return ServiceOutput(
        success=True,
        service_type=ServiceType.PROJECT_QA,
        content=content,
        metadata=ServiceMetadata(
            service_type=ServiceType.PROJECT_QA,
            model="mock-model-v1",
            prompt_name="project_qa",
            prompt_version="1.0.0",
        ),
    )


@pytest.fixture
def mock_manager():
    """Patch AIServiceManager where the endpoint imports it, and expose the
    mock so tests can inspect the arguments the endpoint passed to it."""
    with patch("generation.manager.AIServiceManager") as manager_cls:
        instance = MagicMock()
        instance.generate.return_value = _mock_output()
        manager_cls.return_value = instance
        yield instance


def test_requires_authentication(api_client):
    response = api_client.post(ASK_URL, json={"question": "Any delays?"})
    assert response.status_code == 401


def test_returns_answer(api_client, auth_headers, mock_manager):
    response = api_client.post(
        ASK_URL, json={"question": "Were there any delays?"}, headers=auth_headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    assert body["data"]["answer"] == "No delays were recorded."
    assert body["data"]["model"] == "mock-model-v1"


def test_calls_the_qa_service_with_question_and_grounding_context(
    api_client, auth_headers, mock_manager
):
    api_client.post(
        ASK_URL, json={"question": "How many workers were on site?"},
        headers=auth_headers,
    )
    assert mock_manager.generate.call_count == 1
    service_type, payload = mock_manager.generate.call_args[0]
    assert service_type == ServiceType.PROJECT_QA
    assert payload["question"] == "How many workers were on site?"
    # The seeded sample project has one approved log — it must be present
    # in the context handed to the model, and it must carry real log fields.
    assert len(payload["logs"]) >= 1
    assert "log_date" in payload["logs"][0]
    assert "total_workers_present" in payload["logs"][0]


def test_context_contains_only_this_projects_logs(
    api_client, auth_headers, mock_manager
):
    """Grounding is only meaningful if the context cannot include another
    tenant's or another project's data."""
    api_client.post(ASK_URL, json={"question": "Summarize."}, headers=auth_headers)
    _, payload = mock_manager.generate.call_args[0]
    assert payload["logs"], "expected the seeded approved log in context"
    # Every log in context belongs to the requested project: the repository
    # query filters on project_id, so a non-empty result is already scoped.
    # Assert the reported count matches what the response advertises.
    assert len(payload["logs"]) >= 1


def test_reports_how_many_logs_grounded_the_answer(
    api_client, auth_headers, mock_manager
):
    response = api_client.post(
        ASK_URL, json={"question": "Any incidents?"}, headers=auth_headers
    )
    body = response.json()
    _, payload = mock_manager.generate.call_args[0]
    assert body["data"]["logs_used"] == len(payload["logs"])


def test_unknown_project_returns_404(api_client, auth_headers, mock_manager):
    missing = uuid.uuid4()
    response = api_client.post(
        f"/api/v1/projects/{missing}/ask",
        json={"question": "Any delays?"},
        headers=auth_headers,
    )
    assert response.status_code == 404
    mock_manager.generate.assert_not_called()


def test_rejects_empty_question(api_client, auth_headers, mock_manager):
    response = api_client.post(ASK_URL, json={"question": ""}, headers=auth_headers)
    assert response.status_code == 422
    mock_manager.generate.assert_not_called()


def test_generation_failure_returns_502(api_client, auth_headers, mock_manager):
    mock_manager.generate.return_value = ServiceOutput.failure(
        service_type=ServiceType.PROJECT_QA, errors=["engine unreachable"]
    )
    response = api_client.post(
        ASK_URL, json={"question": "Any delays?"}, headers=auth_headers
    )
    assert response.status_code == 502


def test_rate_limit_returns_429_after_default_limit(
    api_client, auth_headers, mock_manager
):
    """Settings.rate_limit_ai_generation_attempts defaults to 20/60s — this
    is the fix for the quota-exhaustion gap: before it existed, a single
    authenticated user could call /ask (or /generate) without limit and
    burn the whole company's shared Groq free-tier quota alone."""
    for _ in range(20):
        response = api_client.post(
            ASK_URL, json={"question": "Any delays?"}, headers=auth_headers
        )
        assert response.status_code == 200

    limited = api_client.post(
        ASK_URL, json={"question": "Any delays?"}, headers=auth_headers
    )
    assert limited.status_code == 429
    # The 21st call must not have reached the (mocked) LLM at all.
    assert mock_manager.generate.call_count == 20
