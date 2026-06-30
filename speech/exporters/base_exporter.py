"""
speech/exporters/base_exporter.py — Abstract base for all result exporters.

To add a new output format (SRT subtitles, VTT, CSV for batch analysis):
1. Subclass BaseExporter.
2. Implement export() and extension.
3. Register the new exporter in speech/exporters/__init__.py.

No other code changes needed. The pipeline accepts any BaseExporter instance.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from speech.models.processing_result import SpeechProcessingResult


class BaseExporter(ABC):
    """Abstract base for SpeechProcessingResult exporters."""

    @property
    @abstractmethod
    def extension(self) -> str:
        """File extension this exporter produces, without the dot. E.g. 'json'."""

    @abstractmethod
    def export(self, result: SpeechProcessingResult, output_path: str) -> str:
        """
        Write result to output_path and return the absolute path written.

        Implementations must:
        - Create parent directories if they don't exist.
        - Overwrite output_path if it already exists.
        - Return the absolute path of the file written.
        - Raise IOError on write failure.
        """

    def _ensure_parent(self, output_path: str) -> Path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
