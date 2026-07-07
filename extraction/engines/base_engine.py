"""
base_engine.py — BaseLLMProvider: abstract interface for all LLM extraction engines.

Every caller outside extraction/engines/ depends on this interface only.
Concrete implementations (e.g. GroqEngine) are the only files that import
provider-specific libraries. Business logic never imports an engine class directly.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class BaseLLMProvider(ABC):

    @abstractmethod
    def extract(self, prompt: str) -> tuple[str, dict]:
        """
        Send prompt to the LLM and return raw response.

        Returns:
            (raw_text, usage_stats)
            raw_text:    The LLM's full response string (may contain JSON,
                         markdown blocks, or surrounding explanation text).
            usage_stats: Dict with keys prompt_tokens, completion_tokens (ints).
                         Return empty dict if the provider can't report usage.
        """

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the underlying LLM service is reachable right now."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Human-readable model identifier (e.g. 'llama-3.3-70b-versatile')."""

    @property
    @abstractmethod
    def host(self) -> str:
        """Service endpoint URL, or 'local' for in-process engines."""
