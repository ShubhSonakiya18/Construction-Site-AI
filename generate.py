"""
generate.py — CLI entry point for the Synthetic Construction Data Generation Framework.

USAGE:
    python generate.py                        # Generate all datasets with default settings
    python generate.py --dataset daily_logs   # Generate only daily logs
    python generate.py --count 500 --seed 99  # Custom count and seed
    python generate.py --dry-run              # Validate framework without writing files

SCALING:
    To scale from 5,000 to 500,000 records, either:
      a) Change DAILY_LOG_COUNT in config.py (permanent)
      b) Pass --count 500000 on the CLI (one-time override)

OUTPUTS:
    datasets/exports/daily_logs_v1.jsonl       5,000 records (default)
    datasets/exports/project_schedules_v1.jsonl 1,000 records
    datasets/exports/customer_updates_v1.jsonl  1,000 records
    datasets/exports/safety_talks_v1.csv         200 records
    datasets/exports/materials_v1.csv            500 records
    datasets/exports/generation_report.json     statistics
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

# Ensure project root is on sys.path when run as a script
PROJECT_ROOT = Path(__file__).parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dataset_generation_framework.config import (
    CUSTOMER_UPDATE_COUNT,
    DAILY_LOG_COUNT,
    DEFAULT_SEED,
    EXPORTS_DIR,
    MATERIAL_COUNT,
    SAFETY_TALK_COUNT,
    SCHEDULE_COUNT,
)
from dataset_generation_framework.core.knowledge_loader import get_knowledge_base
from dataset_generation_framework.exporters.csv_exporter import CsvExporter
from dataset_generation_framework.exporters.jsonl_exporter import JsonlExporter
from dataset_generation_framework.generators.customer_update_generator import CustomerUpdateGenerator
from dataset_generation_framework.generators.daily_log_generator import DailyLogGenerator
from dataset_generation_framework.generators.material_generator import MaterialGenerator
from dataset_generation_framework.generators.safety_talk_generator import SafetyTalkGenerator
from dataset_generation_framework.generators.schedule_generator import ScheduleGenerator
from dataset_generation_framework.statistics.report_generator import StatisticsReport

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("generate")

DATASET_CHOICES = ["all", "daily_logs", "schedules", "customer_updates", "safety_talks", "materials"]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Synthetic Construction Data Generation Framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--dataset", "-d",
        choices=DATASET_CHOICES,
        default="all",
        help="Which dataset to generate (default: all)",
    )
    p.add_argument(
        "--count", "-n",
        type=int,
        default=None,
        help="Override the record count (applies to selected dataset only)",
    )
    p.add_argument(
        "--seed", "-s",
        type=int,
        default=DEFAULT_SEED,
        help=f"Random seed for reproducibility (default: {DEFAULT_SEED})",
    )
    p.add_argument(
        "--output-dir", "-o",
        type=Path,
        default=None,
        help="Override the output directory (default: datasets/exports/)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate framework setup without writing any files",
    )
    p.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )
    return p.parse_args()


def run_generation(args: argparse.Namespace) -> int:
    """
    Main generation loop. Returns exit code (0 = success, 1 = error).
    """
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    output_dir = args.output_dir or EXPORTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Loading knowledge base...")
    t0 = time.perf_counter()
    kb = get_knowledge_base()
    logger.info("Knowledge base loaded in %.2fs", time.perf_counter() - t0)

    if args.dry_run:
        logger.info("Dry run complete — framework validated. No files written.")
        return 0

    report = StatisticsReport()
    selected = args.dataset

    # ── Daily Logs ─────────────────────────────────────────────────────────────
    if selected in ("all", "daily_logs"):
        count = args.count if args.count is not None else DAILY_LOG_COUNT
        out   = output_dir / "daily_logs_v1.jsonl"
        logger.info("Generating %d daily logs -> %s", count, out)

        gen = DailyLogGenerator(kb, seed=args.seed)
        t0  = time.perf_counter()
        with JsonlExporter(out) as exp:
            for record in gen.stream(count):
                exp.write(record)

        elapsed = time.perf_counter() - t0
        logger.info("Daily logs done: %d records in %.1fs", exp.total_written, elapsed)
        report.add_generator_stats("daily_logs", gen.stats)
        report.add_file_stats("daily_logs", out)
        report.analyze_daily_logs(out)

    # ── Project Schedules ──────────────────────────────────────────────────────
    if selected in ("all", "schedules"):
        count = args.count if args.count is not None else SCHEDULE_COUNT
        out   = output_dir / "project_schedules_v1.jsonl"
        logger.info("Generating %d project schedules -> %s", count, out)

        gen = ScheduleGenerator(kb, seed=args.seed)
        t0  = time.perf_counter()
        with JsonlExporter(out) as exp:
            for record in gen.stream(count):
                exp.write(record)

        elapsed = time.perf_counter() - t0
        logger.info("Schedules done: %d records in %.1fs", exp.total_written, elapsed)
        report.add_generator_stats("schedules", gen.stats)
        report.add_file_stats("schedules", out)
        report.analyze_schedules(out)

    # ── Customer Updates ───────────────────────────────────────────────────────
    if selected in ("all", "customer_updates"):
        count = args.count if args.count is not None else CUSTOMER_UPDATE_COUNT
        out   = output_dir / "customer_updates_v1.jsonl"
        logger.info("Generating %d customer update pairs -> %s", count, out)

        gen = CustomerUpdateGenerator(kb, seed=args.seed)
        t0  = time.perf_counter()
        with JsonlExporter(out) as exp:
            for record in gen.stream(count):
                exp.write(record)

        elapsed = time.perf_counter() - t0
        logger.info("Customer updates done: %d records in %.1fs", exp.total_written, elapsed)
        report.add_generator_stats("customer_updates", gen.stats)
        report.add_file_stats("customer_updates", out)
        report.analyze_customer_updates(out)

    # ── Safety Talks ───────────────────────────────────────────────────────────
    if selected in ("all", "safety_talks"):
        count = args.count if args.count is not None else SAFETY_TALK_COUNT
        out   = output_dir / "safety_talks_v1.csv"
        logger.info("Generating %d safety talks -> %s", count, out)

        gen = SafetyTalkGenerator(kb, seed=args.seed)
        t0  = time.perf_counter()
        with CsvExporter(out) as exp:
            for record in gen.stream(count):
                exp.write(record)

        elapsed = time.perf_counter() - t0
        logger.info("Safety talks done: %d records in %.1fs", exp.total_written, elapsed)
        report.add_generator_stats("safety_talks", gen.stats)
        report.add_file_stats("safety_talks", out)

    # ── Materials ──────────────────────────────────────────────────────────────
    if selected in ("all", "materials"):
        count = args.count if args.count is not None else MATERIAL_COUNT
        out   = output_dir / "materials_v1.csv"
        logger.info("Generating %d materials -> %s", count, out)

        gen = MaterialGenerator(kb, seed=args.seed)
        t0  = time.perf_counter()
        with CsvExporter(out) as exp:
            for record in gen.stream(count):
                exp.write(record)

        elapsed = time.perf_counter() - t0
        logger.info("Materials done: %d records in %.1fs", exp.total_written, elapsed)
        report.add_generator_stats("materials", gen.stats)
        report.add_file_stats("materials", out)

    # ── Statistics Report ──────────────────────────────────────────────────────
    report_path = output_dir / "generation_report.json"
    report.save(report_path)
    report.print_summary()
    logger.info("Report saved: %s", report_path)

    return 0


def main() -> None:
    args = parse_args()
    try:
        code = run_generation(args)
        sys.exit(code)
    except KeyboardInterrupt:
        logger.info("Generation interrupted by user.")
        sys.exit(130)
    except Exception as exc:
        logger.exception("Fatal error during generation: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
