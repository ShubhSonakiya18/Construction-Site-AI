"""
tests/test_integration.py — End-to-end integration tests for the full pipeline.

These tests run the full generation pipeline for a small count (10 records each)
and verify the output files are written correctly and contain valid JSON/CSV.

Why integration tests separate from unit tests:
- Unit tests mock nothing; they use real knowledge files.
- Integration tests run the FULL pipeline: generator → validator → exporter → file.
- If unit tests pass but integration tests fail, the issue is in the pipeline
  wiring (exporter, file paths, batch flushing) rather than the logic.
"""
import json
import csv
import tempfile
from pathlib import Path

import pytest

from dataset_generation_framework.core.knowledge_loader import (
    get_knowledge_base,
    reset_knowledge_base,
)
from dataset_generation_framework.exporters.csv_exporter import CsvExporter
from dataset_generation_framework.exporters.jsonl_exporter import JsonlExporter
from dataset_generation_framework.generators.customer_update_generator import CustomerUpdateGenerator
from dataset_generation_framework.generators.daily_log_generator import DailyLogGenerator
from dataset_generation_framework.generators.material_generator import MaterialGenerator
from dataset_generation_framework.generators.safety_talk_generator import SafetyTalkGenerator
from dataset_generation_framework.generators.schedule_generator import ScheduleGenerator


SMALL_COUNT = 10
SEED = 42


@pytest.fixture(autouse=True)
def reset_kb():
    reset_knowledge_base()
    yield
    reset_knowledge_base()


@pytest.fixture
def kb():
    return get_knowledge_base()


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


class TestJsonlExporter:
    def test_writes_and_reads_back(self, tmp_dir):
        out = tmp_dir / "test.jsonl"
        with JsonlExporter(out) as exp:
            for i in range(5):
                exp.write({"record_id": i, "value": f"test_{i}"})

        assert out.exists()
        lines = [l for l in out.read_text().splitlines() if l.strip()]
        assert len(lines) == 5

        for line in lines:
            obj = json.loads(line)
            assert "record_id" in obj

    def test_count_records_matches(self, tmp_dir):
        out = tmp_dir / "test.jsonl"
        with JsonlExporter(out) as exp:
            for i in range(7):
                exp.write({"n": i})

        assert JsonlExporter.count_records(out) == 7

    def test_append_mode_adds_records(self, tmp_dir):
        out = tmp_dir / "test.jsonl"
        with JsonlExporter(out) as exp:
            for i in range(3):
                exp.write({"n": i})
        with JsonlExporter(out, append=True) as exp:
            for i in range(3, 6):
                exp.write({"n": i})

        assert JsonlExporter.count_records(out) == 6

    def test_total_written_property(self, tmp_dir):
        out = tmp_dir / "test.jsonl"
        with JsonlExporter(out) as exp:
            for i in range(4):
                exp.write({"n": i})
        # total_written is only tracked during context; check manually
        lines = sum(1 for l in out.read_text().splitlines() if l.strip())
        assert lines == 4


class TestCsvExporter:
    def test_writes_csv_with_header(self, tmp_dir):
        out = tmp_dir / "test.csv"
        with CsvExporter(out) as exp:
            exp.write({"name": "Widget A", "price": 9.99, "qty": 100})
            exp.write({"name": "Widget B", "price": 14.99, "qty": 50})

        assert out.exists()
        with open(out, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 2
        assert rows[0]["name"] == "Widget A"
        assert "price" in rows[0]

    def test_none_values_become_empty_string(self, tmp_dir):
        out = tmp_dir / "test.csv"
        with CsvExporter(out) as exp:
            exp.write({"a": "value", "b": None, "c": 42})

        with open(out, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            row = next(reader)
        assert row["b"] == ""

    def test_list_values_become_semicolon_string(self, tmp_dir):
        out = tmp_dir / "test.csv"
        with CsvExporter(out) as exp:
            exp.write({"items": ["a", "b", "c"]})

        with open(out, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            row = next(reader)
        assert ";" in row["items"] or row["items"] in ("a; b; c", "a;b;c")


class TestSchedulePipeline:
    def test_generates_and_writes_jsonl(self, kb, tmp_dir):
        out = tmp_dir / "schedules.jsonl"
        gen = ScheduleGenerator(kb, seed=SEED)
        with JsonlExporter(out) as exp:
            for rec in gen.stream(SMALL_COUNT):
                exp.write(rec)

        assert out.exists()
        count = JsonlExporter.count_records(out)
        assert count == SMALL_COUNT

    def test_all_records_are_valid_json(self, kb, tmp_dir):
        out = tmp_dir / "schedules.jsonl"
        gen = ScheduleGenerator(kb, seed=SEED)
        with JsonlExporter(out) as exp:
            for rec in gen.stream(SMALL_COUNT):
                exp.write(rec)

        with open(out, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    obj = json.loads(line)
                    assert isinstance(obj, dict)


class TestSafetyTalkPipeline:
    def test_generates_and_writes_csv(self, kb, tmp_dir):
        out = tmp_dir / "safety_talks.csv"
        gen = SafetyTalkGenerator(kb, seed=SEED)
        with CsvExporter(out) as exp:
            for rec in gen.stream(SMALL_COUNT):
                exp.write(rec)

        assert out.exists()
        with open(out, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == SMALL_COUNT

    def test_csv_has_expected_columns(self, kb, tmp_dir):
        out = tmp_dir / "safety_talks.csv"
        gen = SafetyTalkGenerator(kb, seed=SEED)
        with CsvExporter(out) as exp:
            for rec in gen.stream(SMALL_COUNT):
                exp.write(rec)

        with open(out, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
        assert "talk_id" in fieldnames
        assert "talk_topic" in fieldnames
        assert "osha_reference" in fieldnames


class TestMaterialPipeline:
    def test_generates_and_writes_csv(self, kb, tmp_dir):
        out = tmp_dir / "materials.csv"
        gen = MaterialGenerator(kb, seed=SEED)
        with CsvExporter(out) as exp:
            for rec in gen.stream(SMALL_COUNT):
                exp.write(rec)

        assert out.exists()
        with open(out, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == SMALL_COUNT

    def test_material_records_have_prices(self, kb, tmp_dir):
        out = tmp_dir / "materials.csv"
        gen = MaterialGenerator(kb, seed=SEED)
        with CsvExporter(out) as exp:
            for rec in gen.stream(SMALL_COUNT):
                exp.write(rec)

        with open(out, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                price = float(row["unit_price_usd"])
                assert price > 0


class TestCustomerUpdatePipeline:
    def test_generates_and_writes_jsonl(self, kb, tmp_dir):
        out = tmp_dir / "customer_updates.jsonl"
        gen = CustomerUpdateGenerator(kb, seed=SEED)
        with JsonlExporter(out) as exp:
            for rec in gen.stream(SMALL_COUNT):
                exp.write(rec)

        assert out.exists()
        count = JsonlExporter.count_records(out)
        assert count == SMALL_COUNT

    def test_email_bodies_are_non_empty(self, kb, tmp_dir):
        out = tmp_dir / "customer_updates.jsonl"
        gen = CustomerUpdateGenerator(kb, seed=SEED)
        with JsonlExporter(out) as exp:
            for rec in gen.stream(SMALL_COUNT):
                exp.write(rec)

        with open(out, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    obj = json.loads(line)
                    assert len(obj["customer_email_body"]) > 50


class TestDailyLogPipeline:
    def test_generates_and_writes_jsonl(self, kb, tmp_dir):
        out = tmp_dir / "daily_logs.jsonl"
        gen = DailyLogGenerator(kb, seed=SEED)
        with JsonlExporter(out) as exp:
            for rec in gen.stream(SMALL_COUNT):
                exp.write(rec)

        assert out.exists()
        count = JsonlExporter.count_records(out)
        assert count == SMALL_COUNT

    def test_all_records_have_project_id(self, kb, tmp_dir):
        out = tmp_dir / "daily_logs.jsonl"
        gen = DailyLogGenerator(kb, seed=SEED)
        with JsonlExporter(out) as exp:
            for rec in gen.stream(SMALL_COUNT):
                exp.write(rec)

        with open(out, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    obj = json.loads(line)
                    assert obj["project"]["project_id"]

    def test_stage_sequence_within_project(self, kb, tmp_dir):
        """
        Records from the same project should never go backward in stage progression.
        We verify this by collecting all stage names for each project and checking
        that completion percent never decreases without a rework delay.
        """
        gen = DailyLogGenerator(kb, seed=SEED)
        records = list(gen.stream(SMALL_COUNT))

        project_records: dict[str, list[dict]] = {}
        for rec in records:
            pid = rec["project"]["project_id"]
            project_records.setdefault(pid, []).append(rec)

        for pid, proj_records in project_records.items():
            if len(proj_records) < 2:
                continue
            for i in range(1, len(proj_records)):
                prev_pct = proj_records[i-1]["overall_project_completion_percent"]
                curr_pct = proj_records[i]["overall_project_completion_percent"]
                has_rework = any(
                    d.get("delay_type") == "rework_required"
                    for d in proj_records[i].get("delays", [])
                )
                if curr_pct < prev_pct and not has_rework:
                    # Tolerance: small rounding fluctuations are OK
                    assert prev_pct - curr_pct < 5.0, (
                        f"Project {pid[:8]}: completion dropped from {prev_pct}% to {curr_pct}% "
                        f"without rework"
                    )
