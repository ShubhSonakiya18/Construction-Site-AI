"""
speech/utils/retry.py — Decorator-based retry with exponential backoff.

The STT engine can fail transiently (model loading race, GPU OOM on first
allocation, network timeout during model download). Rather than scattering
try/except retry loops in callers, every engine call is wrapped with @retry.
"""
from __future__ import annotations

import logging
import time
from functools import wraps
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

# Exceptions that indicate a transient failure worth retrying
_RETRYABLE: tuple[type[Exception], ...] = (
    RuntimeError,
    OSError,
    MemoryError,
)


class RetryError(Exception):
    """Raised when all retry attempts are exhausted."""

    def __init__(self, attempts: int, last_error: Exception) -> None:
        super().__init__(
            f"All {attempts} attempts failed. Last error: {last_error}"
        )
        self.attempts = attempts
        self.last_error = last_error


def retry(
    max_attempts: int = 3,
    delay_seconds: float = 1.0,
    backoff: float = 2.0,
    retryable_exceptions: tuple[type[Exception], ...] = _RETRYABLE,
) -> Callable[[F], F]:
    """
    Retry decorator with exponential backoff.

    Usage:
        @retry(max_attempts=3, delay_seconds=1.0, backoff=2.0)
        def load_model():
            ...

    The decorated function raises RetryError after all attempts are exhausted.
    Non-retryable exceptions (e.g. ValueError for bad arguments) are re-raised
    immediately without consuming retry budget.
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_error: Exception | None = None
            current_delay = delay_seconds

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as exc:
                    last_error = exc
                    if attempt == max_attempts:
                        break
                    logger.warning(
                        "Attempt %d/%d for %s failed: %s. Retrying in %.1fs...",
                        attempt,
                        max_attempts,
                        func.__name__,
                        exc,
                        current_delay,
                    )
                    time.sleep(current_delay)
                    current_delay *= backoff

            raise RetryError(max_attempts, last_error)  # type: ignore[arg-type]

        return wrapper  # type: ignore[return-value]

    return decorator
