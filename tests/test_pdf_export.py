"""
tests/test_pdf_export.py — Sprint 10: app/services/pdf_export.py and
GET /daily-logs/{id}/outputs/{output_id}/pdf.

Unit tests for the Markdown-to-PDF renderer itself, plus API tests for
the endpoint's scoping (safety_talk only, tenant isolation, 404s).
"""
from __future__ import annotations

import uuid

import pytest

from app.services.pdf_export import _sanitize_for_pdf_font, render_markdown_pdf
from database.models.generation import GenerationOutput
from database.seed.sample_data import DAILY_LOG_ID

pytest_plugins = ["tests.conftest_api"]


class TestRenderMarkdownPdf:
    def test_produces_valid_pdf_bytes(self):
        content = "## Heading\n\n- Bullet one\n- Bullet two\n"
        pdf_bytes = render_markdown_pdf("Test Doc", content)
        assert pdf_bytes.startswith(b"%PDF-")
        assert len(pdf_bytes) > 0

    def test_handles_empty_content_without_raising(self):
        pdf_bytes = render_markdown_pdf("Empty Doc", "")
        assert pdf_bytes.startswith(b"%PDF-")

    def test_escapes_special_characters_without_raising(self):
        """A literal <, >, or & in generated content (e.g. "8 AM < 9 AM",
        "trades & subs") must not be misread as reportlab markup and
        crash or corrupt the render."""
        content = "## Section\n\nSome <tag> text with & an ampersand > here.\n"
        pdf_bytes = render_markdown_pdf("Special Chars", content)
        assert pdf_bytes.startswith(b"%PDF-")

    def test_renders_bold_inline_markup(self):
        content = "## Heading\n\n**Bold label:** normal text\n"
        pdf_bytes = render_markdown_pdf("Bold Test", content)
        assert pdf_bytes.startswith(b"%PDF-")

    def test_realistic_safety_talk_content(self):
        """The actual shape generation/prompts/safety_talk.md produces —
        REQUIRED SECTIONS headers, bold labels, bullet hazards."""
        content = (
            "## Daily Safety Toolbox Talk — 2026-05-14\n"
            "**Stage:** framing | **Presenter:** Site Safety Officer\n\n"
            "## Today's Key Hazards\n"
            "- Fall hazard from elevated work platforms (29 CFR 1926.502)\n"
            "- Nail gun kickback during framing work\n\n"
            "## Required PPE\n"
            "- Hard hats at all times\n\n"
            "## Emergency Procedures Reminder\n"
            "**Emergency Contact:** Call 911 immediately for any injury requiring medical attention.\n"
        )
        pdf_bytes = render_markdown_pdf("Safety Toolbox Talk — 2026-05-14", content)
        assert pdf_bytes.startswith(b"%PDF-")
        assert len(pdf_bytes) > 500  # a real multi-section document, not a near-empty page


class TestSanitizeForPdfFont:
    """Found via live verification: a real Groq-generated safety_talk
    (not synthetic test data) rendered with black-box glyphs (■) wherever
    the LLM used Unicode punctuation outside reportlab's default
    Helvetica/WinAnsi font's ~256-glyph coverage — U+2011 (non-breaking
    hyphen, in compound words like "second-floor") and U+2248
    (approximately-equal, "~12 kg") were the two that actually appeared
    in a real generation. See app/services/pdf_export.py's module-level
    comment for the full character map and why normalization (not a
    bundled Unicode font) was chosen."""

    def test_non_breaking_hyphen_becomes_ascii_hyphen(self):
        assert _sanitize_for_pdf_font("second‑floor") == "second-floor"

    def test_approximately_equal_becomes_tilde(self):
        assert _sanitize_for_pdf_font("≈12 kg") == "~12 kg"

    def test_smart_quotes_become_straight_quotes(self):
        assert _sanitize_for_pdf_font("‘hello’") == "'hello'"
        assert _sanitize_for_pdf_font("“world”") == '"world"'

    def test_em_and_en_dash_become_ascii_dashes(self):
        assert _sanitize_for_pdf_font("2026–05‑14") == "2026-05-14"
        assert _sanitize_for_pdf_font("Talk — today") == "Talk -- today"

    def test_plain_ascii_text_is_unchanged(self):
        plain = "Hard hats at all times (29 CFR 1926.100)."
        assert _sanitize_for_pdf_font(plain) == plain

    def test_render_does_not_produce_replacement_glyphs_for_llm_typical_punctuation(self):
        """Integration-level guard: the full render pipeline, not just
        the sanitizer function in isolation, must apply this — regression
        guard for the title parameter specifically, which bypassed
        sanitization until this bug was found and fixed."""
        content = "## Today's Key Hazards\n- second‑floor deck ≈12 kg\n"
        pdf_bytes = render_markdown_pdf("Safety Talk — Today", content)
        assert pdf_bytes.startswith(b"%PDF-")
        # The raw problem characters must not appear anywhere in the
        # object stream text-showing operators as literal bytes — a loose
        # but meaningful proxy, since reportlab encodes Paragraph text as
        # WinAnsi-mapped bytes in the content stream, and these code
        # points have no WinAnsi mapping to begin with.
        assert "‑".encode() not in pdf_bytes
        assert "≈".encode() not in pdf_bytes


@pytest.fixture
def safety_talk_output(seeded_session):
    output = GenerationOutput(
        daily_log_id=DAILY_LOG_ID,
        service_type="safety_talk",
        generation_id=uuid.uuid4(),
        content="## Daily Safety Toolbox Talk\n\n- Wear PPE\n",
        is_valid=True,
    )
    seeded_session.add(output)
    seeded_session.commit()
    return output


@pytest.fixture
def daily_report_output(seeded_session):
    output = GenerationOutput(
        daily_log_id=DAILY_LOG_ID,
        service_type="daily_report",
        generation_id=uuid.uuid4(),
        content="## Daily Report\n\nWork completed.\n",
        is_valid=True,
    )
    seeded_session.add(output)
    seeded_session.commit()
    return output


def _pdf_url(log_id, output_id) -> str:
    return f"/api/v1/daily-logs/{log_id}/outputs/{output_id}/pdf"


class TestPdfExportEndpoint:
    def test_requires_authentication(self, api_client, safety_talk_output):
        response = api_client.get(_pdf_url(DAILY_LOG_ID, safety_talk_output.id))
        assert response.status_code == 401

    def test_returns_a_real_pdf_for_safety_talk(
        self, api_client, auth_headers, safety_talk_output
    ):
        response = api_client.get(
            _pdf_url(DAILY_LOG_ID, safety_talk_output.id), headers=auth_headers
        )
        assert response.status_code == 200, response.text
        assert response.headers["content-type"] == "application/pdf"
        assert "attachment" in response.headers["content-disposition"]
        assert response.content.startswith(b"%PDF-")

    def test_rejects_non_safety_talk_document_types(
        self, api_client, auth_headers, daily_report_output
    ):
        response = api_client.get(
            _pdf_url(DAILY_LOG_ID, daily_report_output.id), headers=auth_headers
        )
        assert response.status_code == 400
        assert "safety_talk" in response.json()["message"]

    def test_nonexistent_output_returns_404(self, api_client, auth_headers):
        response = api_client.get(_pdf_url(DAILY_LOG_ID, uuid.uuid4()), headers=auth_headers)
        assert response.status_code == 404

    def test_nonexistent_log_returns_404(self, api_client, auth_headers, safety_talk_output):
        response = api_client.get(
            _pdf_url(uuid.uuid4(), safety_talk_output.id), headers=auth_headers
        )
        assert response.status_code == 404
