"""
speech/postprocessors/transcript_cleaner.py — Post-STT transcript cleaning.

Whisper's raw output often includes:
- Filler words: "um", "uh", "like", "you know"
- [INAUDIBLE] markers for segments it could not transcribe
- Repeated punctuation or whitespace from segment boundaries
- Hallucinated text for silent segments (when VAD filter is off)

This cleaner operates on Transcript objects and returns new cleaned Transcript
objects. It never modifies in place — callers can compare before/after.
"""
from __future__ import annotations

import re

from speech.models.transcript import Transcript, TranscriptSegment
from speech.postprocessors.construction_normalizer import ConstructionNormalizer
from speech.utils.constants import FILLER_WORDS


# Patterns for Whisper hallucination artifacts — segments containing ONLY these
# should be dropped (they contain no real speech content).
_HALLUCINATION_PATTERNS: list[re.Pattern] = [
    re.compile(r"^\[.*?\]$"),                    # [INAUDIBLE], [Music], [Applause]
    re.compile(r"^[\s\.\,\!\?\-\*]+$"),          # Punctuation-only segments
    re.compile(r"^(thanks? for watching|subscribe)", re.IGNORECASE),  # YouTube artifacts
    re.compile(r"^(you|thank you)\.?$", re.IGNORECASE),
]

# Filler word pattern — whole-word match only
_FILLER_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(f) for f in sorted(FILLER_WORDS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

# Collapse multiple spaces and fix spacing around punctuation
_MULTI_SPACE = re.compile(r"  +")
_SPACE_BEFORE_PUNCT = re.compile(r" ([,\.!?;:])")


class TranscriptCleaner:
    """
    Cleans a Transcript returned by the STT engine.

    Can be configured to:
    - Remove filler words
    - Apply construction term normalization
    - Drop hallucinated segments

    All operations return a new Transcript; the original is not mutated.
    """

    def __init__(
        self,
        remove_filler_words: bool = True,
        normalize_construction_terms: bool = True,
        drop_hallucinations: bool = True,
    ) -> None:
        self._remove_fillers = remove_filler_words
        self._drop_hallucinations = drop_hallucinations
        self._normalizer = (
            ConstructionNormalizer() if normalize_construction_terms else None
        )

    def clean(self, transcript: Transcript) -> Transcript:
        """
        Return a new cleaned Transcript derived from the input.

        Operations applied in order:
        1. Drop hallucinated/artifact segments
        2. Remove filler words from segment text
        3. Apply construction term normalization
        4. Rebuild full text from cleaned segments
        5. Fix whitespace and punctuation
        """
        cleaned_segments: list[TranscriptSegment] = []

        for seg in transcript.segments:
            text = seg.text.strip()

            if self._drop_hallucinations and self._is_hallucination(text):
                continue

            if self._remove_fillers:
                text = self._strip_fillers(text)

            if self._normalizer:
                text = self._normalizer.normalize(text)

            text = self._fix_whitespace(text)

            if not text:
                continue

            # Build a new segment with cleaned text (other fields unchanged)
            cleaned_segments.append(
                TranscriptSegment(
                    id=len(cleaned_segments),
                    text=text,
                    start=seg.start,
                    end=seg.end,
                    avg_logprob=seg.avg_logprob,
                    no_speech_prob=seg.no_speech_prob,
                    confidence=seg.confidence,
                    words=seg.words,
                )
            )

        full_text = self._join_segments(cleaned_segments)
        full_text = self._fix_whitespace(full_text)

        return Transcript(
            text=full_text,
            language=transcript.language,
            language_probability=transcript.language_probability,
            duration_seconds=transcript.duration_seconds,
            segments=cleaned_segments,
        )

    # ── Private helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _is_hallucination(text: str) -> bool:
        return any(p.match(text) for p in _HALLUCINATION_PATTERNS)

    @staticmethod
    def _strip_fillers(text: str) -> str:
        cleaned = _FILLER_PATTERN.sub("", text)
        return _MULTI_SPACE.sub(" ", cleaned).strip()

    @staticmethod
    def _fix_whitespace(text: str) -> str:
        text = _MULTI_SPACE.sub(" ", text)
        text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
        return text.strip()

    @staticmethod
    def _join_segments(segments: list[TranscriptSegment]) -> str:
        return " ".join(seg.text.strip() for seg in segments if seg.text.strip())
