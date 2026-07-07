"""
base_generator.py — Abstract base class for all 5 dataset generators.

WHY THIS MODULE EXISTS:
    All generators share the same lifecycle:
        1. Accept a seeded RNG for reproducibility
        2. Load knowledge from KnowledgeBase (not from files directly)
        3. Yield records one at a time (streaming — never accumulates all in memory)
        4. Each record passes through ValidationPipeline before being yielded
        5. Emit statistics

    Without a base class, this lifecycle would be copied into each generator —
    violating DRY and making it easy for generators to drift apart.

STREAMING DESIGN:
    Every generator uses Python generator functions (yield). This means:
    - Memory usage is O(batch_size), not O(total_records)
    - A 500k-record run uses the same peak memory as a 5k run
    - Exporters flush every BATCH_SIZE records to disk

    COMMON BEGINNER MISTAKE: Writing generate() to return a list. This loads
    all records into memory. Always yield instead.

REPRODUCIBILITY:
    Every generator receives a seeded random.Random instance.
    random.Random is NOT the global random module — it's isolated.
    This ensures: same seed → same output, regardless of what other
    code happens to call random functions.

SUBCLASS CONTRACT:
    Subclasses must implement:
        generate_one(**kwargs) -> dict   # generate a single raw record
    Subclasses may override:
        pre_validate(record) -> dict     # transform before validation
        post_validate(record) -> dict    # transform after validation
"""
from __future__ import annotations

import logging
import random
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Iterator, Optional

from dataset_generation_framework.core.knowledge_loader import KnowledgeBase
from dataset_generation_framework.validation.pipeline import (
    ValidationPipeline,
    ValidationResult,
)
from dataset_generation_framework.config import VALIDATE_EVERY_N

logger = logging.getLogger(__name__)


class GeneratorStats:
    """Accumulates statistics during a generation run."""

    def __init__(self, generator_name: str) -> None:
        self.name = generator_name
        self.total_attempted: int = 0
        self.total_valid: int = 0
        self.total_blocked: int = 0
        self.total_with_errors: int = 0
        self.total_with_warnings: int = 0
        self.blocking_errors: dict[str, int] = {}
        self.started_at: datetime = datetime.now(timezone.utc)
        self.finished_at: Optional[datetime] = None

    def record(self, result: ValidationResult) -> None:
        self.total_attempted += 1
        if result.is_valid:
            self.total_valid += 1
        else:
            self.total_blocked += 1
            for err in result.blocking_errors:
                rule_id = err.split("]")[0].lstrip("[") if "]" in err else "UNKNOWN"
                self.blocking_errors[rule_id] = self.blocking_errors.get(rule_id, 0) + 1
        if result.non_blocking_errors:
            self.total_with_errors += 1
        if result.warnings:
            self.total_with_warnings += 1

    def finish(self) -> None:
        self.finished_at = datetime.now(timezone.utc)

    def to_dict(self) -> dict:
        elapsed = (
            (self.finished_at - self.started_at).total_seconds()
            if self.finished_at else None
        )
        return {
            "generator": self.name,
            "total_attempted": self.total_attempted,
            "total_valid": self.total_valid,
            "total_blocked": self.total_blocked,
            "total_with_errors": self.total_with_errors,
            "total_with_warnings": self.total_with_warnings,
            "pass_rate_percent": round(
                self.total_valid / max(self.total_attempted, 1) * 100, 2
            ),
            "top_blocking_errors": sorted(
                self.blocking_errors.items(), key=lambda x: -x[1]
            )[:10],
            "elapsed_seconds": elapsed,
            "records_per_second": round(
                self.total_valid / elapsed, 1
            ) if elapsed and elapsed > 0 else None,
        }


class BaseGenerator(ABC):
    """
    Abstract base class for all synthetic data generators.

    Every subclass inherits:
    - Seeded RNG (self.rng)
    - KnowledgeBase access (self.kb)
    - ValidationPipeline (self.pipeline)
    - Streaming generate() method
    - GeneratorStats tracking
    """

    def __init__(
        self,
        kb: KnowledgeBase,
        seed: int,
        *,
        validate_every_n: int = VALIDATE_EVERY_N,
    ) -> None:
        self.kb = kb
        self.rng = random.Random(seed)
        self.pipeline = ValidationPipeline(kb)
        self.stats = GeneratorStats(self.__class__.__name__)
        self._validate_every_n = validate_every_n
        self._record_counter = 0

    # ── Abstract interface ─────────────────────────────────────────────────────

    @abstractmethod
    def generate_one(self, **kwargs: Any) -> dict:
        """
        Generate a single raw record dict.
        Must not perform validation — that is the pipeline's job.
        Must use self.rng for all random operations.
        """

    # ── Public streaming API ───────────────────────────────────────────────────

    def stream(
        self,
        count: int,
        applies_to: str = "dataset_generation",
        **kwargs: Any,
    ) -> Iterator[dict]:
        """
        Yield validated records one at a time.

        Calling stream(500_000) uses the same peak memory as stream(5_000)
        because records are never accumulated — they flow to the exporter.

        count:      How many VALID records to yield.
        applies_to: Validation context filter.
        kwargs:     Passed to generate_one() on each call.
        """
        yielded = 0
        self.stats = GeneratorStats(self.__class__.__name__)

        while yielded < count:
            record = self.generate_one(**kwargs)
            self._record_counter += 1

            # Sample validation (every Nth record)
            if self._record_counter % self._validate_every_n == 0:
                result = self.pipeline.validate(record, applies_to=applies_to)
                self.stats.record(result)

                if not result.is_valid:
                    logger.debug(
                        "[%s] Record blocked: %s",
                        self.__class__.__name__,
                        result.blocking_errors[0] if result.blocking_errors else "",
                    )
                    continue
            else:
                # Not sampled — mark as valid without checking
                self.stats.total_attempted += 1
                self.stats.total_valid += 1

            yield record
            yielded += 1

        self.stats.finish()
        logger.info(
            "[%s] Generated %d records. %s",
            self.__class__.__name__,
            count,
            self.stats.to_dict(),
        )

    # ── Utility helpers available to all subclasses ────────────────────────────

    def new_uuid(self) -> str:
        """Generate a UUID4. Uses Python's uuid module, not self.rng."""
        return str(uuid.uuid4())

    def seeded_uuid(self) -> str:
        """Generate a deterministic UUID from self.rng for reproducibility."""
        return str(uuid.UUID(int=self.rng.getrandbits(128), version=4))

    def pick(self, items: list, weights: Optional[list] = None) -> Any:
        """Random choice from a list, optionally weighted. Uses self.rng."""
        if not items:
            raise ValueError("Cannot pick from empty list")
        if weights:
            return self.rng.choices(items, weights=weights, k=1)[0]
        return self.rng.choice(items)

    def pick_many(self, items: list, k: int, unique: bool = True) -> list:
        """Pick k items from a list, optionally without replacement."""
        if unique:
            return self.rng.sample(items, min(k, len(items)))
        return self.rng.choices(items, k=k)

    def maybe(self, probability: float) -> bool:
        """Return True with given probability [0.0, 1.0]."""
        return self.rng.random() < probability

    def rand_int(self, lo: int, hi: int) -> int:
        """Inclusive integer in [lo, hi]."""
        return self.rng.randint(lo, hi)

    def rand_float(self, lo: float, hi: float) -> float:
        """Float in [lo, hi)."""
        return self.rng.uniform(lo, hi)
