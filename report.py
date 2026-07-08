"""
report.py — Sprint 5 CLI entry point for AI generation services.

Accepts a ConstructionDailyLog (as ExtractionResult JSON or raw log JSON)
and generates all 4 AI outputs: daily report, customer update, safety talk,
material reminder.

Usage examples:
    # Generate all outputs from an extraction result file
    python report.py data/extracted/result.json

    # Generate all outputs from a raw log JSON file
    python report.py data/extracted/result.json --output data/generated/

    # Generate a single service only
    python report.py data/extracted/result.json --service daily_report

    # Read log from stdin (pipe from extract.py)
    python extract.py audio.wav --output - | python report.py --stdin

    # Check if Groq API is available
    python report.py --check
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# ── Logging setup (before any module imports that log) ────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("report")


def _load_env() -> None:
    """Load .env file if present (stdlib only — no python-dotenv required)."""
    env_path = Path(".env")
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _load_log(input_path: str) -> dict:
    """Load a ConstructionDailyLog from an ExtractionResult or raw log JSON file."""
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))

    # ExtractionResult wraps the log under extracted_log
    if "extracted_log" in raw and isinstance(raw["extracted_log"], dict):
        log = raw["extracted_log"]
        logger.info("Loaded ConstructionDailyLog from ExtractionResult")
    elif "log_id" in raw and "log_date" in raw:
        log = raw
        logger.info("Loaded raw ConstructionDailyLog")
    else:
        raise ValueError(
            "Input JSON must be an ExtractionResult (with 'extracted_log' key) "
            "or a raw ConstructionDailyLog (with 'log_id' and 'log_date' keys)"
        )

    return log


def _save_outputs(result, output_dir: str) -> None:
    """Save each service output as a separate file."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    log_date = result.log_date.replace("-", "") if result.log_date else "unknown"

    files = {
        "daily_report": (result.daily_report, f"daily_report_{log_date}.md"),
        "customer_update": (result.customer_update, f"customer_update_{log_date}.txt"),
        "safety_talk": (result.safety_talk, f"safety_talk_{log_date}.md"),
        "material_reminder": (result.material_reminder, f"material_reminder_{log_date}.md"),
    }

    for name, (output, filename) in files.items():
        file_path = out / filename
        if output.success and output.content:
            file_path.write_text(output.content, encoding="utf-8")
            logger.info("Saved %s → %s", name, file_path)
        else:
            logger.warning("Skipped %s (success=%s errors=%s)", name, output.success, output.errors)

    summary_path = out / f"generation_result_{log_date}.json"
    summary_path.write_text(result.to_json(), encoding="utf-8")
    logger.info("Saved full result → %s", summary_path)


def main() -> int:
    _load_env()

    parser = argparse.ArgumentParser(
        description="Sprint 5 AI Generation Services — ConstructionDailyLog → 4 outputs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "input_file",
        nargs="?",
        help="Path to ExtractionResult JSON or raw ConstructionDailyLog JSON",
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="Read JSON from stdin",
    )
    parser.add_argument(
        "--service",
        choices=["daily_report", "customer_update", "safety_talk", "material_reminder"],
        help="Generate a single service output (default: all four)",
    )
    parser.add_argument(
        "--output",
        default="data/generated",
        help="Output directory for generated files (default: data/generated)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check Groq API availability and exit",
    )
    parser.add_argument(
        "--provider",
        default=None,
        help="LLM provider override (default: from GENERATION_PROVIDER env var)",
    )

    args = parser.parse_args()

    from generation.manager import AIServiceManager
    from generation.config import GenerationConfig
    from generation.models.outputs import ServiceType

    config = GenerationConfig.from_env()
    if args.provider:
        config.provider = args.provider

    manager = AIServiceManager(config=config)

    if args.check:
        available = manager.is_available()
        status = "AVAILABLE" if available else "UNAVAILABLE"
        print(f"Groq API: {status}")
        print(f"Model: {config.groq.model}")
        print(f"API key set: {'Yes' if config.groq.api_key else 'No'}")
        return 0 if available else 1

    # Load input
    if args.stdin:
        raw = json.loads(sys.stdin.read())
        if "extracted_log" in raw:
            log = raw["extracted_log"]
        else:
            log = raw
    elif args.input_file:
        log = _load_log(args.input_file)
    else:
        parser.print_help()
        return 1

    # Generate
    if args.service:
        service_type = ServiceType(args.service)
        output = manager.generate(service_type, log)
        if output.success:
            print(output.content)
            return 0
        else:
            for err in output.errors:
                print(f"ERROR: {err}", file=sys.stderr)
            return 1
    else:
        result = manager.generate_all(log)

        # Print summary to stdout
        successes = sum(1 for o in [
            result.daily_report, result.customer_update,
            result.safety_talk, result.material_reminder,
        ] if o.success)
        print(f"\nGeneration complete: {successes}/4 services succeeded")
        for service_output in [
            result.daily_report, result.customer_update,
            result.safety_talk, result.material_reminder,
        ]:
            status = "OK" if service_output.success else "FAIL"
            tokens = (
                service_output.metadata.total_tokens
                if service_output.metadata else 0
            )
            print(f"  [{status}] {service_output.service_type.value} ({tokens} tokens)")

        if not result.success:
            for err in result.errors:
                print(f"  ERROR: {err}", file=sys.stderr)
            return 1

        _save_outputs(result, args.output)
        return 0


if __name__ == "__main__":
    sys.exit(main())
