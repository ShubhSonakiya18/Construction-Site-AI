"""
tests/test_transcript_cleaner.py — Unit tests for TranscriptCleaner and
ConstructionNormalizer.

No audio files needed. All tests operate on synthetic Transcript objects
constructed directly from dataclasses.
"""
from __future__ import annotations

import pytest

from speech.models.transcript import Transcript, TranscriptSegment, WordTimestamp
from speech.postprocessors.construction_normalizer import ConstructionNormalizer
from speech.postprocessors.transcript_cleaner import TranscriptCleaner


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_segment(text: str, id: int = 0, confidence: float = 0.85,
                 no_speech_prob: float = 0.01) -> TranscriptSegment:
    return TranscriptSegment(
        id=id, text=text, start=float(id), end=float(id + 1),
        avg_logprob=-0.3, no_speech_prob=no_speech_prob, confidence=confidence, words=[]
    )


def make_transcript(segments: list[TranscriptSegment]) -> Transcript:
    return Transcript(
        text=" ".join(s.text for s in segments),
        language="en",
        language_probability=0.99,
        duration_seconds=float(len(segments)),
        segments=segments,
    )


# ── ConstructionNormalizer ─────────────────────────────────────────────────────

class TestConstructionNormalizer:
    @pytest.fixture()
    def norm(self):
        return ConstructionNormalizer()

    def test_rebar_correction(self, norm):
        assert norm.normalize("check the re bar here") == "check the rebar here"

    def test_hvac_correction(self, norm):
        result = norm.normalize("the h v a c unit is broken")
        assert "HVAC" in result

    def test_pvc_correction(self, norm):
        result = norm.normalize("install p v c pipe")
        assert "PVC" in result

    def test_case_insensitive_match(self, norm):
        result = norm.normalize("check the RE BAR section")
        assert "rebar" in result.lower()

    def test_no_false_positive_on_normal_text(self, norm):
        text = "The project is on schedule."
        assert norm.normalize(text) == text

    def test_empty_string(self, norm):
        assert norm.normalize("") == ""

    def test_extra_corrections(self):
        norm = ConstructionNormalizer(extra_corrections={"spec sheet": "specification sheet"})
        result = norm.normalize("see the spec sheet for details")
        assert "specification sheet" in result

    def test_longest_match_first(self):
        # "re bar" should be caught before "bar" alone could interfere
        norm = ConstructionNormalizer()
        result = norm.normalize("the re bar and steel bar are different")
        assert "rebar" in result

    def test_normalize_segment_texts(self, norm):
        texts = ["check re bar", "install p v c pipe"]
        results = norm.normalize_segment_texts(texts)
        assert len(results) == 2
        assert "rebar" in results[0]
        assert "PVC" in results[1]


# ── TranscriptCleaner — filler removal ────────────────────────────────────────

class TestTranscriptCleanerFillers:
    @pytest.fixture()
    def cleaner(self):
        return TranscriptCleaner(
            remove_filler_words=True,
            normalize_construction_terms=False,
            drop_hallucinations=False,
        )

    def test_removes_um(self, cleaner):
        seg = make_segment("Um so we need the rebar.")
        t = make_transcript([seg])
        cleaned = cleaner.clean(t)
        assert "um" not in cleaned.text.lower()
        assert "Um" not in cleaned.text

    def test_removes_uh(self, cleaner):
        seg = make_segment("The uh column needs inspection.")
        t = make_transcript([seg])
        cleaned = cleaner.clean(t)
        assert "uh" not in cleaned.text.lower()

    def test_preserves_content_words(self, cleaner):
        seg = make_segment("Um check the footing uh depth.")
        t = make_transcript([seg])
        cleaned = cleaner.clean(t)
        assert "check" in cleaned.text
        assert "footing" in cleaned.text
        assert "depth" in cleaned.text

    def test_does_not_remove_partial_matches(self, cleaner):
        # "umbrella" should not be stripped because "um" is word-boundary matched
        seg = make_segment("Bring the umbrella tomorrow.")
        t = make_transcript([seg])
        cleaned = cleaner.clean(t)
        assert "umbrella" in cleaned.text

    def test_cleans_multiple_fillers(self, cleaner):
        seg = make_segment("Um, like, you know, the beam is, uh, there.")
        t = make_transcript([seg])
        cleaned = cleaner.clean(t)
        filler_words = ["um", "uh", "like", "you know"]
        for fw in filler_words:
            assert fw not in cleaned.text.lower()


# ── TranscriptCleaner — hallucination dropping ────────────────────────────────

class TestTranscriptCleanerHallucinations:
    @pytest.fixture()
    def cleaner(self):
        return TranscriptCleaner(
            remove_filler_words=False,
            normalize_construction_terms=False,
            drop_hallucinations=True,
        )

    def test_drops_inaudible(self, cleaner):
        segs = [
            make_segment("Check the rebar.", 0),
            make_segment("[INAUDIBLE]", 1, no_speech_prob=0.95),
            make_segment("Level two is done.", 2),
        ]
        t = make_transcript(segs)
        cleaned = cleaner.clean(t)
        assert len(cleaned.segments) == 2
        assert not any("[INAUDIBLE]" in s.text for s in cleaned.segments)

    def test_drops_music_marker(self, cleaner):
        segs = [make_segment("[Music]", 0), make_segment("Real speech here.", 1)]
        t = make_transcript(segs)
        cleaned = cleaner.clean(t)
        assert len(cleaned.segments) == 1
        assert cleaned.segments[0].text == "Real speech here."

    def test_drops_punctuation_only_segment(self, cleaner):
        segs = [make_segment("...", 0), make_segment("Good content.", 1)]
        t = make_transcript(segs)
        cleaned = cleaner.clean(t)
        assert len(cleaned.segments) == 1

    def test_keeps_real_speech(self, cleaner):
        segs = [make_segment("The footing is poured.", 0)]
        t = make_transcript(segs)
        cleaned = cleaner.clean(t)
        assert len(cleaned.segments) == 1

    def test_empty_result_when_all_hallucinated(self, cleaner):
        segs = [make_segment("[INAUDIBLE]", 0), make_segment("[Music]", 1)]
        t = make_transcript(segs)
        cleaned = cleaner.clean(t)
        assert len(cleaned.segments) == 0
        assert cleaned.is_empty()


# ── TranscriptCleaner — construction normalization ────────────────────────────

class TestTranscriptCleanerNormalization:
    @pytest.fixture()
    def cleaner(self):
        return TranscriptCleaner(
            remove_filler_words=False,
            normalize_construction_terms=True,
            drop_hallucinations=False,
        )

    def test_normalizes_rebar(self, cleaner):
        seg = make_segment("We need re bar for the slab.")
        t = make_transcript([seg])
        cleaned = cleaner.clean(t)
        assert "rebar" in cleaned.text

    def test_normalizes_hvac(self, cleaner):
        seg = make_segment("The h v a c unit needs work.")
        t = make_transcript([seg])
        cleaned = cleaner.clean(t)
        assert "HVAC" in cleaned.text

    def test_rebuilds_full_text_from_segments(self, cleaner):
        segs = [
            make_segment("Install the re bar.", 0),
            make_segment("Check the p v c pipe.", 1),
        ]
        t = make_transcript(segs)
        cleaned = cleaner.clean(t)
        assert "rebar" in cleaned.text
        assert "PVC" in cleaned.text


# ── TranscriptCleaner — full pipeline ─────────────────────────────────────────

class TestTranscriptCleanerFull:
    @pytest.fixture()
    def full_cleaner(self):
        return TranscriptCleaner(
            remove_filler_words=True,
            normalize_construction_terms=True,
            drop_hallucinations=True,
        )

    def test_full_clean_on_sample_transcript(self, full_cleaner, sample_transcript):
        cleaned = full_cleaner.clean(sample_transcript)
        assert isinstance(cleaned, Transcript)
        assert not any("[INAUDIBLE]" in s.text for s in cleaned.segments)
        assert "um" not in cleaned.text.lower()
        assert "uh" not in cleaned.text.lower()

    def test_does_not_mutate_original(self, full_cleaner, sample_transcript):
        original_text = sample_transcript.text
        original_seg_count = len(sample_transcript.segments)
        full_cleaner.clean(sample_transcript)
        assert sample_transcript.text == original_text
        assert len(sample_transcript.segments) == original_seg_count

    def test_segment_ids_renumbered(self, full_cleaner):
        segs = [
            make_segment("[INAUDIBLE]", 0),
            make_segment("Good content here.", 1),
            make_segment("More good content.", 2),
        ]
        t = make_transcript(segs)
        cleaned = full_cleaner.clean(t)
        assert len(cleaned.segments) == 2
        assert cleaned.segments[0].id == 0
        assert cleaned.segments[1].id == 1

    def test_whitespace_is_clean(self, full_cleaner):
        seg = make_segment("  Um  ,  like  ,  check  the  beam  .  ")
        t = make_transcript([seg])
        cleaned = full_cleaner.clean(t)
        assert "  " not in cleaned.text
        assert not cleaned.text.startswith(" ")
        assert not cleaned.text.endswith(" ")
