"""
csv_exporter.py — Writes flat records to CSV files in configurable batches.

WHY CSV FOR SOME DATASETS:
    Safety talks and materials are flat tabular data — no nested objects.
    CSV is the universal format for flat data: Excel can open it, pandas can
    read it, and it's human-readable without tooling. JSONL would be overkill
    for data that has no nesting.

DYNAMIC COLUMNS:
    The exporter infers column names from the first record's keys.
    This means adding a field to a generator automatically adds a column
    without changing the exporter.

BEGINNER MISTAKE:
    csv.writer doesn't handle None gracefully — it writes "None" (a string).
    This exporter converts None → "" (empty string) for clean CSV output.
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any, Optional

from dataset_generation_framework.config import BATCH_SIZE

logger = logging.getLogger(__name__)


class CsvExporter:
    """Context manager that writes flat dicts to a CSV file."""

    def __init__(
        self,
        output_path: Path,
        fieldnames: Optional[list[str]] = None,
        batch_size: int = BATCH_SIZE,
    ) -> None:
        self.output_path = Path(output_path)
        self._fieldnames = fieldnames      # None = infer from first record
        self.batch_size = batch_size
        self._buffer: list[dict] = []
        self._file: Optional[Any] = None
        self._writer: Optional[csv.DictWriter] = None
        self._total_written: int = 0
        self._header_written = False

    def __enter__(self) -> "CsvExporter":
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self.output_path, "w", newline="", encoding="utf-8")
        logger.info("CsvExporter opened: %s", self.output_path)
        return self

    def __exit__(self, *_) -> None:
        self._flush()
        if self._file:
            self._file.close()
        logger.info(
            "CsvExporter closed: %s (%d records written)",
            self.output_path, self._total_written,
        )

    def write(self, record: dict) -> None:
        self._buffer.append(record)
        if len(self._buffer) >= self.batch_size:
            self._flush()

    def _flush(self) -> None:
        if not self._buffer or not self._file:
            return

        if not self._header_written:
            if self._fieldnames is None:
                self._fieldnames = list(self._buffer[0].keys())
            self._writer = csv.DictWriter(
                self._file,
                fieldnames=self._fieldnames,
                extrasaction="ignore",
            )
            self._writer.writeheader()
            self._header_written = True

        for record in self._buffer:
            # Convert None → "" and lists → semicolon-separated strings
            clean = {}
            for k, v in record.items():
                if v is None:
                    clean[k] = ""
                elif isinstance(v, list):
                    clean[k] = "; ".join(str(x) for x in v)
                else:
                    clean[k] = v
            self._writer.writerow(clean)

        self._total_written += len(self._buffer)
        self._buffer.clear()
        self._file.flush()

    @property
    def total_written(self) -> int:
        return self._total_written
