"""
loader.py — PromptLoader: loads and parses versioned .md prompt templates.

Why prompts-as-files (not hardcoded strings):
    Hardcoded prompts require a code change + redeploy for every iteration.
    File-based prompts let product owners or prompt engineers iterate without
    touching Python. The .md extension means prompts render nicely in GitHub
    and editors — critical for a non-developer reviewing what the AI "knows."

Frontmatter format (YAML-like, no PyYAML dependency):
    ---
    name: daily_report
    version: 1.0.0
    description: ...
    supported_models:
      - llama-3.3-70b-versatile
    variables:
      - log_date
      - current_stage
    expected_output: markdown
    last_updated: 2026-07-07
    ---

    Prompt body...

Why no PyYAML:
    Adding PyYAML would be a new dependency for 20 lines of parsing.
    Our frontmatter schema is simple enough (scalar + list values only)
    to parse with a hand-written parser. No nested objects, no anchors.

Cache invalidation (Sprint 5.1):
    The loader tracks each cached file's mtime (os.path.getmtime). On every
    load() call the current mtime is compared against the stored value. If the
    file was modified since it was cached, the cached entry is evicted and the
    file is re-read. This means prompt engineers can edit .md files and the
    change is picked up on the next generate() call — no process restart needed.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class PromptMetadata:
    """Versioning metadata extracted from the prompt file's frontmatter."""

    name: str
    version: str = "0.0.0"
    description: str = ""
    supported_models: list[str] = field(default_factory=list)
    variables: list[str] = field(default_factory=list)
    expected_output: str = "markdown"
    last_updated: str = ""


@dataclass
class LoadedPrompt:
    """A parsed prompt: metadata (from frontmatter) + template (body text)."""

    metadata: PromptMetadata
    template: str


class PromptLoader:
    """Loads versioned .md prompts from a directory.

    Caches parsed prompts so repeated calls to .load() within one service
    instance do not re-read the file. Cache is per-PromptLoader instance,
    so tests can create fresh instances with isolation.

    Mtime-aware cache invalidation (Sprint 5.1):
        Each cached entry stores the file's mtime at load time. On every
        subsequent .load() the current mtime is compared; a changed file
        triggers automatic eviction and re-read. No process restart needed
        when a prompt file is edited during development.
    """

    def __init__(self, prompts_dir: str | Path = "generation/prompts") -> None:
        self._dir = Path(prompts_dir)
        self._cache: dict[str, LoadedPrompt] = {}
        self._mtime: dict[str, float] = {}

    def load(self, prompt_name: str) -> LoadedPrompt:
        path = self._dir / f"{prompt_name}.md"
        if not path.exists():
            raise FileNotFoundError(
                f"Prompt file not found: {path}. "
                f"Available prompts: {self.list_available()}"
            )

        current_mtime = os.path.getmtime(path)

        if prompt_name in self._cache:
            if self._mtime.get(prompt_name) == current_mtime:
                logger.debug("PromptLoader: cache hit '%s'", prompt_name)
                return self._cache[prompt_name]
            # File was modified — evict stale entry
            logger.info(
                "PromptLoader: '%s' modified since last load — reloading",
                prompt_name,
            )
            del self._cache[prompt_name]
            del self._mtime[prompt_name]

        logger.debug("PromptLoader: cache miss '%s' — reading from disk", prompt_name)
        raw = path.read_text(encoding="utf-8")
        metadata, template = self._parse(raw, prompt_name)

        loaded = LoadedPrompt(metadata=metadata, template=template)
        self._cache[prompt_name] = loaded
        self._mtime[prompt_name] = current_mtime

        logger.debug(
            "PromptLoader: loaded '%s' v%s from %s",
            metadata.name, metadata.version, path,
        )
        return loaded

    def list_available(self) -> list[str]:
        """Return stems of all .md files in the prompts directory."""
        if not self._dir.exists():
            return []
        return sorted(p.stem for p in self._dir.glob("*.md"))

    def clear_cache(self) -> None:
        """Force re-read of all prompts on next access (useful in tests)."""
        self._cache.clear()
        self._mtime.clear()

    # ── Parsing ───────────────────────────────────────────────────────────────

    def _parse(self, raw: str, fallback_name: str) -> tuple[PromptMetadata, str]:
        if not raw.startswith("---"):
            return PromptMetadata(name=fallback_name), raw.strip()

        end = raw.find("\n---", 3)
        if end == -1:
            return PromptMetadata(name=fallback_name), raw.strip()

        front = raw[3:end].strip()
        body = raw[end + 4:].strip()

        return self._parse_frontmatter(front, fallback_name), body

    def _parse_frontmatter(
        self, front: str, fallback_name: str
    ) -> PromptMetadata:
        """Parse scalar and list values from YAML-like frontmatter.

        Handles:
            scalar:  key: value
            list:    key:\n  - item1\n  - item2
        """
        parsed: dict = {}
        current_key: Optional[str] = None

        for line in front.splitlines():
            if line.startswith("  - "):
                if current_key is not None:
                    if not isinstance(parsed.get(current_key), list):
                        parsed[current_key] = []
                    parsed[current_key].append(line[4:].strip())
            elif ":" in line:
                key, _, value = line.partition(":")
                key = key.strip()
                value = value.strip()
                if value:
                    parsed[key] = value
                    current_key = None
                else:
                    parsed[key] = []
                    current_key = key
            else:
                current_key = None

        return PromptMetadata(
            name=parsed.get("name", fallback_name),
            version=str(parsed.get("version", "0.0.0")),
            description=parsed.get("description", ""),
            supported_models=parsed.get("supported_models", []),
            variables=parsed.get("variables", []),
            expected_output=parsed.get("expected_output", "markdown"),
            last_updated=str(parsed.get("last_updated", "")),
        )
