"""
test_json_repairer.py — Tests for the JSON repair/extraction utility.
"""
import pytest

from extraction.postprocessors.json_repairer import JSONRepairError, repair_json


class TestRepairJson:
    def test_clean_json_no_repair(self):
        raw = '{"current_stage": "framing", "log_date": "2024-01-15"}'
        result, repaired = repair_json(raw)
        assert result == {"current_stage": "framing", "log_date": "2024-01-15"}
        assert repaired is False

    def test_clean_json_with_whitespace(self):
        raw = '  \n  {"a": 1}  \n  '
        result, repaired = repair_json(raw)
        assert result == {"a": 1}
        assert repaired is False

    def test_json_in_markdown_fence(self):
        raw = '```json\n{"current_stage": "foundation"}\n```'
        result, repaired = repair_json(raw)
        assert result["current_stage"] == "foundation"
        assert repaired is True

    def test_json_in_plain_fence(self):
        raw = '```\n{"current_stage": "framing"}\n```'
        result, repaired = repair_json(raw)
        assert result["current_stage"] == "framing"
        assert repaired is True

    def test_json_embedded_in_text(self):
        raw = 'Here is the extracted log:\n{"current_stage": "roofing"}\nHope that helps!'
        result, repaired = repair_json(raw)
        assert result["current_stage"] == "roofing"
        assert repaired is True

    def test_empty_string_raises(self):
        with pytest.raises(JSONRepairError):
            repair_json("")

    def test_whitespace_only_raises(self):
        with pytest.raises(JSONRepairError):
            repair_json("   \n  ")

    def test_pure_text_raises(self):
        with pytest.raises(JSONRepairError):
            repair_json("This is just a sentence with no JSON.")

    def test_invalid_json_in_fence_raises(self):
        raw = "```json\n{not valid json\n```"
        with pytest.raises(JSONRepairError):
            repair_json(raw)

    def test_nested_json(self):
        raw = '{"workforce": {"total_workers_present": 5}, "current_stage": "framing"}'
        result, repaired = repair_json(raw)
        assert result["workforce"]["total_workers_present"] == 5
        assert repaired is False

    def test_json_with_null_values(self):
        raw = '{"current_stage": "framing", "log_date": null}'
        result, repaired = repair_json(raw)
        assert result["log_date"] is None
        assert repaired is False

    def test_json_with_arrays(self):
        raw = '{"work_completed": [{"task_description": "Poured slab"}]}'
        result, repaired = repair_json(raw)
        assert len(result["work_completed"]) == 1
        assert repaired is False

    def test_extraction_possible_false_flag(self):
        raw = '{"extraction_possible": false}'
        result, repaired = repair_json(raw)
        assert result["extraction_possible"] is False
        assert repaired is False

    def test_llm_explanation_then_json(self):
        raw = (
            "Based on the transcript, here is the extracted information:\n\n"
            '{"current_stage": "drywall", "workforce": {"total_workers_present": 3}}\n\n'
            "Please verify the above fields."
        )
        result, repaired = repair_json(raw)
        assert result["current_stage"] == "drywall"
        assert repaired is True
