"""
tests/test_audio_pipeline.py — Integration tests for SpeechProcessingPipeline.

Strategy: inject a MockSTTEngine instead of FasterWhisperEngine so tests run
without a GPU, without downloading 150MB+ models, and without internet access.
All assertions verify the pipeline contract, not Faster Whisper behavior.

Real-STT tests (those that require a downloaded model) are marked:
    @pytest.mark.skipif(not HAS_FASTER_WHISPER, reason="faster-whisper not installed")
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from speech.config import SpeechProcessingConfig, WhisperConfig
from speech.models.processing_result import SpeechProcessingResult
from speech.models.transcript import Transcript, TranscriptSegment
from speech.whisper.engine import BaseSTTEngine

# Check if faster_whisper is installed (needed for real-STT tests)
try:
    import faster_whisper  # noqa: F401
    HAS_FASTER_WHISPER = True
except ImportError:
    HAS_FASTER_WHISPER = False


# ── Mock STT Engine ────────────────────────────────────────────────────────────

class MockSTTEngine(BaseSTTEngine):
    """
    Deterministic mock engine. Returns a canned Transcript on every call.

    Raises MockSTTEngine.Error when self.should_fail is set to True.
    """

    class Error(Exception):
        pass

    def __init__(self, transcript: Transcript | None = None):
        self._transcript = transcript or _make_mock_transcript()
        self.call_count = 0
        self.should_fail = False
        self.last_audio_path: str | None = None

    def transcribe(self, audio_path: str) -> Transcript:
        self.call_count += 1
        self.last_audio_path = audio_path
        if self.should_fail:
            raise MockSTTEngine.Error("Simulated STT failure")
        return self._transcript

    def is_available(self) -> bool:
        return True


def _make_mock_transcript(text: str = "The rebar is in place on level two.") -> Transcript:
    seg = TranscriptSegment(
        id=0, text=text, start=0.0, end=3.5,
        avg_logprob=-0.2, no_speech_prob=0.01, confidence=0.85, words=[],
    )
    return Transcript(
        text=text, language="en", language_probability=0.99,
        duration_seconds=3.5, segments=[seg],
    )


# ── Pipeline fixtures ──────────────────────────────────────────────────────────

@pytest.fixture()
def mock_engine():
    return MockSTTEngine()


@pytest.fixture()
def pipeline(mock_engine, default_config):
    from speech.pipeline import SpeechProcessingPipeline
    return SpeechProcessingPipeline(config=default_config, engine=mock_engine)


@pytest.fixture()
def pipeline_with_config(mock_engine):
    from speech.pipeline import SpeechProcessingPipeline
    config = SpeechProcessingConfig(
        whisper=WhisperConfig(model_size="base"),
    )
    return SpeechProcessingPipeline(config=config, engine=mock_engine)


# ── Single-file processing ─────────────────────────────────────────────────────

class TestPipelineSingleFile:
    def test_returns_speech_processing_result(self, pipeline, valid_wav):
        result = pipeline.process(valid_wav)
        assert isinstance(result, SpeechProcessingResult)

    def test_success_on_valid_wav(self, pipeline, valid_wav):
        result = pipeline.process(valid_wav)
        assert result.success is True

    def test_transcript_not_none_on_success(self, pipeline, valid_wav):
        result = pipeline.process(valid_wav)
        assert result.transcript is not None

    def test_audio_id_is_string(self, pipeline, valid_wav):
        result = pipeline.process(valid_wav)
        assert isinstance(result.audio_id, str)
        assert len(result.audio_id) > 0

    def test_metadata_attached(self, pipeline, valid_wav):
        result = pipeline.process(valid_wav)
        assert result.metadata is not None

    def test_validation_attached(self, pipeline, valid_wav):
        result = pipeline.process(valid_wav)
        assert result.validation is not None
        assert result.validation.is_valid is True

    def test_errors_empty_on_success(self, pipeline, valid_wav):
        result = pipeline.process(valid_wav)
        assert result.errors == []

    def test_plain_text_not_empty(self, pipeline, valid_wav):
        result = pipeline.process(valid_wav)
        assert result.plain_text().strip() != ""

    def test_custom_audio_id(self, pipeline, valid_wav):
        result = pipeline.process(valid_wav, audio_id="custom-id-abc")
        assert result.audio_id == "custom-id-abc"

    def test_engine_called_once(self, pipeline, mock_engine, valid_wav):
        pipeline.process(valid_wav)
        assert mock_engine.call_count == 1

    def test_engine_receives_string_path(self, pipeline, mock_engine, valid_wav):
        pipeline.process(valid_wav)
        assert isinstance(mock_engine.last_audio_path, str)


# ── Validation failure path ────────────────────────────────────────────────────

class TestPipelineValidationFailure:
    def test_nonexistent_returns_failure_result(self, pipeline, nonexistent_path):
        result = pipeline.process(nonexistent_path)
        assert result.success is False

    def test_nonexistent_has_errors(self, pipeline, nonexistent_path):
        result = pipeline.process(nonexistent_path)
        assert len(result.errors) > 0

    def test_nonexistent_engine_not_called(self, pipeline, mock_engine, nonexistent_path):
        pipeline.process(nonexistent_path)
        assert mock_engine.call_count == 0

    def test_failure_result_is_spr_type(self, pipeline, nonexistent_path):
        result = pipeline.process(nonexistent_path)
        assert isinstance(result, SpeechProcessingResult)

    def test_failure_plain_text_is_empty(self, pipeline, nonexistent_path):
        result = pipeline.process(nonexistent_path)
        assert result.plain_text() == ""


# ── STT engine failure path ────────────────────────────────────────────────────

class TestPipelineSTTFailure:
    def test_stt_error_returns_failure(self, pipeline, mock_engine, valid_wav):
        mock_engine.should_fail = True
        result = pipeline.process(valid_wav)
        assert result.success is False

    def test_stt_error_has_error_message(self, pipeline, mock_engine, valid_wav):
        mock_engine.should_fail = True
        result = pipeline.process(valid_wav)
        assert len(result.errors) > 0
        combined = " ".join(result.errors).lower()
        assert "transcription" in combined or "error" in combined or "failure" in combined

    def test_stt_error_result_has_metadata(self, pipeline, mock_engine, valid_wav):
        mock_engine.should_fail = True
        result = pipeline.process(valid_wav)
        assert result.metadata is not None


# ── Batch processing ───────────────────────────────────────────────────────────

class TestPipelineBatch:
    def test_batch_returns_list(self, pipeline, valid_wav, long_wav):
        results = pipeline.process_batch([valid_wav, long_wav])
        assert isinstance(results, list)

    def test_batch_length_matches_input(self, pipeline, valid_wav, long_wav):
        results = pipeline.process_batch([valid_wav, long_wav])
        assert len(results) == 2

    def test_batch_empty_input(self, pipeline):
        results = pipeline.process_batch([])
        assert results == []

    def test_batch_engine_called_per_file(self, pipeline, mock_engine, valid_wav, long_wav):
        pipeline.process_batch([valid_wav, long_wav])
        assert mock_engine.call_count == 2

    def test_batch_on_result_callback(self, pipeline, valid_wav, long_wav):
        received = []
        pipeline.process_batch([valid_wav, long_wav], on_result=received.append)
        assert len(received) == 2

    def test_batch_callback_failure_does_not_crash(self, pipeline, valid_wav):
        def bad_callback(r):
            raise RuntimeError("callback error")
        results = pipeline.process_batch([valid_wav], on_result=bad_callback)
        assert len(results) == 1

    def test_batch_mixed_valid_invalid(self, pipeline, valid_wav, nonexistent_path):
        results = pipeline.process_batch([valid_wav, nonexistent_path])
        assert results[0].success is True
        assert results[1].success is False


# ── Metadata content ───────────────────────────────────────────────────────────

class TestPipelineMetadata:
    def test_stats_completed_at_is_set(self, pipeline, valid_wav):
        result = pipeline.process(valid_wav)
        assert result.metadata.stats is not None
        assert result.metadata.stats.completed_at is not None

    def test_stats_processing_time_positive(self, pipeline, valid_wav):
        result = pipeline.process(valid_wav)
        assert result.metadata.stats.processing_time_seconds >= 0

    def test_stages_completed_includes_transcription(self, pipeline, valid_wav):
        result = pipeline.process(valid_wav)
        assert "transcription" in result.metadata.stats.stages_completed

    def test_stages_completed_includes_validation(self, pipeline, valid_wav):
        result = pipeline.process(valid_wav)
        assert "validation" in result.metadata.stats.stages_completed

    def test_project_id_attached(self, pipeline, valid_wav):
        result = pipeline.process(valid_wav, project_id="site-alpha")
        assert result.metadata.project_id == "site-alpha"


# ── Export path ────────────────────────────────────────────────────────────────

class TestPipelineExport:
    def test_export_to_creates_json(self, pipeline, valid_wav, tmp_path):
        result = pipeline.process(valid_wav, export_to=str(tmp_path))
        json_files = list(tmp_path.glob("*.json"))
        assert len(json_files) == 1

    def test_exported_json_is_valid(self, pipeline, valid_wav, tmp_path):
        result = pipeline.process(valid_wav, export_to=str(tmp_path))
        json_file = next(tmp_path.glob("*.json"))
        parsed = json.loads(json_file.read_text(encoding="utf-8"))
        assert parsed["success"] is True

    def test_exported_filename_is_audio_id(self, pipeline, valid_wav, tmp_path):
        result = pipeline.process(valid_wav, export_to=str(tmp_path))
        json_file = next(tmp_path.glob("*.json"))
        assert result.audio_id in json_file.name


# ── Progress callback ──────────────────────────────────────────────────────────

class TestPipelineProgressCallback:
    def test_progress_callback_called(self, mock_engine, valid_wav):
        from speech.pipeline import SpeechProcessingPipeline
        calls = []
        config = SpeechProcessingConfig(progress_callback=lambda s, p: calls.append((s, p)))
        pl = SpeechProcessingPipeline(config=config, engine=mock_engine)
        pl.process(valid_wav)
        assert len(calls) > 0

    def test_progress_callback_stages_are_strings(self, mock_engine, valid_wav):
        from speech.pipeline import SpeechProcessingPipeline
        stages = []
        config = SpeechProcessingConfig(progress_callback=lambda s, p: stages.append(s))
        pl = SpeechProcessingPipeline(config=config, engine=mock_engine)
        pl.process(valid_wav)
        assert all(isinstance(s, str) for s in stages)

    def test_progress_final_stage_is_complete(self, mock_engine, valid_wav):
        from speech.pipeline import SpeechProcessingPipeline
        stages = []
        config = SpeechProcessingConfig(progress_callback=lambda s, p: stages.append(s))
        pl = SpeechProcessingPipeline(config=config, engine=mock_engine)
        pl.process(valid_wav)
        assert stages[-1] == "complete"

    def test_broken_callback_does_not_crash_pipeline(self, mock_engine, valid_wav):
        from speech.pipeline import SpeechProcessingPipeline
        def bad_cb(s, p):
            raise RuntimeError("callback broken")
        config = SpeechProcessingConfig(progress_callback=bad_cb)
        pl = SpeechProcessingPipeline(config=config, engine=mock_engine)
        result = pl.process(valid_wav)
        assert isinstance(result, SpeechProcessingResult)


# ── Real STT tests (skipped if faster_whisper not installed) ───────────────────

@pytest.mark.skipif(not HAS_FASTER_WHISPER, reason="faster-whisper not installed")
class TestRealSTTEngine:
    """These tests actually load a Whisper model. Skipped in CI unless model is cached."""

    def test_real_engine_processes_sine_wav(self, valid_wav):
        """A sine wave returns some result — may be empty but should not crash."""
        from speech.pipeline import SpeechProcessingPipeline
        config = SpeechProcessingConfig(
            whisper=WhisperConfig(model_size="tiny"),
        )
        pl = SpeechProcessingPipeline(config=config)
        result = pl.process(valid_wav)
        # Sine waves produce no real speech — result may succeed with empty transcript
        assert isinstance(result, SpeechProcessingResult)
        assert result.metadata is not None
