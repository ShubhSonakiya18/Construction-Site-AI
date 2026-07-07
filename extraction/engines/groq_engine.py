"""
groq_engine.py — GroqEngine: the ONLY file in the framework that calls the Groq API.

Uses the groq Python package (Groq's official client, free tier available).
API key is read from GROQ_API_KEY env var (set in .env — never committed to git).

To swap to a different provider: write a new BaseLLMProvider subclass and
register it in extraction/engines/factory.py. No other files need to change.
"""
from __future__ import annotations

import logging
import os

from extraction.engines.base_engine import BaseLLMProvider

logger = logging.getLogger(__name__)

_GROQ_ENDPOINT = "https://api.groq.com"

try:
    from groq import Groq as _Groq
    _HAS_GROQ = True
except ImportError:
    _HAS_GROQ = False


class GroqEngine(BaseLLMProvider):
    """
    Extraction engine backed by the Groq cloud API (free tier available).

    API key must be set via the GROQ_API_KEY environment variable or passed
    directly as api_key. The Groq client is initialised lazily on first use.
    """

    def __init__(
        self,
        model: str = "llama-3.3-70b-versatile",
        api_key: str = "",
        system_prompt: str = "",
        temperature: float = 0.1,
        timeout_seconds: int = 60,
        max_tokens: int = 4096,
    ) -> None:
        self._model = model
        self._api_key = api_key or os.getenv("GROQ_API_KEY", "")
        self._system_prompt = system_prompt
        self._temperature = temperature
        self._timeout = timeout_seconds
        self._max_tokens = max_tokens
        self._client = None  # lazy init

    def _get_client(self):
        if self._client is None:
            if not _HAS_GROQ:
                raise RuntimeError(
                    "groq package not installed. Run: pip install groq"
                )
            self._client = _Groq(api_key=self._api_key, timeout=self._timeout)
        return self._client

    # ── BaseLLMProvider interface ─────────────────────────────────────────────

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def host(self) -> str:
        return _GROQ_ENDPOINT

    def is_available(self) -> bool:
        if not _HAS_GROQ:
            return False
        if not self._api_key:
            return False
        try:
            self._get_client().models.list()
            return True
        except Exception:
            return False

    def extract(self, prompt: str) -> tuple[str, dict]:
        if not _HAS_GROQ:
            raise RuntimeError(
                "groq package not installed. Run: pip install groq"
            )
        if not self._api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Add it to your .env file: GROQ_API_KEY=gsk_..."
            )

        messages: list[dict] = []
        if self._system_prompt:
            messages.append({"role": "system", "content": self._system_prompt})
        messages.append({"role": "user", "content": prompt})

        client = self._get_client()
        resp = client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )

        raw_text: str = resp.choices[0].message.content or ""
        usage = {
            "prompt_tokens": resp.usage.prompt_tokens if resp.usage else 0,
            "completion_tokens": resp.usage.completion_tokens if resp.usage else 0,
        }
        logger.debug(
            "GroqEngine: model=%s tokens=%s+%s",
            self._model, usage["prompt_tokens"], usage["completion_tokens"],
        )
        return raw_text, usage
