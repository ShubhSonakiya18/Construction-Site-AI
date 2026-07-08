"""
manager.py — AIServiceManager: single orchestration point for all generation services.

Architecture decision — why a Manager (not direct service calls):
    The user specification says: "Business logic must never call Groq directly.
    All AI communication must go through AIServiceManager."

    Without a manager, callers must import 4 services, create an engine, wire
    up the prompt loader and validator, then call each service in order. That's
    6 objects to construct and maintain per caller. With the manager, callers
    have a single object: manager.generate_all(log).

    The manager also owns:
    - Engine lifecycle (one engine, checked once via is_available())
    - Prompt loader (shared, cached across services)
    - Validator (shared, stateless)
    - Structured logging across the full generation cycle

    Adding a fifth service in the future requires:
    1. Create NewService in generation/services/
    2. Register it in the manager's _services dict
    3. Add its output field to GenerationResult
    That's it. No changes to callers.

Dependency injection:
    The engine= parameter accepts any BaseLLMProvider — including mocks.
    Tests inject a MockLLMProvider to run without GROQ_API_KEY.
    The manager itself is never responsible for creating the engine class;
    it delegates to EngineFactory (which knows the concrete type).
"""
from __future__ import annotations

import logging
import time

from extraction.engines.base_engine import BaseLLMProvider
from extraction.engines.factory import EngineFactory
from generation.config import GenerationConfig
from generation.models.outputs import (
    CustomerUpdate,
    DailyReport,
    GenerationResult,
    MaterialReminder,
    ServiceOutput,
    ServiceType,
    ToolboxTalk,
)
from generation.prompts.loader import PromptLoader
from generation.services.base_service import BaseAIService
from generation.services.registry import DEFAULT_SERVICE_REGISTRY, ServiceRegistry
from generation.validators.content_validator import ContentValidator

logger = logging.getLogger(__name__)


class AIServiceManager:
    """Orchestrates all 4 AI generation services for a single ConstructionDailyLog.

    Usage:
        manager = AIServiceManager()                     # reads config from env
        result  = manager.generate_all(extracted_log)   # returns GenerationResult

        # Or inject a mock engine for tests:
        manager = AIServiceManager(engine=MockLLMProvider())

        # Or inject a custom service registry (e.g. in tests with partial services):
        manager = AIServiceManager(service_registry=my_registry, engine=mock)

    Sprint 5.1: The _services dict is now built by ServiceRegistry.create_all().
    Adding a new service requires only:
        1. Create the service class
        2. Register it in DEFAULT_SERVICE_REGISTRY
        Zero changes to AIServiceManager.
    """

    def __init__(
        self,
        config: GenerationConfig | None = None,
        engine: BaseLLMProvider | None = None,
        service_registry: ServiceRegistry | None = None,
    ) -> None:
        self._config = config or GenerationConfig.from_env()

        if engine is not None:
            self._engine = engine
        else:
            # EngineFactory works here via duck typing:
            # GenerationConfig has the same .provider / .groq.* attributes
            # as ExtractionConfig, which the factory's lambda extractor accesses.
            self._engine = EngineFactory.create_from_config(
                self._config, system_prompt=""
            )

        prompt_loader = PromptLoader(self._config.prompts_dir)
        validator = ContentValidator()
        registry = service_registry or DEFAULT_SERVICE_REGISTRY

        self._services: dict[ServiceType, BaseAIService] = registry.create_all(
            engine=self._engine,
            prompt_loader=prompt_loader,
            validator=validator,
            config=self._config,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def is_available(self) -> bool:
        """Return True if the underlying LLM engine is reachable."""
        return self._engine.is_available()

    def generate(self, service_type: ServiceType, log: dict) -> ServiceOutput:
        """Generate output from a single named service."""
        if service_type not in self._services:
            raise ValueError(
                f"Unknown service type '{service_type}'. "
                f"Available: {list(self._services)}"
            )
        return self._services[service_type].generate(log)

    def generate_all(self, log: dict) -> GenerationResult:
        """Generate all 4 outputs from a ConstructionDailyLog dict.

        Returns a GenerationResult even when some services fail —
        individual service outputs carry their own success flags.
        Callers must check result.success and each sub-output's success.
        """
        log_id = log.get("log_id", "")
        log_date = log.get("log_date", "")
        current_stage = log.get("current_stage", "")

        logger.info(
            "AIServiceManager.generate_all: log=%s date=%s stage=%s",
            log_id, log_date, current_stage,
        )
        t_start = time.monotonic()

        raw_report = self._services[ServiceType.DAILY_REPORT].generate(log)
        raw_customer = self._services[ServiceType.CUSTOMER_UPDATE].generate(log)
        raw_safety = self._services[ServiceType.SAFETY_TALK].generate(log)
        raw_material = self._services[ServiceType.MATERIAL_REMINDER].generate(log)

        # Wrap raw ServiceOutputs in typed subclasses for clear downstream access
        daily_report = DailyReport(**raw_report.model_dump())
        customer_update = CustomerUpdate(**raw_customer.model_dump())
        safety_talk = ToolboxTalk(**raw_safety.model_dump())
        material_reminder = MaterialReminder(**raw_material.model_dump())

        all_errors = (
            raw_report.errors
            + raw_customer.errors
            + raw_safety.errors
            + raw_material.errors
        )
        any_success = any(
            [raw_report.success, raw_customer.success,
             raw_safety.success, raw_material.success]
        )

        elapsed = time.monotonic() - t_start
        logger.info(
            "AIServiceManager.generate_all: completed in %.2fs success=%s errors=%d",
            elapsed, any_success, len(all_errors),
        )

        return GenerationResult(
            success=any_success,
            log_id=log_id,
            log_date=log_date,
            current_stage=current_stage,
            daily_report=daily_report,
            customer_update=customer_update,
            safety_talk=safety_talk,
            material_reminder=material_reminder,
            errors=all_errors,
        )
