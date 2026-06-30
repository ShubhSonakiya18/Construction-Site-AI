"""
tests/test_speech_models.py — Unit tests for the core data model classes.

Tests cover:
- WordTimestamp, TranscriptSegment, Transcript construction and serialization
- AudioFileInfo, ProcessingStats, SpeechProcessingMetadata
- SpeechProcessingResult (success, failure, serialization)
- AudioValidationResult
"""
from __future__ import annotations

import json

import pytest

from speech.models.metadata import AudioFileInfo, ProcessingStats, SpeechProcessingMetadata
from speech.models.processing_result import AudioValidationResult, SpeechProcessingResult
from speech.models.transcript import Transcript, TranscriptSegment, WordTimestamp


# ── WordTimestamp ──────────────────────────────────────────────────────────────

class TestWordTimestamp:
    def test_construction(self):
        wt = WordTimestamp(word="rebar", start=1.0, end=1.5, probability=0.92)
        assert wt.word == "rebar"
        assert wt.start == 1.0
        assert wt.end == 1.5
        assert wt.probability == 0.92

    def test_to_dict_keys(self):
        wt = WordTimestamp("beam", 0.0, 0.5, 0.8)
        d = wt.to_dict()
        assert set(d) == {"word", "start", "end", "probability"}

    def test_to_dict_values(self):
        wt = WordTimestamp("column", 2.0, 2.5, 0.95)
        d = wt.to_dict()
        assert d["word"] == "column"
        assert d["start"] == 2.0
        assert d["end"] == 2.5
        assert d["probability"] == 0.95


# ── TranscriptSegment ──────────────────────────────────────────────────────────

class TestTranscriptSegment:
    def _make(self, **kwargs):
        defaults = dict(
            id=0, text="Test segment.", start=0.0, end=3.0,
            avg_logprob=-0.3, no_speech_prob=0.02, confidence=0.74, words=[]
        )
        defaults.update(kwargs)
        return TranscriptSegment(**defaults)

    def test_duration(self):
        seg = self._make(start=1.0, end=4.0)
        assert seg.duration() == pytest.approx(3.0)

    def test_duration_zero(self):
        seg = self._make(start=2.5, end=2.5)
        assert seg.duration() == pytest.approx(0.0)

    def test_to_dict_has_required_keys(self):
        seg = self._make()
        d = seg.to_dict()
        for key in ("id", "text", "start", "end", "avg_logprob",
                    "no_speech_prob", "confidence", "words", "duration"):
            assert key in d, f"Missing key: {key}"

    def test_to_dict_words_is_list(self):
        wt = WordTimestamp("hello", 0.0, 0.5, 0.9)
        seg = self._make(words=[wt])
        d = seg.to_dict()
        assert isinstance(d["words"], list)
        assert len(d["words"]) == 1
        assert d["words"][0]["word"] == "hello"


# ── Transcript ─────────────────────────────────────────────────────────────────

class TestTranscript:
    def _make(self, text="Hello world.", segments=None):
        if segments is None:
            segments = []
        return Transcript(
            text=text,
            language="en",
            language_probability=0.99,
            duration_seconds=5.0,
            segments=segments,
        )

    def test_word_count_empty(self):
        t = self._make(text="")
        assert t.word_count() == 0

    def test_word_count(self):
        t = self._make(text="Hello world test.")
        assert t.word_count() == 3

    def test_avg_confidence_no_segments(self):
        t = self._make()
        assert t.avg_confidence() == 0.0

    def test_avg_confidence_with_segments(self):
        segs = [
            TranscriptSegment(0, "a", 0, 1, -0.3, 0.01, 0.8, []),
            TranscriptSegment(1, "b", 1, 2, -0.3, 0.01, 0.6, []),
        ]
        t = self._make(segments=segs)
        assert t.avg_confidence() == pytest.approx(0.7)

    def test_is_empty_true(self):
        t = self._make(text="")
        assert t.is_empty() is True

    def test_is_empty_false(self):
        t = self._make(text="Something here.")
        assert t.is_empty() is False

    def test_is_empty_whitespace(self):
        t = self._make(text="   ")
        assert t.is_empty() is True

    def test_to_dict_is_json_serializable(self):
        t = self._make(text="Check the PVC.")
        d = t.to_dict()
        serialized = json.dumps(d)
        assert "PVC" in serialized

    def test_to_dict_structure(self):
        t = self._make()
        d = t.to_dict()
        for key in ("text", "language", "language_probability",
                    "duration_seconds", "segments", "word_count", "avg_confidence"):
            assert key in d


# ── SpeechProcessingResult ─────────────────────────────────────────────────────

class TestSpeechProcessingResult:
    def test_success_result(self, sample_processing_result):
        r = sample_processing_result
        assert r.success is True
        assert r.transcript is not None
        assert r.errors == []

    def test_plain_text(self, sample_processing_result):
        text = sample_processing_result.plain_text()
        assert isinstance(text, str)
        assert len(text) > 0

    def test_confidence(self, sample_processing_result):
        c = sample_processing_result.confidence()
        assert 0.0 <= c <= 1.0

    def test_duration_seconds(self, sample_processing_result):
        d = sample_processing_result.duration_seconds()
        assert d > 0

    def test_language(self, sample_processing_result):
        lang = sample_processing_result.language()
        assert lang == "en"

    def test_to_dict_is_complete(self, sample_processing_result):
        d = sample_processing_result.to_dict()
        for key in ("success", "audio_id", "metadata", "transcript",
                    "validation", "errors", "warnings"):
            assert key in d

    def test_to_json_is_valid(self, sample_processing_result):
        raw = sample_processing_result.to_json()
        parsed = json.loads(raw)
        assert parsed["success"] is True
        assert "transcript" in parsed

    def test_failure_factory(self):
        from speech.models.metadata import SpeechProcessingMetadata
        meta = SpeechProcessingMetadata(
            audio_id="fail-001",
            framework_version="1.0.0",
            audio_info=None,
            stats=None,
            project_id=None,
        )
        r = SpeechProcessingResult.failure(
            audio_id="fail-001",
            metadata=meta,
            errors=["File not found"],
        )
        assert r.success is False
        assert "File not found" in r.errors
        assert r.transcript is None

    def test_failure_plain_text_is_empty(self):
        from speech.models.metadata import SpeechProcessingMetadata
        meta = SpeechProcessingMetadata("x", "1.0.0", None, None, None)
        r = SpeechProcessingResult.failure("x", meta, ["err"])
        assert r.plain_text() == ""

    def test_failure_confidence_is_zero(self):
        from speech.models.metadata import SpeechProcessingMetadata
        meta = SpeechProcessingMetadata("x", "1.0.0", None, None, None)
        r = SpeechProcessingResult.failure("x", meta, ["err"])
        assert r.confidence() == 0.0


# ── AudioValidationResult ──────────────────────────────────────────────────────

class TestAudioValidationResult:
    def test_valid_result(self):
        r = AudioValidationResult(is_valid=True, errors=[], warnings=[], audio_info=None)
        assert r.is_valid is True

    def test_invalid_has_errors(self):
        r = AudioValidationResult(is_valid=False, errors=["too small"], warnings=[], audio_info=None)
        assert r.is_valid is False
        assert len(r.errors) == 1
