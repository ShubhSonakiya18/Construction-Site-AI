"""
speech/exporters/json_exporter.py — Export full SpeechProcessingResult as JSON.

The JSON output is the canonical, lossless format. It includes the full
transcript with segments, word timestamps, metadata, and processing stats.
Sprint 4 AI extraction reads this JSON to ground field extraction to timestamps.
Sprint 6 stores the important fields in PostgreSQL.
"""
from __future__ import annotations

import json
from pathlib import Path

from speech.exporters.base_exporter import BaseExporter
from speech.models.processing_result import SpeechProcessingResult


class JSONExporter(BaseExporter):
    """Exports SpeechProcessingResult as a pretty-printed JSON file."""

    def __init__(self, indent: int = 2) -> None:
        self._indent = indent

    @property
    def extension(self) -> str:
        return "json"

    def export(self, result: SpeechProcessingResult, output_path: str) -> str:
        path = self._ensure_parent(output_path)
        data = result.to_dict()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=self._indent, ensure_ascii=False)
        return str(path.resolve())


class JSONLExporter(BaseExporter):
    """
    Exports one result per line as JSONL (newline-delimited JSON).

    JSONL format is used for batch processing where multiple results are
    appended to the same file. Each line is a complete, self-contained JSON
    object — the same format used by datasets/exports/ from Sprint 2.
    """

    @property
    def extension(self) -> str:
        return "jsonl"

    def export(self, result: SpeechProcessingResult, output_path: str) -> str:
        """Appends one JSON line to output_path (creates file if not exists)."""
        path = self._ensure_parent(output_path)
        data = result.to_dict()
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")
        return str(path.resolve())
