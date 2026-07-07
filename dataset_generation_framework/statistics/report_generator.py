"""
report_generator.py — Produces statistical summary reports after dataset generation.

WHY THIS MODULE EXISTS:
    After generating 5,000+ records, we need confidence that the dataset is:
    1. Internally consistent (distributions look realistic)
    2. Correct in volume (correct record counts per dataset)
    3. Representative (no stage is overrepresented or missing)

    This module reads completed datasets and computes summary statistics.
    It does NOT regenerate data — it analyzes what was written to disk.

REPORT STRUCTURE:
    - Per-dataset: count, file size, records/sec, validation pass rate
    - Daily logs: stage distribution, weather distribution, avg workers
    - Schedules: on_time/delayed ratio, avg delay days
    - Safety talks: topic distribution, stage coverage
    - Materials: category distribution, price ranges
    - Customer updates: stage coverage, avg expansion ratio
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dataset_generation_framework.config import (
    CUSTOMER_UPDATE_COUNT,
    DAILY_LOG_COUNT,
    EXPORTS_DIR,
    MATERIAL_COUNT,
    SAFETY_TALK_COUNT,
    SCHEDULE_COUNT,
    SCHEMA_VERSION,
)
from dataset_generation_framework.generators.base_generator import GeneratorStats

logger = logging.getLogger(__name__)


class StatisticsReport:
    """Aggregates statistics from all generator runs and exports."""

    def __init__(self) -> None:
        self.generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self.schema_version = SCHEMA_VERSION
        self.dataset_stats: dict[str, Any] = {}
        self.generator_stats: dict[str, dict] = {}
        self.content_stats: dict[str, Any] = {}
        self.validation_summary: dict[str, Any] = {}

    def add_generator_stats(self, dataset_name: str, stats: GeneratorStats) -> None:
        self.generator_stats[dataset_name] = stats.to_dict()

    def add_file_stats(self, dataset_name: str, file_path: Path) -> None:
        if not file_path.exists():
            logger.warning("File not found for stats: %s", file_path)
            return

        size_bytes = file_path.stat().st_size
        count = self._count_records(file_path)

        self.dataset_stats[dataset_name] = {
            "file_path": str(file_path),
            "file_size_mb": round(size_bytes / 1_048_576, 3),
            "record_count": count,
            "target_count": self._target_count(dataset_name),
            "count_match": count == self._target_count(dataset_name),
        }

    def analyze_daily_logs(self, file_path: Path) -> None:
        """Parse daily_logs JSONL for content statistics."""
        if not file_path.exists():
            return

        stage_counts: dict[str, int] = {}
        weather_counts: dict[str, int] = {}
        worker_totals: list[int] = []
        total = 0

        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                total += 1
                stage = rec.get("current_stage", "unknown")
                stage_counts[stage] = stage_counts.get(stage, 0) + 1
                weather = rec.get("weather", {}).get("morning_condition", "unknown")
                weather_counts[weather] = weather_counts.get(weather, 0) + 1
                workers = rec.get("workforce", {}).get("total_workers_present", 0)
                worker_totals.append(workers)

        self.content_stats["daily_logs"] = {
            "total_records": total,
            "unique_stages": len(stage_counts),
            "stage_distribution": dict(sorted(stage_counts.items(), key=lambda x: -x[1])),
            "weather_distribution": dict(sorted(weather_counts.items(), key=lambda x: -x[1])),
            "avg_workers_per_log": round(sum(worker_totals) / max(1, len(worker_totals)), 1),
            "rain_days_percent": round(
                (weather_counts.get("rainy", 0) + weather_counts.get("heavy_rain", 0))
                / max(1, total) * 100, 1
            ),
        }

    def analyze_schedules(self, file_path: Path) -> None:
        if not file_path.exists():
            return

        statuses: dict[str, int] = {}
        delays: list[int] = []
        total = 0

        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                total += 1
                s = rec.get("schedule_status", "unknown")
                statuses[s] = statuses.get(s, 0) + 1
                d = rec.get("total_delay_days", 0)
                if d:
                    delays.append(d)

        self.content_stats["schedules"] = {
            "total_records": total,
            "status_distribution": statuses,
            "avg_delay_days": round(sum(delays) / max(1, len(delays)), 1),
            "delayed_percent": round(statuses.get("delayed", 0) / max(1, total) * 100, 1),
        }

    def analyze_customer_updates(self, file_path: Path) -> None:
        if not file_path.exists():
            return

        stages: dict[str, int] = {}
        ratios: list[float] = []
        total = 0

        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                total += 1
                s = rec.get("stage_context", "unknown")
                stages[s] = stages.get(s, 0) + 1
                r = rec.get("expansion_ratio", 1.0)
                if r:
                    ratios.append(r)

        self.content_stats["customer_updates"] = {
            "total_records": total,
            "stage_coverage": len(stages),
            "stage_distribution": dict(sorted(stages.items(), key=lambda x: -x[1])),
            "avg_expansion_ratio": round(sum(ratios) / max(1, len(ratios)), 2),
        }

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "schema_version": self.schema_version,
            "target_counts": {
                "daily_logs": DAILY_LOG_COUNT,
                "schedules": SCHEDULE_COUNT,
                "customer_updates": CUSTOMER_UPDATE_COUNT,
                "safety_talks": SAFETY_TALK_COUNT,
                "materials": MATERIAL_COUNT,
            },
            "dataset_stats": self.dataset_stats,
            "generator_performance": self.generator_stats,
            "content_analysis": self.content_stats,
        }

    def print_summary(self) -> None:
        """Print a human-readable summary to stdout."""
        print("\n" + "=" * 65)
        print("  CONSTRUCTION SITE AI — DATASET GENERATION REPORT")
        print("=" * 65)
        print(f"  Generated at: {self.generated_at}")
        print()

        print("  DATASET VOLUMES")
        print("  " + "-" * 63)
        for name, stats in self.dataset_stats.items():
            count  = stats.get("record_count", 0)
            target = stats.get("target_count", 0)
            size   = stats.get("file_size_mb", 0)
            mark   = "OK" if stats.get("count_match") else "XX"
            print(f"  {mark} {name:<25} {count:>7,} / {target:>7,} records  ({size:.1f} MB)")
        print()

        print("  GENERATOR PERFORMANCE")
        print("  " + "-" * 63)
        for name, stats in self.generator_stats.items():
            rate    = stats.get("records_per_second", 0) or 0
            elapsed = stats.get("elapsed_seconds", 0) or 0
            prate   = stats.get("pass_rate_percent", 100)
            print(f"  {name:<30} {rate:>6.0f} rec/s  {elapsed:>6.1f}s  {prate:.1f}% pass")
        print()

        if "daily_logs" in self.content_stats:
            dl = self.content_stats["daily_logs"]
            print("  DAILY LOGS ANALYSIS")
            print("  " + "-" * 63)
            print(f"  Unique stages:      {dl.get('unique_stages', 0)}")
            print(f"  Avg workers/log:    {dl.get('avg_workers_per_log', 0)}")
            print(f"  Rain day rate:      {dl.get('rain_days_percent', 0)}%")
            print()

        if "schedules" in self.content_stats:
            sc = self.content_stats["schedules"]
            print("  SCHEDULES ANALYSIS")
            print("  " + "-" * 63)
            print(f"  Status:             {sc.get('status_distribution', {})}")
            print(f"  Avg delay days:     {sc.get('avg_delay_days', 0)}")
            print()

        print("=" * 65 + "\n")

    def save(self, output_path: Path) -> None:
        """Write full report as JSON."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)
        logger.info("Statistics report saved: %s", output_path)

    @staticmethod
    def _count_records(file_path: Path) -> int:
        suffix = file_path.suffix.lower()
        with open(file_path, "r", encoding="utf-8") as f:
            if suffix == ".jsonl":
                return sum(1 for line in f if line.strip())
            if suffix == ".csv":
                # Subtract 1 for header row
                return max(0, sum(1 for line in f if line.strip()) - 1)
        return 0

    @staticmethod
    def _target_count(dataset_name: str) -> int:
        mapping = {
            "daily_logs":       DAILY_LOG_COUNT,
            "schedules":        SCHEDULE_COUNT,
            "customer_updates": CUSTOMER_UPDATE_COUNT,
            "safety_talks":     SAFETY_TALK_COUNT,
            "materials":        MATERIAL_COUNT,
        }
        return mapping.get(dataset_name, 0)
