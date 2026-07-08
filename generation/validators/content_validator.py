"""
content_validator.py — AI output quality checks beyond JSON structure.

Why content validation matters:
    JSON validation (Sprint 4) confirms the AI returned parseable JSON.
    Content validation confirms the CONTENT is useful. An AI can return valid
    JSON with an empty string, a placeholder like "{{date}}", or a 10-word
    response that technically passes JSON validation but is useless in production.

Checks performed:
    1. Empty output detection
    2. Minimum/maximum character length (per service type)
    3. Required phrases/sections present
    4. Unfilled template placeholder detection
    5. Duplicate sentence detection
    6. Markdown structure validation (for services expecting Markdown)

Design:
    One ContentValidator class handles all service types. Each check receives
    the service_type to apply per-service rules. This is better than 4 separate
    validator classes (which would duplicate the boilerplate detection logic)
    while still keeping the rules per-service (configurable, not hardcoded).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from generation.models.outputs import ServiceType

logger = logging.getLogger(__name__)

# ── Per-service constraints ────────────────────────────────────────────────────

_MIN_LENGTH: dict[ServiceType, int] = {
    ServiceType.DAILY_REPORT: 300,
    ServiceType.CUSTOMER_UPDATE: 100,
    ServiceType.SAFETY_TALK: 250,
    ServiceType.MATERIAL_REMINDER: 100,
}

_MAX_LENGTH: dict[ServiceType, int] = {
    ServiceType.DAILY_REPORT: 8000,
    ServiceType.CUSTOMER_UPDATE: 2000,
    ServiceType.SAFETY_TALK: 5000,
    ServiceType.MATERIAL_REMINDER: 3000,
}

# Required phrases that must appear in the output (case-insensitive check)
_REQUIRED_PHRASES: dict[ServiceType, list[str]] = {
    ServiceType.DAILY_REPORT: [
        "Work Completed",
        "Workforce",
        "Weather",
    ],
    ServiceType.CUSTOMER_UPDATE: [
        "Subject:",
        "Best regards",
        "Construction Team",
    ],
    ServiceType.SAFETY_TALK: [
        "PPE",
        "Safety",
        "Emergency",
    ],
    ServiceType.MATERIAL_REMINDER: [
        "Material",
        "Priority",
    ],
}

# Services whose output is expected to contain Markdown headers
_EXPECTS_MARKDOWN: set[ServiceType] = {
    ServiceType.DAILY_REPORT,
    ServiceType.SAFETY_TALK,
    ServiceType.MATERIAL_REMINDER,
}

# Patterns that indicate an unfilled template placeholder
_PLACEHOLDER_PATTERNS: list[re.Pattern] = [
    re.compile(r"\{\{[^}]+\}\}"),          # {{variable}}
    re.compile(r"\[PLACEHOLDER\]"),         # [PLACEHOLDER]
    re.compile(r"\[INSERT\s+[^\]]+\]"),     # [INSERT something]
    re.compile(r"\[YOUR\s+[^\]]+\]"),       # [YOUR something]
    re.compile(r"<PLACEHOLDER>"),           # <PLACEHOLDER>
    re.compile(r"\[DATE FROM LOG\]"),       # unfilled date placeholder from prompt template
    re.compile(r"\[DATE\]"),               # simple date placeholder
]


@dataclass
class ContentValidationResult:
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class ContentValidator:
    """
    Validates AI-generated content for quality beyond structural correctness.

    Usage:
        validator = ContentValidator()
        result = validator.validate(ai_output_text, ServiceType.DAILY_REPORT)
        if not result.passed:
            # handle failure
    """

    def validate(
        self, content: str, service_type: ServiceType
    ) -> ContentValidationResult:
        errors: list[str] = []
        warnings: list[str] = []

        stripped = content.strip()

        # 1. Empty output
        if not stripped:
            errors.append("AI output is empty")
            return ContentValidationResult(passed=False, errors=errors, warnings=warnings)

        # 2. Length checks
        char_count = len(stripped)
        min_len = _MIN_LENGTH.get(service_type, 50)
        max_len = _MAX_LENGTH.get(service_type, 10_000)

        if char_count < min_len:
            errors.append(
                f"Output too short: {char_count} chars "
                f"(minimum {min_len} for {service_type.value})"
            )

        if char_count > max_len:
            warnings.append(
                f"Output unusually long: {char_count} chars "
                f"(expected maximum {max_len} for {service_type.value})"
            )

        # 3. Required phrases
        for phrase in _REQUIRED_PHRASES.get(service_type, []):
            if phrase.lower() not in stripped.lower():
                errors.append(f"Required section/phrase missing: '{phrase}'")

        # 4. Placeholder detection
        found_placeholders: list[str] = []
        for pattern in _PLACEHOLDER_PATTERNS:
            matches = pattern.findall(stripped)
            found_placeholders.extend(matches)
        if found_placeholders:
            unique = list(dict.fromkeys(found_placeholders))[:3]
            errors.append(f"Unfilled template placeholders found: {unique}")

        # 5. Duplicate sentence detection
        sentences = [
            s.strip()
            for s in re.split(r"[.!?\n]+", stripped)
            if len(s.strip()) > 25
        ]
        seen_sentences: set[str] = set()
        duplicates: list[str] = []
        for s in sentences:
            norm = re.sub(r"\s+", " ", s.lower())
            if norm in seen_sentences:
                duplicates.append(s[:70])
            seen_sentences.add(norm)
        if duplicates:
            warnings.append(
                f"Possibly duplicated sentences: {duplicates[:2]}"
            )

        # 6. Markdown structure
        if service_type in _EXPECTS_MARKDOWN and "#" not in stripped:
            warnings.append(
                f"Expected Markdown headers (#) not found in {service_type.value} output"
            )

        passed = len(errors) == 0
        logger.debug(
            "ContentValidator: %s %s — %d error(s), %d warning(s)",
            service_type.value,
            "PASS" if passed else "FAIL",
            len(errors),
            len(warnings),
        )
        return ContentValidationResult(passed=passed, errors=errors, warnings=warnings)
