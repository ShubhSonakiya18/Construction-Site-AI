"""
test_extraction_pipeline.py — Integration tests for ExtractionPipeline.

All tests use MockExtractionEngine (injected via engine= parameter).
No network, no GPU required. Real-Groq tests are gated
behind @pytest.mark.skipif(not HAS_GROQ, ...).
"""
from __future__ import annotations

import json
import os
import pytest

from extraction.config import ExtractionConfig
from extraction.engines.base_engine import BaseLLMProvider
from extraction.engines.factory import EngineFactory
from extraction.models.extraction_result import ExtractionResult
from extraction.pipeline import ExtractionPipeline

HAS_GROQ = bool(os.getenv("GROQ_API_KEY", ""))


# ── Mock engine ───────────────────────────────────────────────────────────────

class MockExtractionEngine(BaseLLMProvider):
    """Returns canned JSON responses without calling any LLM."""

    def __init__(
        self,
        response: str | dict = None,
        available: bool = True,
        raise_on_extract: Exception | None = None,
    ):
        self._available = available
        self._raise = raise_on_extract
        if response is None:
            response = {
                "current_stage": "framing",
                "log_date": "2024-01-15",
                "schema_version": "1.0.0",
                "log_source": "voice_recording",
                "workforce": {"total_workers_present": 5},
                "work_completed": [
                    {"task_description": "Framed second floor walls"}
                ],
            }
        self._response = json.dumps(response) if isinstance(response, dict) else response

    @property
    def model_name(self) -> str:
        return "mock-model"

    @property
    def host(self) -> str:
        return "mock://local"

    def is_available(self) -> bool:
        return self._available

    def extract(self, prompt: str) -> tuple[str, dict]:
        if self._raise:
            raise self._raise
        return self._response, {"prompt_tokens": 10, "completion_tokens": 20}


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def pipeline():
    return ExtractionPipeline(engine=MockExtractionEngine())


@pytest.fixture
def sample_transcript():
    return (
        "Today is January 15th. We had 5 workers on site. "
        "We're in the framing stage. Crew framed the second floor walls today. "
        "Weather was sunny. No safety incidents."
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestExtractionPipelineBasic:
    def test_returns_extraction_result(self, pipeline, sample_transcript):
        result = pipeline.extract(sample_transcript)
        assert isinstance(result, ExtractionResult)

    def test_success_on_valid_transcript(self, pipeline, sample_transcript):
        result = pipeline.extract(sample_transcript)
        assert result.success is True
        assert result.extracted_log is not None

    def test_extracted_stage(self, pipeline, sample_transcript):
        result = pipeline.extract(sample_transcript)
        assert result.current_stage() == "framing"

    def test_extracted_workers(self, pipeline, sample_transcript):
        result = pipeline.extract(sample_transcript)
        assert result.worker_count() == 5

    def test_audio_id_preserved(self, sample_transcript):
        engine = MockExtractionEngine()
        pipeline = ExtractionPipeline(engine=engine)
        result = pipeline.extract(sample_transcript, audio_id="my-audio-001")
        assert result.audio_id == "my-audio-001"

    def test_audio_id_generated_when_none(self, pipeline, sample_transcript):
        result = pipeline.extract(sample_transcript)
        assert result.audio_id is not None
        assert len(result.audio_id) > 0

    def test_field_confidences_populated(self, pipeline, sample_transcript):
        result = pipeline.extract(sample_transcript)
        assert isinstance(result.field_confidences, dict)
        assert "current_stage" in result.field_confidences
        assert result.field_confidences["current_stage"] > 0.0

    def test_metadata_populated(self, pipeline, sample_transcript):
        result = pipeline.extract(sample_transcript)
        assert result.metadata is not None
        assert result.metadata.model == "mock-model"
        assert result.metadata.attempts == 1
        assert result.metadata.transcript_length > 0

    def test_to_json_serializable(self, pipeline, sample_transcript):
        result = pipeline.extract(sample_transcript)
        raw = result.to_json()
        parsed = json.loads(raw)
        assert parsed["success"] is True


class TestExtractionPipelineFailureModes:
    def test_empty_transcript_fails(self, pipeline):
        result = pipeline.extract("")
        assert result.success is False
        assert any("empty" in e.lower() for e in result.errors)

    def test_whitespace_transcript_fails(self, pipeline):
        result = pipeline.extract("   \n  ")
        assert result.success is False

    def test_engine_unavailable_fails(self, sample_transcript):
        engine = MockExtractionEngine(available=False)
        pipeline = ExtractionPipeline(engine=engine)
        result = pipeline.extract(sample_transcript)
        assert result.success is False
        assert any("not available" in e.lower() for e in result.errors)

    def test_engine_error_fails_gracefully(self, sample_transcript):
        engine = MockExtractionEngine(raise_on_extract=RuntimeError("connection refused"))
        pipeline = ExtractionPipeline(engine=engine)
        result = pipeline.extract(sample_transcript)
        assert result.success is False
        assert len(result.errors) > 0
        assert result.extracted_log is None

    def test_invalid_json_response_fails(self, sample_transcript):
        engine = MockExtractionEngine(response="this is not json at all!!!")
        pipeline = ExtractionPipeline(engine=engine)
        result = pipeline.extract(sample_transcript)
        assert result.success is False
        assert any("json" in e.lower() for e in result.errors)

    def test_extraction_possible_false_fails(self, sample_transcript):
        engine = MockExtractionEngine(response={"extraction_possible": False})
        pipeline = ExtractionPipeline(engine=engine)
        result = pipeline.extract(sample_transcript)
        assert result.success is False

    def test_never_raises_exception(self, sample_transcript):
        engine = MockExtractionEngine(raise_on_extract=Exception("unexpected crash"))
        pipeline = ExtractionPipeline(engine=engine)
        result = pipeline.extract(sample_transcript)  # must not raise
        assert isinstance(result, ExtractionResult)
        assert result.success is False


class TestExtractionPipelineJSONRepair:
    def test_json_in_markdown_fence_succeeds(self, sample_transcript):
        response = '```json\n{"current_stage": "framing", "workforce": {"total_workers_present": 3}}\n```'
        engine = MockExtractionEngine(response=response)
        pipeline = ExtractionPipeline(engine=engine)
        result = pipeline.extract(sample_transcript)
        assert result.success is True
        assert any("JSON was extracted" in w for w in result.warnings)

    def test_json_in_plain_fence_succeeds(self, sample_transcript):
        response = '```\n{"current_stage": "roofing"}\n```'
        engine = MockExtractionEngine(response=response)
        pipeline = ExtractionPipeline(engine=engine)
        result = pipeline.extract(sample_transcript)
        assert result.success is True


class TestExtractionPipelineFromSpeechResult:
    def test_extract_from_speech_result_success(self, pipeline):
        class FakeSpeechResult:
            success = True
            audio_id = "speech-001"
            def plain_text(self): return "Framing the second floor, 5 workers on site."

        result = pipeline.extract_from_speech_result(FakeSpeechResult())
        assert isinstance(result, ExtractionResult)

    def test_extract_from_failed_speech_result(self, pipeline):
        class FakeSpeechResult:
            success = False
            audio_id = "speech-002"
            def plain_text(self): return ""

        result = pipeline.extract_from_speech_result(FakeSpeechResult())
        assert result.success is False
        assert any("SpeechProcessingResult" in e for e in result.errors)


class TestExtractionPipelineConfig:
    def test_custom_config_respected(self, sample_transcript):
        config = ExtractionConfig(max_retries=1, retry_delay_seconds=0.0)
        engine = MockExtractionEngine(raise_on_extract=RuntimeError("fail"))
        pipeline = ExtractionPipeline(config=config, engine=engine)
        result = pipeline.extract(sample_transcript)
        assert result.success is False
        assert result.metadata.attempts == 1

    def test_default_pipeline_builds_without_error(self):
        # Should construct without raising even if Groq API key is not set
        pipeline = ExtractionPipeline()
        assert pipeline is not None


@pytest.mark.skipif(not HAS_GROQ, reason="GROQ_API_KEY not set")
class TestRealGroqEngine:
    def test_real_extraction(self):
        pipeline = ExtractionPipeline()
        result = pipeline.extract(
            "Today we had 4 workers. We're doing framing. Weather was cloudy. No incidents."
        )
        assert isinstance(result, ExtractionResult)


class TestEngineFactory:
    def test_groq_is_registered(self):
        assert "groq" in EngineFactory.available()

    def test_available_returns_list(self):
        providers = EngineFactory.available()
        assert isinstance(providers, list)
        assert len(providers) >= 1

    def test_create_from_config_returns_provider(self):
        config = ExtractionConfig()
        engine = EngineFactory.create_from_config(config)
        assert isinstance(engine, BaseLLMProvider)

    def test_unknown_provider_raises(self):
        config = ExtractionConfig(provider="nonexistent_provider")
        with pytest.raises(ValueError, match="nonexistent_provider"):
            EngineFactory.create_from_config(config)

    def test_register_custom_provider(self):
        class DummyEngine(BaseLLMProvider):
            def __init__(self, system_prompt="", **kwargs): pass
            @property
            def model_name(self): return "dummy"
            @property
            def host(self): return "dummy://local"
            def is_available(self): return True
            def extract(self, prompt): return '{"test": true}', {}

        EngineFactory.register("dummy", DummyEngine, lambda cfg: {})
        assert "dummy" in EngineFactory.available()

        config = ExtractionConfig(provider="dummy")
        engine = EngineFactory.create_from_config(config)
        assert isinstance(engine, DummyEngine)

        # cleanup so other tests are unaffected
        del EngineFactory._REGISTRY["dummy"]
