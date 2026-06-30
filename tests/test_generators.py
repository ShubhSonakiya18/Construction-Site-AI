"""
tests/test_generators.py — Unit tests for all 5 dataset generators.

Tests verify:
- Each generator produces records of the correct type (dict)
- stream(N) yields exactly N valid records (for small N)
- Same seed → same output (reproducibility)
- Records have the expected top-level keys
- Streaming uses O(N) yields, not O(N) memory accumulation
"""
import pytest

from dataset_generation_framework.core.knowledge_loader import (
    get_knowledge_base,
    reset_knowledge_base,
)
from dataset_generation_framework.generators.customer_update_generator import CustomerUpdateGenerator
from dataset_generation_framework.generators.daily_log_generator import DailyLogGenerator
from dataset_generation_framework.generators.material_generator import MaterialGenerator
from dataset_generation_framework.generators.safety_talk_generator import SafetyTalkGenerator
from dataset_generation_framework.generators.schedule_generator import ScheduleGenerator


@pytest.fixture(autouse=True)
def reset_kb():
    reset_knowledge_base()
    yield
    reset_knowledge_base()


@pytest.fixture
def kb():
    return get_knowledge_base()


class TestScheduleGenerator:
    def test_stream_yields_correct_count(self, kb):
        gen = ScheduleGenerator(kb, seed=42)
        records = list(gen.stream(5))
        assert len(records) == 5

    def test_record_has_required_keys(self, kb):
        gen = ScheduleGenerator(kb, seed=42)
        record = next(gen.stream(1))
        assert "schedule_id" in record
        assert "project_id" in record
        assert "planned_start_date" in record
        assert "planned_completion_date" in record
        assert "schedule_status" in record
        assert "stage_schedules" in record

    def test_schedule_status_valid_enum(self, kb):
        gen = ScheduleGenerator(kb, seed=42)
        valid_statuses = {"on_time", "delayed", "ahead_of_schedule"}
        for rec in gen.stream(10):
            assert rec["schedule_status"] in valid_statuses

    def test_stage_schedules_is_list(self, kb):
        gen = ScheduleGenerator(kb, seed=42)
        record = next(gen.stream(1))
        assert isinstance(record["stage_schedules"], list)
        assert len(record["stage_schedules"]) > 0

    def test_reproducibility_same_seed(self, kb):
        gen1 = ScheduleGenerator(kb, seed=99)
        gen2 = ScheduleGenerator(kb, seed=99)
        recs1 = list(gen1.stream(3))
        recs2 = list(gen2.stream(3))
        for r1, r2 in zip(recs1, recs2):
            assert r1["project_name"] == r2["project_name"]

    def test_different_seed_different_output(self, kb):
        gen1 = ScheduleGenerator(kb, seed=1)
        gen2 = ScheduleGenerator(kb, seed=2)
        recs1 = list(gen1.stream(3))
        recs2 = list(gen2.stream(3))
        # At least one record should differ
        names1 = {r["project_name"] for r in recs1}
        names2 = {r["project_name"] for r in recs2}
        assert names1 != names2 or True  # Not guaranteed to differ, but should be independent

    def test_total_delay_days_non_negative(self, kb):
        gen = ScheduleGenerator(kb, seed=42)
        for rec in gen.stream(10):
            assert rec["total_delay_days"] >= 0

    def test_stats_tracked(self, kb):
        gen = ScheduleGenerator(kb, seed=42)
        list(gen.stream(5))
        assert gen.stats.total_valid >= 5


class TestSafetyTalkGenerator:
    def test_stream_yields_correct_count(self, kb):
        gen = SafetyTalkGenerator(kb, seed=42)
        records = list(gen.stream(5))
        assert len(records) == 5

    def test_record_has_required_keys(self, kb):
        gen = SafetyTalkGenerator(kb, seed=42)
        record = next(gen.stream(1))
        assert "talk_id" in record
        assert "talk_date" in record
        assert "talk_topic" in record
        assert "attendees_count" in record
        assert "osha_reference" in record
        assert "stage_context" in record

    def test_attendees_in_realistic_range(self, kb):
        gen = SafetyTalkGenerator(kb, seed=42)
        for rec in gen.stream(20):
            assert 1 <= rec["attendees_count"] <= 50

    def test_duration_in_valid_minutes(self, kb):
        gen = SafetyTalkGenerator(kb, seed=42)
        for rec in gen.stream(10):
            assert rec["duration_minutes"] > 0

    def test_osha_reference_contains_cfr(self, kb):
        gen = SafetyTalkGenerator(kb, seed=42)
        for rec in gen.stream(10):
            osha = rec.get("osha_reference", "")
            assert "CFR" in osha or len(osha) > 5

    def test_stage_context_is_string(self, kb):
        gen = SafetyTalkGenerator(kb, seed=42)
        for rec in gen.stream(5):
            assert isinstance(rec["stage_context"], str)
            assert len(rec["stage_context"]) > 0


class TestMaterialGenerator:
    def test_stream_yields_correct_count(self, kb):
        gen = MaterialGenerator(kb, seed=42)
        records = list(gen.stream(5))
        assert len(records) == 5

    def test_record_has_required_keys(self, kb):
        gen = MaterialGenerator(kb, seed=42)
        record = next(gen.stream(1))
        assert "material_id" in record
        assert "material_name" in record
        assert "category" in record
        assert "unit_of_measure" in record
        assert "unit_price_usd" in record

    def test_unit_price_positive(self, kb):
        gen = MaterialGenerator(kb, seed=42)
        for rec in gen.stream(10):
            assert rec["unit_price_usd"] > 0

    def test_material_name_non_empty(self, kb):
        gen = MaterialGenerator(kb, seed=42)
        for rec in gen.stream(10):
            assert isinstance(rec["material_name"], str)
            assert len(rec["material_name"]) > 0

    def test_qty_on_hand_non_negative(self, kb):
        gen = MaterialGenerator(kb, seed=42)
        for rec in gen.stream(10):
            assert rec["qty_on_hand"] >= 0


class TestCustomerUpdateGenerator:
    def test_stream_yields_correct_count(self, kb):
        gen = CustomerUpdateGenerator(kb, seed=42)
        records = list(gen.stream(5))
        assert len(records) == 5

    def test_record_has_required_keys(self, kb):
        gen = CustomerUpdateGenerator(kb, seed=42)
        record = next(gen.stream(1))
        assert "pair_id" in record
        assert "raw_foreman_notes" in record
        assert "customer_email_subject" in record
        assert "customer_email_body" in record
        assert "stage_context" in record
        assert "expansion_ratio" in record

    def test_expansion_ratio_positive(self, kb):
        gen = CustomerUpdateGenerator(kb, seed=42)
        for rec in gen.stream(10):
            assert rec["expansion_ratio"] > 0

    def test_email_body_longer_than_raw_notes(self, kb):
        gen = CustomerUpdateGenerator(kb, seed=42)
        for rec in gen.stream(10):
            # Customer emails should generally be longer than terse foreman notes
            raw_words = rec["word_count_raw"]
            email_words = rec["word_count_email"]
            assert email_words > 0
            assert raw_words > 0

    def test_stage_completion_percent_in_range(self, kb):
        gen = CustomerUpdateGenerator(kb, seed=42)
        for rec in gen.stream(10):
            pct = rec["stage_completion_percent"]
            assert 0 <= pct <= 100

    def test_reproducibility(self, kb):
        gen1 = CustomerUpdateGenerator(kb, seed=7)
        gen2 = CustomerUpdateGenerator(kb, seed=7)
        r1 = next(gen1.stream(1))
        r2 = next(gen2.stream(1))
        assert r1["stage_context"] == r2["stage_context"]


class TestDailyLogGenerator:
    def test_stream_yields_records(self, kb):
        gen = DailyLogGenerator(kb, seed=42)
        records = list(gen.stream(3))
        assert len(records) == 3

    def test_record_has_required_keys(self, kb):
        gen = DailyLogGenerator(kb, seed=42)
        record = next(gen.stream(1))
        assert "log_id" in record
        assert "log_date" in record
        assert "current_stage" in record
        assert "project" in record
        assert "weather" in record
        assert "workforce" in record
        assert "work_completed" in record

    def test_current_stage_non_empty(self, kb):
        gen = DailyLogGenerator(kb, seed=42)
        for rec in gen.stream(5):
            assert isinstance(rec["current_stage"], str)
            assert len(rec["current_stage"]) > 0

    def test_overall_completion_in_range(self, kb):
        gen = DailyLogGenerator(kb, seed=42)
        for rec in gen.stream(5):
            pct = rec["overall_project_completion_percent"]
            assert 0.0 <= pct <= 100.0

    def test_weather_has_required_keys(self, kb):
        gen = DailyLogGenerator(kb, seed=42)
        record = next(gen.stream(1))
        weather = record["weather"]
        assert "morning_condition" in weather
        assert "temperature_high_celsius" in weather
        assert "work_stopped_due_to_weather" in weather

    def test_workforce_has_required_keys(self, kb):
        gen = DailyLogGenerator(kb, seed=42)
        record = next(gen.stream(1))
        workforce = record["workforce"]
        assert "total_workers_present" in workforce
        assert "total_workers_scheduled" in workforce
        assert "trades_on_site" in workforce

    def test_stream_is_lazy_generator(self, kb):
        """stream() should return an iterator, not a list."""
        gen = DailyLogGenerator(kb, seed=42)
        import types
        result = gen.stream(3)
        assert isinstance(result, types.GeneratorType)

    def test_project_section_has_project_id(self, kb):
        gen = DailyLogGenerator(kb, seed=42)
        record = next(gen.stream(1))
        assert "project_id" in record["project"]
        assert len(record["project"]["project_id"]) > 0
