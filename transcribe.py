"""
transcribe.py — CLI entry point for the Speech Processing Framework.

Usage
-----
    # Single file
    python transcribe.py recording.wav

    # Single file with explicit output directory
    python transcribe.py recording.wav --output-dir data/transcripts/raw

    # Batch mode (all WAV files in a directory)
    python transcribe.py --batch data/sample_audio/ --output-dir data/transcripts/raw

    # Use a larger model
    python transcribe.py recording.wav --model large-v3

    # Dry run (validate only, no transcription)
    python transcribe.py recording.wav --dry-run

    # Export as verbose text (with timestamps)
    python transcribe.py recording.wav --format verbose-text

    # GPU inference
    python transcribe.py recording.wav --device cuda --compute-type float16

Environment variables (override defaults without passing flags):
    SPEECH_WHISPER_MODEL_SIZE   = tiny|base|small|medium|large-v3
    SPEECH_WHISPER_DEVICE       = cpu|cuda|auto
    SPEECH_WHISPER_COMPUTE_TYPE = int8|float16|float32
    SPEECH_WHISPER_LANGUAGE     = en  (empty = auto-detect)
    SPEECH_MAX_FILE_SIZE_MB     = 500
    SPEECH_ENABLE_NOISE_REDUCTION = true|false
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

# ── Logging setup ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("transcribe")

# ── Supported export formats ───────────────────────────────────────────────────
_FORMATS = ("json", "text", "verbose-text", "jsonl")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="transcribe",
        description="Transcribe audio files using the Speech Processing Framework.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "audio",
        nargs="?",
        help="Path to a single audio file.",
    )
    parser.add_argument(
        "--batch",
        metavar="DIR",
        help="Transcribe all supported audio files in DIR (batch mode).",
    )
    parser.add_argument(
        "--output-dir", "-o",
        metavar="DIR",
        default="data/transcripts/raw",
        help="Directory for output files. (default: data/transcripts/raw)",
    )
    parser.add_argument(
        "--format", "-f",
        choices=_FORMATS,
        default="json",
        help="Output format. (default: json)",
    )
    parser.add_argument(
        "--model", "-m",
        choices=["tiny", "base", "small", "medium", "large-v3"],
        default=None,
        help="Whisper model size. (default: base, or SPEECH_WHISPER_MODEL_SIZE env var)",
    )
    parser.add_argument(
        "--device",
        choices=["cpu", "cuda", "auto"],
        default=None,
        help="Compute device. (default: cpu)",
    )
    parser.add_argument(
        "--compute-type",
        choices=["int8", "float16", "float32"],
        default=None,
        help="Compute type. (default: int8)",
    )
    parser.add_argument(
        "--language",
        default=None,
        help="Force language (e.g. 'en'). Auto-detected if not set.",
    )
    parser.add_argument(
        "--noise-reduction",
        action="store_true",
        default=False,
        help="Enable noise reduction (requires noisereduce package).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate audio only; do not transcribe.",
    )
    parser.add_argument(
        "--project-id",
        default=None,
        help="Optional project identifier embedded in metadata.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging.",
    )

    return parser.parse_args()


def _build_config(args: argparse.Namespace):
    """Build SpeechProcessingConfig from CLI args + environment variables."""
    from speech.config import (
        PreprocessingConfig,
        SpeechProcessingConfig,
        WhisperConfig,
    )

    base = SpeechProcessingConfig.from_env()

    if args.model:
        base.whisper.model_size = args.model
    if args.device:
        base.whisper.device = args.device
    if args.compute_type:
        base.whisper.compute_type = args.compute_type
    if args.language:
        base.whisper.language = args.language
    if args.noise_reduction:
        base.preprocessing.enable_noise_reduction = True

    return base


def _build_exporter(fmt: str):
    """Return the appropriate exporter instance for the requested format."""
    from speech.exporters import JSONExporter, JSONLExporter, TextExporter, VerboseTextExporter
    if fmt == "json":
        return JSONExporter()
    if fmt == "jsonl":
        return JSONLExporter()
    if fmt == "text":
        return TextExporter()
    if fmt == "verbose-text":
        return VerboseTextExporter()
    raise ValueError(f"Unknown format: {fmt}")


def _output_path(audio_path: str, output_dir: str, exporter) -> str:
    stem = Path(audio_path).stem
    return str(Path(output_dir) / f"{stem}.{exporter.extension}")


def _print_result_summary(result, elapsed: float) -> None:
    """Print a compact one-line summary after processing."""
    if result.success and result.transcript:
        tr = result.transcript
        conf = tr.avg_confidence()
        words = tr.word_count()
        dur = result.duration_seconds()
        print(
            f"  OK  {result.audio_id[:8]}  "
            f"{dur:.1f}s audio | {words} words | conf {conf:.0%} | "
            f"took {elapsed:.1f}s"
        )
    else:
        errors = "; ".join(result.errors)
        print(f"  XX  {result.audio_id[:8]}  FAILED: {errors}")


def _collect_batch_files(batch_dir: str) -> list[str]:
    from speech.utils.constants import SUPPORTED_AUDIO_FORMATS
    d = Path(batch_dir)
    if not d.is_dir():
        print(f"Error: --batch path is not a directory: {batch_dir}", file=sys.stderr)
        sys.exit(1)

    files = []
    for ext in SUPPORTED_AUDIO_FORMATS:
        files.extend(d.glob(f"*.{ext}"))
        files.extend(d.glob(f"*.{ext.upper()}"))

    return sorted(str(f) for f in set(files))


def _run_dry(audio_path: str, config) -> None:
    """Validate only; print result and exit."""
    from speech.validators.audio_validator import AudioValidator
    validator = AudioValidator(config.validation)
    result = validator.validate(audio_path)
    print(f"Validation: {'PASS' if result.is_valid else 'FAIL'}")
    for e in result.errors:
        print(f"  Error  : {e}")
    for w in result.warnings:
        print(f"  Warning: {w}")
    if result.audio_info:
        ai = result.audio_info
        print(f"  Format : {ai.format}")
        print(f"  Duration: {ai.duration_seconds:.1f}s")
        print(f"  Sample rate: {ai.sample_rate} Hz")
        print(f"  Channels: {ai.channels}")
    sys.exit(0 if result.is_valid else 1)


def main() -> None:
    args = _parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)

    if not args.audio and not args.batch:
        print("Error: provide an audio file or --batch DIR", file=sys.stderr)
        sys.exit(1)

    config = _build_config(args)

    # Dry run — validate only
    if args.dry_run:
        target = args.audio or (
            _collect_batch_files(args.batch)[0] if args.batch else None
        )
        if not target:
            print("Error: no audio file to validate", file=sys.stderr)
            sys.exit(1)
        _run_dry(target, config)
        return

    from speech.pipeline import SpeechProcessingPipeline
    exporter = _build_exporter(args.format)
    output_dir = args.output_dir
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Progress callback for verbose mode
    def _progress(stage: str, pct: float) -> None:
        if args.verbose:
            print(f"  ... {stage} ({pct:.0f}%)", flush=True)

    config.progress_callback = _progress if args.verbose else None
    pipeline = SpeechProcessingPipeline(config=config)

    if args.batch:
        files = _collect_batch_files(args.batch)
        if not files:
            print(f"No supported audio files found in: {args.batch}")
            sys.exit(0)

        print(f"Batch: {len(files)} file(s) -> {output_dir}")
        succeeded = 0
        failed = 0

        for audio_path in files:
            t0 = time.perf_counter()
            result = pipeline.process(
                audio_path=audio_path,
                project_id=args.project_id,
            )
            elapsed = time.perf_counter() - t0
            _print_result_summary(result, elapsed)

            out_path = _output_path(audio_path, output_dir, exporter)
            try:
                exporter.export(result, out_path)
            except Exception as exc:
                print(f"  Export failed: {exc}", file=sys.stderr)

            if result.success:
                succeeded += 1
            else:
                failed += 1

        print(f"\nBatch complete: {succeeded} succeeded, {failed} failed.")
        sys.exit(0 if failed == 0 else 1)

    else:
        # Single file
        t0 = time.perf_counter()
        result = pipeline.process(
            audio_path=args.audio,
            project_id=args.project_id,
        )
        elapsed = time.perf_counter() - t0
        _print_result_summary(result, elapsed)

        out_path = _output_path(args.audio, output_dir, exporter)
        try:
            written = exporter.export(result, out_path)
            print(f"  Exported: {written}")
        except Exception as exc:
            print(f"  Export failed: {exc}", file=sys.stderr)

        if result.transcript and not args.verbose:
            print()
            print(result.plain_text())

        sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()
