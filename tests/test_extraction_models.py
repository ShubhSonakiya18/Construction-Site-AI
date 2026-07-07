"""
test_extraction_models.py — Tests for ExtractionResult and ExtractionMetadata.
"""
import json
import pytest

from extraction.models.extraction_result import ExtractionMetadata, ExtractionResult


def _make_meta(**kwargs) -> ExtractionMetadata:
    defaults = dict(
        model="llama-3.3-70b-versatile",
        engine_endpoint="https://api.groq.com",
        prompt_tokens=100,
        completion_tokens=200,
        duration_seconds=1.5,
        attempts=1,
        transcript_length=42,
        json_repair_applied=False,
    )
    defaults.update(kwargs)
    return ExtractionMetadata(**defaults)


def _make_result(**kwargs) -> ExtractionResult:
    defaults = dict(
        success=True,
        audio_id="test-id-123",
        extracted_log={"current_stage": "framing", "log_date": "2024-01-15"},
        validation_passed=True,
        validation_errors=[],
        validation_warnings=[],
        field_confidences={"current_stage": 0.9, "log_date": 0.9},
        errors=[],
        warnings=[],
        metadata=_make_meta(),
    )
    defaults.update(kwargs)
    return ExtractionResult(**defaults)


class TestExtractionMetadata:
    def test_construction(self):
        meta = _make_meta()
        assert meta.model == "llama-3.3-70b-versatile"
        assert meta.prompt_tokens == 100
        assert meta.json_repair_applied is False

    def test_repair_flag(self):
        meta = _make_meta(json_repair_applied=True)
        assert meta.json_repair_applied is True


class TestExtractionResult:
    def test_success_result(self):
        r = _make_result()
        assert r.success is True
        assert r.audio_id == "test-id-123"
        assert r.extracted_log["current_stage"] == "framing"

    def test_to_dict_structure(self):
        r = _make_result()
        d = r.to_dict()
        assert d["success"] is True
        assert "extracted_log" in d
        assert "validation" in d
        assert "field_confidences" in d
        assert "metadata" in d
        assert d["metadata"]["model"] == "llama-3.3-70b-versatile"

    def test_to_json_is_valid_json(self):
        r = _make_result()
        raw = r.to_json()
        parsed = json.loads(raw)
        assert parsed["success"] is True

    def test_to_json_indent(self):
        r = _make_result()
        raw = r.to_json(indent=4)
        assert "    " in raw  # 4-space indent

    def test_failure_factory(self):
        r = ExtractionResult.failure(
            errors=["engine not available"],
            audio_id="abc-123",
        )
        assert r.success is False
        assert r.errors == ["engine not available"]
        assert r.audio_id == "abc-123"
        assert r.extracted_log is None
        assert r.validation_passed is False

    def test_failure_generates_audio_id_when_none(self):
        r = ExtractionResult.failure(errors=["fail"])
        assert r.audio_id is not None
        assert len(r.audio_id) > 0

    def test_failure_to_dict(self):
        r = ExtractionResult.failure(errors=["bad json"])
        d = r.to_dict()
        assert d["success"] is False
        assert d["extracted_log"] is None

    def test_current_stage_accessor(self):
        r = _make_result()
        assert r.current_stage() == "framing"

    def test_current_stage_none_on_failure(self):
        r = ExtractionResult.failure(errors=["fail"])
        assert r.current_stage() is None

    def test_worker_count_accessor(self):
        r = _make_result(
            extracted_log={
                "current_stage": "framing",
                "workforce": {"total_workers_present": 5},
            }
        )
        assert r.worker_count() == 5

    def test_worker_count_none_when_missing(self):
        r = _make_result(extracted_log={"current_stage": "framing"})
        assert r.worker_count() is None

    def test_plain_text_from_work_completed(self):
        r = _make_result(
            extracted_log={
                "work_completed": [
                    {"task_description": "Poured foundation slab"},
                    {"task_description": "Set anchor bolts"},
                ]
            }
        )
        text = r.plain_text()
        assert "Poured foundation slab" in text
        assert "Set anchor bolts" in text

    def test_plain_text_empty_on_failure(self):
        r = ExtractionResult.failure(errors=["fail"])
        assert r.plain_text() == ""

    def test_metadata_none_on_failure(self):
        r = ExtractionResult.failure(errors=["fail"])
        assert r.metadata is None

    def test_to_dict_metadata_none(self):
        r = ExtractionResult.failure(errors=["fail"])
        assert r.to_dict()["metadata"] is None
