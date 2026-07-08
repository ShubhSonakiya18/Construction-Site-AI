"""
registry.py — PromptRegistry: central registry of known generation prompts.

Why a registry (not a filesystem scan):
    PromptLoader.list_available() discovers prompts by scanning *.md files on
    disk — it answers "what files exist?" PromptRegistry answers "what prompts
    are *expected* to exist and what are their contracts?"

    The registry separates discovery from validation:
        - PromptLoader: I/O concern (reads files, parses frontmatter, caches)
        - PromptRegistry: domain concern (known prompts, expected metadata)

    Adding a new prompt requires:
        1. Create generation/prompts/<name>.md
        2. Call DEFAULT_PROMPT_REGISTRY.register(PromptRegistration(...))
        No other file needs to change.

    The registry also provides future introspection entry points:
        - Sprint 7 admin API can expose GET /prompts listing all registered prompts
        - Sprint 9 UI can surface prompt versions to operators
        - Monitoring can alert when a registered prompt is missing from disk
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PromptRegistration:
    """Describes one registered prompt and its contract."""

    name: str
    description: str
    expected_output: str  # "markdown", "email", "json"
    service_class_name: str  # documentation only — not an import
    variables: list[str] = field(default_factory=list)
    min_body_length: int = 50  # minimum chars expected in the .md body


class PromptRegistry:
    """Registry of known prompt names and their metadata contracts.

    Usage:
        reg = PromptRegistry()
        reg.register(PromptRegistration(name="daily_report", ...))
        reg.validate("daily_report")              # raises if not registered
        entry = reg.get("daily_report")           # returns PromptRegistration
        names = reg.list_names()                  # sorted list of registered names
    """

    def __init__(self) -> None:
        self._registry: dict[str, PromptRegistration] = {}

    def register(self, registration: PromptRegistration) -> "PromptRegistry":
        """Register a prompt. Returns self for chaining."""
        if registration.name in self._registry:
            logger.warning(
                "PromptRegistry: '%s' already registered — overwriting",
                registration.name,
            )
        self._registry[registration.name] = registration
        logger.debug("PromptRegistry: registered '%s'", registration.name)
        return self

    def get(self, name: str) -> PromptRegistration:
        """Return the registration for *name*. Raises KeyError if not found."""
        if name not in self._registry:
            raise KeyError(
                f"Prompt '{name}' not registered. "
                f"Known prompts: {self.list_names()}"
            )
        return self._registry[name]

    def validate(self, name: str) -> None:
        """Raise ValueError if *name* is not registered."""
        if name not in self._registry:
            raise ValueError(
                f"Prompt '{name}' is not registered in PromptRegistry. "
                f"Known: {self.list_names()}. "
                f"To add it: DEFAULT_PROMPT_REGISTRY.register(PromptRegistration(name='{name}', ...))"
            )

    def is_registered(self, name: str) -> bool:
        return name in self._registry

    def list_names(self) -> list[str]:
        """Return sorted list of registered prompt names."""
        return sorted(self._registry.keys())

    def __len__(self) -> int:
        return len(self._registry)


# ── Default registry — the 4 built-in Sprint 5 prompts ───────────────────────
#
# To add a new prompt in a future sprint:
#   1. Create generation/prompts/<name>.md with frontmatter
#   2. Add a DEFAULT_PROMPT_REGISTRY.register(...) call here
#   3. Create the corresponding service class
#   No other file needs to change.

DEFAULT_PROMPT_REGISTRY = PromptRegistry()

DEFAULT_PROMPT_REGISTRY.register(PromptRegistration(
    name="daily_report",
    description="Formal daily site report for contractor records",
    expected_output="markdown",
    service_class_name="DailyReportService",
    variables=[
        "log_date", "current_stage", "work_completed",
        "workforce", "weather", "delays", "safety", "tomorrows_plan",
    ],
))

DEFAULT_PROMPT_REGISTRY.register(PromptRegistration(
    name="customer_update",
    description="Client-facing project progress email (jargon-free)",
    expected_output="email",
    service_class_name="CustomerUpdateService",
    variables=["log_date", "project_name", "current_stage", "work_completed", "tomorrows_plan"],
))

DEFAULT_PROMPT_REGISTRY.register(PromptRegistration(
    name="safety_talk",
    description="OSHA-referenced daily safety toolbox talk for crew briefing",
    expected_output="markdown",
    service_class_name="SafetyTalkService",
    variables=["log_date", "current_stage", "work_completed", "materials", "weather", "safety"],
))

DEFAULT_PROMPT_REGISTRY.register(PromptRegistration(
    name="material_reminder",
    description="Material procurement action list with priority levels",
    expected_output="markdown",
    service_class_name="MaterialReminderService",
    variables=["log_date", "current_stage", "materials", "work_completed", "tomorrows_plan"],
))
