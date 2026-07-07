"""
extract.py — CLI entry point for the AI Extraction Framework.

Usage:
    # Extract from a SpeechProcessingResult JSON file (Sprint 3 output)
    python extract.py data/transcripts/raw/recording.json

    # Extract from raw transcript text
    python extract.py --text "Today we had 6 workers. We poured the foundation slab."

    # Check engine availability without extracting
    python extract.py --check

    # Override model
    python extract.py recording.json --model mixtral-8x7b-32768

    # Save output to file
    python extract.py recording.json --output data/extracted/result.json
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("extract")


def _load_speech_result_json(path: str) -> str:
    """Read transcript text from a SpeechProcessingResult JSON file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    transcript = data.get("transcript")
    if transcript and isinstance(transcript, dict):
        text = transcript.get("full_text", "") or transcript.get("text", "")
        if text:
            return text
    return data.get("plain_text", "") or data.get("text", "")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract a ConstructionDailyLog from a voice transcript.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "input_file",
        nargs="?",
        help="Path to a SpeechProcessingResult JSON file (Sprint 3 output).",
    )
    parser.add_argument(
        "--text",
        metavar="TRANSCRIPT",
        help="Extract from a raw transcript string instead of a file.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check if the extraction engine is available, then exit.",
    )
    parser.add_argument(
        "--provider",
        default=None,
        help="LLM provider override (default: from EXTRACTION_PROVIDER env var, currently 'groq').",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model name override (e.g. mixtral-8x7b-32768).",
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        help="Save extraction result JSON to this file.",
    )
    parser.add_argument(
        "--log-date",
        metavar="YYYY-MM-DD",
        help="Log date to embed in the extracted record.",
    )

    args = parser.parse_args()

    from extraction import ExtractionConfig, ExtractionPipeline

    # Build config with any CLI overrides
    config = ExtractionConfig.from_env()
    if args.provider:
        config.provider = args.provider
    if args.model:
        # Apply model override to the active provider's config sub-object
        provider_cfg = getattr(config, config.provider, None)
        if provider_cfg is not None and hasattr(provider_cfg, "model"):
            provider_cfg.model = args.model

    # --check mode
    if args.check:
        pipeline = ExtractionPipeline(config=config)
        available = pipeline._engine.is_available()
        if available:
            print(
                f"Engine available: provider={config.provider} "
                f"model={pipeline._engine.model_name} "
                f"endpoint={pipeline._engine.host}"
            )
            return 0
        else:
            print(
                f"Engine NOT available.\n"
                f"Provider: {config.provider}\n"
                f"Check that GROQ_API_KEY is set in your .env file."
            )
            return 1

    # Resolve transcript text
    transcript_text = ""
    audio_id = None

    if args.text:
        transcript_text = args.text
    elif args.input_file:
        input_path = Path(args.input_file)
        if not input_path.exists():
            logger.error("File not found: %s", args.input_file)
            return 1
        if input_path.suffix.lower() == ".json":
            try:
                transcript_text = _load_speech_result_json(args.input_file)
                audio_id = input_path.stem
            except Exception as exc:
                logger.error("Could not read speech result JSON: %s", exc)
                return 1
        else:
            transcript_text = input_path.read_text(encoding="utf-8")
    else:
        parser.print_help()
        return 1

    if not transcript_text.strip():
        logger.error(
            "No transcript text found. The speech result may have an empty transcript "
            "(sine-tone sample files contain no speech)."
        )
        return 1

    # Run extraction
    pipeline = ExtractionPipeline(config=config)
    logger.info("Extracting from transcript (%d chars)...", len(transcript_text))

    result = pipeline.extract(
        transcript_text=transcript_text,
        audio_id=audio_id,
        log_date=args.log_date,
    )

    # Output
    output_json = result.to_json(indent=2)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_json, encoding="utf-8")
        logger.info("Saved to: %s", args.output)
    else:
        print(output_json)

    if result.success:
        logger.info(
            "Extraction successful. Stage: %s | Workers: %s | Validation: %s",
            result.current_stage(),
            result.worker_count(),
            "PASSED" if result.validation_passed else "FAILED",
        )
        if result.validation_errors:
            for err in result.validation_errors:
                logger.warning("Validation error: %s", err)
        return 0
    else:
        for err in result.errors:
            logger.error("%s", err)
        return 1


if __name__ == "__main__":
    sys.exit(main())
