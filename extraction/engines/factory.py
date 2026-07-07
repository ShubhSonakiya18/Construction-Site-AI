"""
factory.py — EngineFactory: registry-based factory for BaseLLMProvider implementations.

How to add a new LLM provider (the ONLY files that need to touch):
    1. Implement BaseLLMProvider in extraction/engines/<name>_engine.py
    2. Add a <Name>Config dataclass in extraction/config.py
    3. Add its config field to ExtractionConfig (and to from_env())
    4. Call EngineFactory.register(...) in the "Built-in registrations" block below

Nothing in business logic (ExtractionPipeline.extract) needs to change.
The pipeline calls EngineFactory.create_from_config(config, system_prompt)
and receives a BaseLLMProvider — it never knows the concrete type.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from extraction.engines.base_engine import BaseLLMProvider

if TYPE_CHECKING:
    from extraction.config import ExtractionConfig


class EngineFactory:
    """
    Registry mapping provider name → (EngineClass, config_extractor).

    config_extractor is a callable that receives an ExtractionConfig and
    returns the kwargs dict for the engine constructor (excluding system_prompt,
    which is always passed separately so the factory controls prompt wiring).
    """

    _REGISTRY: dict[str, tuple[type[BaseLLMProvider], Callable]] = {}

    @classmethod
    def register(
        cls,
        name: str,
        engine_cls: type[BaseLLMProvider],
        config_extractor: Callable[["ExtractionConfig"], dict],
    ) -> None:
        """Register a provider. Call this at module level in this file."""
        cls._REGISTRY[name] = (engine_cls, config_extractor)

    @classmethod
    def create_from_config(
        cls,
        config: "ExtractionConfig",
        system_prompt: str = "",
    ) -> BaseLLMProvider:
        """Instantiate the engine for config.provider with its config kwargs."""
        provider = config.provider
        if provider not in cls._REGISTRY:
            raise ValueError(
                f"Unknown LLM provider '{provider}'. "
                f"Registered providers: {cls.available()}"
            )
        engine_cls, extractor = cls._REGISTRY[provider]
        return engine_cls(system_prompt=system_prompt, **extractor(config))

    @classmethod
    def available(cls) -> list[str]:
        """Return sorted list of registered provider names."""
        return sorted(cls._REGISTRY)


# ── Built-in provider registrations ──────────────────────────────────────────
# Add new providers here. Import their engine class, call EngineFactory.register.

from extraction.engines.groq_engine import GroqEngine  # noqa: E402

EngineFactory.register(
    "groq",
    GroqEngine,
    lambda cfg: {
        "model": cfg.groq.model,
        "api_key": cfg.groq.api_key,
        "temperature": cfg.groq.temperature,
        "timeout_seconds": cfg.groq.timeout_seconds,
    },
)
