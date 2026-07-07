"""
config.py — ExtractionConfig with nested GroqConfig.

All tunables in one place; zero magic numbers elsewhere in the framework.
Read env vars via ExtractionConfig.from_env().

Env vars:
    EXTRACTION_PROVIDER             default: groq
    GROQ_API_KEY                    required for Groq (set in .env — never commit)
    EXTRACTION_GROQ_MODEL           default: llama-3.3-70b-versatile
    EXTRACTION_GROQ_TEMPERATURE     default: 0.1
    EXTRACTION_GROQ_TIMEOUT         default: 60
    EXTRACTION_MAX_RETRIES          default: 3
    EXTRACTION_KNOWLEDGE_DIR        default: knowledge

To add a new provider: add a <Name>Config dataclass here, add its field to
ExtractionConfig, read its env vars in from_env(), and register its engine
in extraction/engines/factory.py.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class GroqConfig:
    model: str = "llama-3.3-70b-versatile"
    api_key: str = ""  # always loaded from GROQ_API_KEY env var at runtime
    temperature: float = 0.1
    timeout_seconds: int = 60
    max_tokens: int = 4096


@dataclass
class ExtractionConfig:
    provider: str = "groq"
    groq: GroqConfig = field(default_factory=GroqConfig)
    max_retries: int = 3
    retry_delay_seconds: float = 2.0
    retry_backoff: float = 2.0
    knowledge_dir: str = "knowledge"

    @classmethod
    def from_env(cls) -> "ExtractionConfig":
        return cls(
            provider=os.getenv("EXTRACTION_PROVIDER", "groq"),
            groq=GroqConfig(
                model=os.getenv("EXTRACTION_GROQ_MODEL", "llama-3.3-70b-versatile"),
                api_key=os.getenv("GROQ_API_KEY", ""),
                temperature=float(os.getenv("EXTRACTION_GROQ_TEMPERATURE", "0.1")),
                timeout_seconds=int(os.getenv("EXTRACTION_GROQ_TIMEOUT", "60")),
            ),
            max_retries=int(os.getenv("EXTRACTION_MAX_RETRIES", "3")),
            knowledge_dir=os.getenv("EXTRACTION_KNOWLEDGE_DIR", "knowledge"),
        )
