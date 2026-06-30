"""
speech/preprocessors/chunker.py — Reports chunking metadata for long recordings.

Faster Whisper handles chunking internally via its chunk_length parameter and
VAD filter. This module reports the expected chunk breakdown for metadata
purposes and can optionally split files for parallel processing in future
distributed deployments.

For Sprint 3 (single-machine, single-thread), the chunker computes the chunk
count and exposes it to the pipeline stats. Actual audio splitting is deferred
to the future distributed processing story.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class ChunkInfo:
    """Metadata for one audio chunk (actual or planned)."""
    chunk_index: int
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    overlap_seconds: float

    def to_dict(self) -> dict:
        return {
            "chunk_index": self.chunk_index,
            "start_seconds": round(self.start_seconds, 3),
            "end_seconds": round(self.end_seconds, 3),
            "duration_seconds": round(self.duration_seconds, 3),
            "overlap_seconds": round(self.overlap_seconds, 3),
        }


class AudioChunker:
    """
    Computes chunk boundaries for a given audio duration.

    In Sprint 3, this is used only for reporting (how many chunks did Whisper
    internally process?). Future sprints will use this for true parallel
    chunked processing.
    """

    def __init__(
        self,
        chunk_length_seconds: float = 30.0,
        overlap_seconds: float = 1.0,
    ) -> None:
        if chunk_length_seconds <= 0:
            raise ValueError("chunk_length_seconds must be positive")
        if overlap_seconds < 0:
            raise ValueError("overlap_seconds cannot be negative")
        if overlap_seconds >= chunk_length_seconds:
            raise ValueError("overlap_seconds must be less than chunk_length_seconds")

        self._chunk_length = chunk_length_seconds
        self._overlap = overlap_seconds

    def compute_chunks(self, duration_seconds: float) -> list[ChunkInfo]:
        """
        Return the list of ChunkInfo objects that would cover a recording of
        the given duration.

        Returns a single chunk for recordings shorter than chunk_length_seconds.
        """
        if duration_seconds <= 0:
            return []

        if duration_seconds <= self._chunk_length:
            return [
                ChunkInfo(
                    chunk_index=0,
                    start_seconds=0.0,
                    end_seconds=duration_seconds,
                    duration_seconds=duration_seconds,
                    overlap_seconds=0.0,
                )
            ]

        chunks: list[ChunkInfo] = []
        step = self._chunk_length - self._overlap
        num_chunks = math.ceil((duration_seconds - self._overlap) / step)

        for i in range(num_chunks):
            start = i * step
            end = min(start + self._chunk_length, duration_seconds)
            overlap = self._overlap if i > 0 else 0.0

            chunks.append(
                ChunkInfo(
                    chunk_index=i,
                    start_seconds=start,
                    end_seconds=end,
                    duration_seconds=end - start,
                    overlap_seconds=overlap,
                )
            )

        return chunks

    def chunk_count(self, duration_seconds: float) -> int:
        return len(self.compute_chunks(duration_seconds))
