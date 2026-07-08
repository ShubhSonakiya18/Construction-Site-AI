"""
config.py — Configuration for the Sprint 5 AI Generation Services.

Mirrors the structure of extraction/config.py so GenerationConfig can be passed
to EngineFactory.create_from_config() via duck typing — no Sprint 4 changes needed.

Environment variables:
    GENERATION_PROVIDER           default: groq
    GROQ_API_KEY                  shared with extraction (console.groq.com — free tier)
    GENERATION_GROQ_MODEL         default: llama-3.3-70b-versatile
    GENERATION_GROQ_TEMPERATURE   default: 0.3  (higher than extraction for natural prose)
    GENERATION_GROQ_TIMEOUT       default: 90
    GENERATION_GROQ_MAX_TOKENS    default: 2048
    GENERATION_MAX_RETRIES        default: 3
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class GenerationGroqConfig:
    """Groq-specific settings for generation.

    temperature=0.3 (vs extraction's 0.1): generation benefits from slightly
    more creative output; extraction needs determinism for JSON structure.
    """

    model: str = "llama-3.3-70b-versatile"
    api_key: str = ""
    temperature: float = 0.3
    timeout_seconds: int = 90
    max_tokens: int = 2048


@dataclass
class GenerationConfig:
    """Top-level configuration for the AI Generation Service Layer.

    Attribute names (.provider, .groq.model, .groq.api_key, etc.) intentionally
    mirror ExtractionConfig so EngineFactory.create_from_config() can accept
    this object via duck typing — no import of extraction config needed.
    """

    provider: str = "groq"
    groq: GenerationGroqConfig = field(default_factory=GenerationGroqConfig)
    max_retries: int = 3
    retry_delay_seconds: float = 2.0
    retry_backoff: float = 2.0
    prompts_dir: str = "generation/prompts"

    @classmethod
    def from_env(cls) -> "GenerationConfig":
        return cls(
            provider=os.getenv("GENERATION_PROVIDER", "groq"),
            groq=GenerationGroqConfig(
                model=os.getenv("GENERATION_GROQ_MODEL", "llama-3.3-70b-versatile"),
                api_key=os.getenv("GROQ_API_KEY", ""),
                temperature=float(os.getenv("GENERATION_GROQ_TEMPERATURE", "0.3")),
                timeout_seconds=int(os.getenv("GENERATION_GROQ_TIMEOUT", "90")),
                max_tokens=int(os.getenv("GENERATION_GROQ_MAX_TOKENS", "2048")),
            ),
            max_retries=int(os.getenv("GENERATION_MAX_RETRIES", "3")),
        )
