"""
tests/test_content_validator.py — Unit tests for AI output content validation.

Tests every check in ContentValidator: empty, length, required phrases,
placeholder detection, duplicate sentences, and markdown structure.
No LLM calls, no file I/O.
"""
from __future__ import annotations

import pytest

from generation.models.outputs import ServiceType
from generation.validators.content_validator import ContentValidationResult, ContentValidator


@pytest.fixture()
def validator():
    return ContentValidator()


# ── Helper: build text that passes all checks for a given service type ────────

VALID_DAILY_REPORT = (
    "## Daily Site Report — 2024-03-15\n\n"
    "## Work Completed\n\n"
    "Exterior wall framing on the north and east elevations is complete. "
    "The crew installed 120 linear feet of 2×6 studs at 16 inches on center.\n\n"
    "## Workforce Summary\n\n"
    "Eight workers were on site: four carpenters, two laborers, and two electricians.\n\n"
    "## Weather Conditions\n\n"
    "Clear and sunny, 72°F, light wind at 5 mph. No weather impact on work.\n\n"
    "## Delays and Issues\n\nNo delays reported.\n\n"
    "## Safety Summary\n\nFull PPE compliance. No incidents.\n\n"
    "## Tomorrow's Plan\n\nComplete south and west wall framing."
)

VALID_CUSTOMER_UPDATE = (
    "Subject: Project Update — March 15, 2024\n\n"
    "Hi there,\n\n"
    "Great progress on your home today! The crew finished framing the north and east walls, "
    "which means you can now see the full shape of your future home taking form. "
    "Everything is on schedule and the team is doing excellent work.\n\n"
    "Tomorrow they will complete the remaining walls and the structure will be fully framed "
    "by the end of the week. It is exciting to see how quickly things are moving.\n\n"
    "We will keep you updated as each milestone is reached. Feel free to visit the site "
    "during working hours if you would like to see the progress in person.\n\n"
    "Best regards,\n"
    "Your Construction Team"
)

VALID_SAFETY_TALK = (
    "## Daily Safety Toolbox Talk — 2024-03-15\n\n"
    "**Stage:** framing | **Presenter:** Site Safety Officer\n\n"
    "## Today's Key Hazards\n\n"
    "- Fall hazard from elevated platforms (29 CFR 1926.502)\n"
    "- Struck-by hazard from overhead work\n"
    "- Hand and finger injuries from framing nailers\n\n"
    "## Required PPE\n\n"
    "- Hard hat at all times (29 CFR 1926.100)\n"
    "- Safety glasses or face shield\n"
    "- Cut-resistant gloves when handling lumber\n"
    "- Steel-toed boots\n\n"
    "## Safety Reminders\n\n"
    "- Always secure temporary guardrails before working above 6 feet.\n"
    "- Inspect all pneumatic nailers before first use.\n"
    "- Keep the work area clear of scrap lumber to prevent trips.\n\n"
    "## Tool and Equipment Inspection Checklist\n\n"
    "- Check nailer hoses for cracks or wear.\n"
    "- Inspect ladder feet for secure placement.\n\n"
    "## Emergency Procedures Reminder\n\n"
    "**Emergency Contact:** Call 911 immediately for any injury requiring medical attention.\n"
    "**Assembly Point:** Front of property.\n\n"
    "## Quick Quiz\n\n"
    "Q1: What height requires fall protection?\nA: 6 feet or more above a lower level.\n"
    "Q2: When should you inspect your tools?\nA: Before every use.\n"
    "Q3: Where is the site assembly point?\nA: Front of property."
)

VALID_MATERIAL_REMINDER = (
    "## Material Procurement Reminder — 2024-03-15\n\n"
    "**Stage:** framing | **Prepared for:** Site Foreman\n\n"
    "## CRITICAL — Order Immediately\n\n"
    "None — no critical shortages reported.\n\n"
    "## HIGH PRIORITY — Order Today\n\n"
    "- 2×4 lumber studs (200 units) — needed for south wall framing tomorrow. Priority: HIGH. Source TBD.\n\n"
    "## MEDIUM PRIORITY — Order This Week\n\n"
    "- Construction screws (box of 500) — current stock running low.\n\n"
    "## LOW PRIORITY — Plan Ahead\n\n"
    "None.\n\n"
    "## Delivery Notes\n\n"
    "No special delivery notes."
)


# ── Empty content ──────────────────────────────────────────────────────────────

class TestEmptyContent:
    def test_empty_string_fails(self, validator):
        result = validator.validate("", ServiceType.DAILY_REPORT)
        assert result.passed is False
        assert any("empty" in e.lower() for e in result.errors)

    def test_whitespace_only_fails(self, validator):
        result = validator.validate("   \n\t  ", ServiceType.DAILY_REPORT)
        assert result.passed is False

    def test_empty_returns_early_without_further_checks(self, validator):
        result = validator.validate("", ServiceType.DAILY_REPORT)
        # Should only have one error about emptiness, not phantom section errors
        assert len(result.errors) == 1


# ── Length checks ──────────────────────────────────────────────────────────────

class TestLengthChecks:
    def test_too_short_daily_report_fails(self, validator):
        short = "## Work Completed\nDone.\n\n## Workforce\nFive.\n\n## Weather\nSunny."
        # This is under 300 chars
        assert len(short) < 300
        result = validator.validate(short, ServiceType.DAILY_REPORT)
        assert result.passed is False
        assert any("short" in e.lower() for e in result.errors)

    def test_too_short_customer_update_fails(self, validator):
        short = "Subject: Update\nHi.\n\nBest regards,\nYour Construction Team"
        assert len(short) < 100
        result = validator.validate(short, ServiceType.CUSTOMER_UPDATE)
        assert result.passed is False

    def test_sufficient_length_passes_length_check(self, validator):
        result = validator.validate(VALID_DAILY_REPORT, ServiceType.DAILY_REPORT)
        # Should not have length errors (may have other errors)
        length_errors = [e for e in result.errors if "short" in e.lower() or "long" in e.lower()]
        assert length_errors == []


# ── Required phrases ───────────────────────────────────────────────────────────

class TestRequiredPhrases:
    def test_daily_report_missing_work_completed(self, validator):
        content = "## Daily Report\n\n" + "x" * 400 + "\n\n## Workforce\n\nFive workers.\n\n## Weather\n\nSunny."
        result = validator.validate(content, ServiceType.DAILY_REPORT)
        missing = [e for e in result.errors if "Work Completed" in e]
        assert missing, f"Expected 'Work Completed' error, got: {result.errors}"

    def test_daily_report_missing_workforce(self, validator):
        content = "## Work Completed\n\n" + "x" * 400 + "\n\n## Weather\n\nSunny."
        result = validator.validate(content, ServiceType.DAILY_REPORT)
        missing = [e for e in result.errors if "Workforce" in e]
        assert missing

    def test_customer_update_missing_subject(self, validator):
        content = "Hi there,\n\nGood progress today. Best regards,\nYour Construction Team\n" + "x" * 100
        result = validator.validate(content, ServiceType.CUSTOMER_UPDATE)
        missing = [e for e in result.errors if "Subject:" in e]
        assert missing

    def test_customer_update_missing_sign_off(self, validator):
        content = "Subject: Update\n\nGood progress. " + "x" * 100
        result = validator.validate(content, ServiceType.CUSTOMER_UPDATE)
        missing = [e for e in result.errors if "Construction Team" in e]
        assert missing

    def test_safety_talk_missing_ppe(self, validator):
        content = "## Safety Talk\n\n" + "x" * 300 + "\n\nSafety first. Emergency: call 911"
        result = validator.validate(content, ServiceType.SAFETY_TALK)
        missing = [e for e in result.errors if "PPE" in e]
        assert missing

    def test_all_valid_outputs_pass_required_phrases(self, validator):
        cases = [
            (VALID_DAILY_REPORT, ServiceType.DAILY_REPORT),
            (VALID_CUSTOMER_UPDATE, ServiceType.CUSTOMER_UPDATE),
            (VALID_SAFETY_TALK, ServiceType.SAFETY_TALK),
            (VALID_MATERIAL_REMINDER, ServiceType.MATERIAL_REMINDER),
        ]
        for content, stype in cases:
            result = validator.validate(content, stype)
            phrase_errors = [
                e for e in result.errors
                if "missing" in e.lower() or "required" in e.lower()
            ]
            assert phrase_errors == [], f"{stype.value}: {phrase_errors}"


# ── Placeholder detection ──────────────────────────────────────────────────────

class TestPlaceholderDetection:
    def test_curly_brace_placeholder_fails(self, validator):
        content = VALID_DAILY_REPORT.replace("2024-03-15", "{{log_date}}")
        result = validator.validate(content, ServiceType.DAILY_REPORT)
        placeholder_errors = [e for e in result.errors if "placeholder" in e.lower()]
        assert placeholder_errors

    def test_unfilled_date_from_prompt_fails(self, validator):
        content = VALID_DAILY_REPORT.replace("2024-03-15", "[DATE FROM LOG]")
        result = validator.validate(content, ServiceType.DAILY_REPORT)
        placeholder_errors = [e for e in result.errors if "placeholder" in e.lower()]
        assert placeholder_errors

    def test_bracket_placeholder_fails(self, validator):
        content = "## Report\n\nWork Completed today. Project: [INSERT project name here].\n" + "x" * 350 + "\nWeather sunny\nWorkforce 5 workers."
        result = validator.validate(content, ServiceType.DAILY_REPORT)
        placeholder_errors = [e for e in result.errors if "placeholder" in e.lower()]
        assert placeholder_errors

    def test_clean_content_has_no_placeholder_errors(self, validator):
        result = validator.validate(VALID_DAILY_REPORT, ServiceType.DAILY_REPORT)
        placeholder_errors = [e for e in result.errors if "placeholder" in e.lower()]
        assert placeholder_errors == []


# ── Duplicate sentence detection ───────────────────────────────────────────────

class TestDuplicateSentences:
    def test_repeated_long_sentence_produces_warning(self, validator):
        sentence = "The crew completed the north wall framing and all structural elements are in place"
        content = VALID_DAILY_REPORT + f"\n\n{sentence}. {sentence}."
        result = validator.validate(content, ServiceType.DAILY_REPORT)
        dup_warnings = [w for w in result.warnings if "duplicate" in w.lower() or "duplicat" in w.lower()]
        assert dup_warnings

    def test_short_repeated_phrases_do_not_trigger_duplicate_check(self, validator):
        # Short strings (< 25 chars) should not be checked for duplicates
        content = VALID_DAILY_REPORT + "\n\nNone. None. None."
        result = validator.validate(content, ServiceType.DAILY_REPORT)
        dup_warnings = [w for w in result.warnings if "duplicate" in w.lower()]
        assert dup_warnings == []


# ── Markdown structure ─────────────────────────────────────────────────────────

class TestMarkdownStructure:
    def test_no_headers_in_daily_report_produces_warning(self, validator):
        content = (
            "Work Completed: framing done. Workforce: 8 workers. "
            "Weather: sunny 72F. " + "x" * 200
        )
        result = validator.validate(content, ServiceType.DAILY_REPORT)
        md_warnings = [w for w in result.warnings if "markdown" in w.lower() or "header" in w.lower()]
        assert md_warnings

    def test_customer_update_does_not_require_markdown(self, validator):
        # CustomerUpdate uses email format, not markdown — no markdown warning expected
        result = validator.validate(VALID_CUSTOMER_UPDATE, ServiceType.CUSTOMER_UPDATE)
        md_warnings = [w for w in result.warnings if "markdown" in w.lower() or "header" in w.lower()]
        assert md_warnings == []

    def test_safety_talk_with_headers_passes_markdown_check(self, validator):
        result = validator.validate(VALID_SAFETY_TALK, ServiceType.SAFETY_TALK)
        md_warnings = [w for w in result.warnings if "markdown" in w.lower() or "header" in w.lower()]
        assert md_warnings == []


# ── Full valid outputs pass all checks ────────────────────────────────────────

class TestFullValidOutputs:
    def test_valid_daily_report_passes(self, validator):
        result = validator.validate(VALID_DAILY_REPORT, ServiceType.DAILY_REPORT)
        assert result.passed is True, f"Errors: {result.errors}"

    def test_valid_customer_update_passes(self, validator):
        result = validator.validate(VALID_CUSTOMER_UPDATE, ServiceType.CUSTOMER_UPDATE)
        assert result.passed is True, f"Errors: {result.errors}"

    def test_valid_safety_talk_passes(self, validator):
        result = validator.validate(VALID_SAFETY_TALK, ServiceType.SAFETY_TALK)
        assert result.passed is True, f"Errors: {result.errors}"

    def test_valid_material_reminder_passes(self, validator):
        result = validator.validate(VALID_MATERIAL_REMINDER, ServiceType.MATERIAL_REMINDER)
        assert result.passed is True, f"Errors: {result.errors}"


# ── ContentValidationResult ────────────────────────────────────────────────────

class TestContentValidationResult:
    def test_passed_true_when_no_errors(self, validator):
        result = validator.validate(VALID_DAILY_REPORT, ServiceType.DAILY_REPORT)
        assert result.passed is True
        assert result.errors == []

    def test_passed_false_when_errors_present(self, validator):
        result = validator.validate("", ServiceType.DAILY_REPORT)
        assert result.passed is False
        assert len(result.errors) >= 1

    def test_warnings_do_not_affect_passed(self, validator):
        # A content that has warnings but no errors should still pass
        # Build content with a duplicate sentence warning but no errors
        extra = "The crew completed the north wall framing and all structural elements are in place"
        content = VALID_DAILY_REPORT + f"\n\n{extra}. {extra}."
        result = validator.validate(content, ServiceType.DAILY_REPORT)
        if result.warnings:  # if duplicate detection triggered
            # passed should still be True (warnings don't fail validation)
            assert result.passed is True
