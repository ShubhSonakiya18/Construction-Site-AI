"""
jsonl_exporter.py — Streams records to JSONL files in configurable batches.

WHY JSONL:
    JSON Lines (one JSON object per line) is the industry standard for large
    datasets because it supports streaming reads and appends. A 500k-record
    JSONL file can be processed line by line without loading it all into memory.
    In contrast, a single JSON array requires loading the entire file.

WHY BATCHED WRITES:
    Writing one record at a time causes disk I/O on every record — slow at scale.
    Writing all records at once loads everything into memory.
    Batched writes balance both: flush every BATCH_SIZE records to disk.

USAGE:
    with JsonlExporter(output_path) as exporter:
        for record in generator.stream(5000):
            exporter.write(record)
    # File is guaranteed to be flushed and closed after the with block.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from dataset_generation_framework.config import BATCH_SIZE

logger = logging.getLogger(__name__)


class JsonlExporter:
    """Context manager that writes records to a JSONL file in batches."""

    def __init__(
        self,
        output_path: Path,
        batch_size: int = BATCH_SIZE,
        *,
        append: bool = False,
    ) -> None:
        self.output_path = Path(output_path)
        self.batch_size = batch_size
        self._mode = "a" if append else "w"
        self._buffer: list[dict] = []
        self._file: Optional[Any] = None
        self._total_written: int = 0

    def __enter__(self) -> "JsonlExporter":
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self.output_path, self._mode, encoding="utf-8")
        logger.info("JsonlExporter opened: %s", self.output_path)
        return self

    def __exit__(self, *_) -> None:
        self._flush()
        if self._file:
            self._file.close()
        logger.info(
            "JsonlExporter closed: %s (%d records written)",
            self.output_path, self._total_written,
        )

    def write(self, record: dict) -> None:
        self._buffer.append(record)
        if len(self._buffer) >= self.batch_size:
            self._flush()

    def _flush(self) -> None:
        if not self._buffer or not self._file:
            return
        for record in self._buffer:
            self._file.write(json.dumps(record, default=str) + "\n")
        self._total_written += len(self._buffer)
        self._buffer.clear()
        self._file.flush()

    @property
    def total_written(self) -> int:
        return self._total_written

    @staticmethod
    def count_records(path: Path) -> int:
        """Count records in an existing JSONL file without loading it."""
        if not path.exists():
            return 0
        with open(path, "r", encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())
