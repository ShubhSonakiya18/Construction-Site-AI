"""
speech/exporters/text_exporter.py — Export SpeechProcessingResult as plain text.

Two formats:
- TextExporter: simple transcript text only, one line per segment
- VerboseTextExporter: includes timestamps, confidence, metadata header

The plain text format is intended for:
- Human review of transcripts
- Feeding into Sprint 4 AI extraction (the AI prompt includes the text)
- Logging and QA workflows
"""
from __future__ import annotations

from speech.exporters.base_exporter import BaseExporter
from speech.models.processing_result import SpeechProcessingResult


class TextExporter(BaseExporter):
    """
    Exports transcript text only, one segment per line.

    Output is a clean, readable plain text file — no metadata headers,
    no timestamps, no confidence scores. Suitable for human review.
    """

    @property
    def extension(self) -> str:
        return "txt"

    def export(self, result: SpeechProcessingResult, output_path: str) -> str:
        path = self._ensure_parent(output_path)

        lines: list[str] = []

        if not result.success or result.transcript is None:
            lines.append("[Transcription failed]")
            for err in result.errors:
                lines.append(f"  Error: {err}")
        else:
            if result.transcript.segments:
                for seg in result.transcript.segments:
                    line = seg.text.strip()
                    if line:
                        lines.append(line)
            else:
                lines.append(result.transcript.text)

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
            if lines:
                f.write("\n")

        return str(path.resolve())


class VerboseTextExporter(BaseExporter):
    """
    Exports transcript with timestamps, confidence, and metadata header.

    Format per segment:
        [00:01.23 -> 00:05.67 | conf: 0.91] Some spoken text here.

    Header block contains audio file info and processing stats.
    """

    @property
    def extension(self) -> str:
        return "txt"

    def export(self, result: SpeechProcessingResult, output_path: str) -> str:
        path = self._ensure_parent(output_path)
        lines = self._build_lines(result)
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
            if lines:
                f.write("\n")
        return str(path.resolve())

    def _build_lines(self, result: SpeechProcessingResult) -> list[str]:
        lines: list[str] = []

        # Header
        lines.append("=" * 60)
        lines.append("TRANSCRIPT REPORT")
        lines.append("=" * 60)
        lines.append(f"Audio ID  : {result.audio_id}")

        meta = result.metadata
        if meta and meta.audio_info:
            ai = meta.audio_info
            lines.append(f"File      : {ai.file_name}")
            lines.append(f"Format    : {ai.format}")
            dur = ai.duration_seconds
            lines.append(f"Duration  : {_fmt_time(dur)} ({dur:.1f}s)")

        if meta and meta.stats:
            st = meta.stats
            lines.append(f"Model     : {st.model_name} ({st.model_size})")
            lines.append(f"Device    : {st.device_used}")
            lines.append(f"Proc time : {st.processing_time_seconds:.2f}s")

        if result.success and result.transcript:
            tr = result.transcript
            lines.append(f"Language  : {tr.language} ({tr.language_probability:.0%})")
            lines.append(f"Words     : {tr.word_count()}")
            lines.append(f"Confidence: {tr.avg_confidence():.2%}")

        lines.append("=" * 60)
        lines.append("")

        if not result.success or result.transcript is None:
            lines.append("[Transcription failed]")
            for err in result.errors:
                lines.append(f"  Error: {err}")
            return lines

        # Segments
        for seg in result.transcript.segments:
            ts = f"[{_fmt_time(seg.start)} -> {_fmt_time(seg.end)} | conf: {seg.confidence:.2f}]"
            lines.append(f"{ts} {seg.text.strip()}")

        lines.append("")

        if result.warnings:
            lines.append("Warnings:")
            for w in result.warnings:
                lines.append(f"  - {w}")

        return lines


def _fmt_time(seconds: float) -> str:
    """Format seconds as MM:SS.ss."""
    m = int(seconds // 60)
    s = seconds % 60
    return f"{m:02d}:{s:05.2f}"
