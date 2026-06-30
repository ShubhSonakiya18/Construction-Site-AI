"""
speech/postprocessors/construction_normalizer.py — Fix STT misrecognitions of
construction terminology.

Whisper's general-purpose training data underrepresents construction industry
vocabulary. Common patterns:
- Acronyms spoken letter-by-letter: "P V C" -> "PVC", "H V A C" -> "HVAC"
- Compound words split: "re bar" -> "rebar"
- Numeric dimensions: "two by four" -> "2x4"

This module contains ONLY display-level corrections (how terms appear in text).
It contains zero construction domain knowledge about what terms mean or when
they are valid. That knowledge lives in knowledge/*.json.
"""
from __future__ import annotations

import re

from speech.utils.constants import CONSTRUCTION_TERM_CORRECTIONS


class ConstructionNormalizer:
    """
    Applies pattern-based text corrections for construction terminology.

    Case-insensitive matching. Replacements preserve the canonical casing from
    CONSTRUCTION_TERM_CORRECTIONS (e.g., "PVC", "HVAC", "rebar").
    """

    def __init__(
        self,
        extra_corrections: dict[str, str] | None = None,
    ) -> None:
        # Merge built-in corrections with any caller-supplied overrides
        corrections = dict(CONSTRUCTION_TERM_CORRECTIONS)
        if extra_corrections:
            corrections.update(extra_corrections)

        # Pre-compile patterns sorted longest-first to avoid partial replacements
        self._patterns: list[tuple[re.Pattern, str]] = [
            (re.compile(r"\b" + re.escape(pattern) + r"\b", re.IGNORECASE), replacement)
            for pattern, replacement in sorted(
                corrections.items(), key=lambda kv: len(kv[0]), reverse=True
            )
        ]

    def normalize(self, text: str) -> str:
        """
        Apply all construction term corrections to text.

        Returns the corrected string. The original text is never modified.
        """
        result = text
        for pattern, replacement in self._patterns:
            result = pattern.sub(replacement, result)
        return result

    def normalize_segment_texts(self, texts: list[str]) -> list[str]:
        """Normalize a list of segment texts (e.g. from TranscriptSegment)."""
        return [self.normalize(t) for t in texts]
