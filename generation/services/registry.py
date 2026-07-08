"""
registry.py — ServiceRegistry: maps ServiceType values to service classes.

Why a registry (not a manual dict in AIServiceManager.__init__):
    Before Sprint 5.1, adding a new AI service required editing
    AIServiceManager.__init__ to add one more dict entry. The manager had to
    know about every concrete service class — violating the Open/Closed Principle.

    With a registry, AIServiceManager.__init__ calls:
        self._services = DEFAULT_SERVICE_REGISTRY.create_all(...)

    Adding a new service requires:
        1. Create generation/services/<name>.py
        2. Call DEFAULT_SERVICE_REGISTRY.register(ServiceRegistration(...))
        Zero changes to AIServiceManager.

    The registry also enables:
        - Introspection: what services are available?
        - Sprint 7 admin API: GET /services → list all registered services
        - Testing: inject a partial registry with only the service under test

Dependency injection:
    ServiceRegistry.create_all() accepts engine, prompt_loader, validator,
    and config — the same four arguments every BaseAIService takes. The
    registry creates all service instances and returns a ready-to-use dict.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Type

from extraction.engines.base_engine import BaseLLMProvider
from generation.config import GenerationConfig
from generation.models.outputs import ServiceType
from generation.services.base_service import BaseAIService
from generation.validators.content_validator import ContentValidator

if TYPE_CHECKING:
    from generation.prompts.loader import PromptLoader

logger = logging.getLogger(__name__)


@dataclass
class ServiceRegistration:
    """Describes one registered service: its type and the class that handles it."""

    service_type: ServiceType
    service_class: Type[BaseAIService]
    description: str


class ServiceRegistry:
    """Registry mapping ServiceType → BaseAIService subclass.

    Usage:
        reg = ServiceRegistry()
        reg.register(ServiceRegistration(
            service_type=ServiceType.DAILY_REPORT,
            service_class=DailyReportService,
            description="Formal daily site report",
        ))

        # Create all registered services in one call:
        services = reg.create_all(engine, prompt_loader, validator, config)
        # → {ServiceType.DAILY_REPORT: DailyReportService(...), ...}
    """

    def __init__(self) -> None:
        self._registry: dict[ServiceType, ServiceRegistration] = {}

    def register(self, registration: ServiceRegistration) -> "ServiceRegistry":
        """Register a service. Returns self for chaining."""
        if registration.service_type in self._registry:
            logger.warning(
                "ServiceRegistry: '%s' already registered — overwriting",
                registration.service_type.value,
            )
        self._registry[registration.service_type] = registration
        logger.debug(
            "ServiceRegistry: registered '%s' → %s",
            registration.service_type.value,
            registration.service_class.__name__,
        )
        return self

    def get(self, service_type: ServiceType) -> ServiceRegistration:
        """Return the registration for *service_type*. Raises KeyError if not found."""
        if service_type not in self._registry:
            raise KeyError(
                f"Service '{service_type}' not registered. "
                f"Known types: {self.list_types()}"
            )
        return self._registry[service_type]

    def is_registered(self, service_type: ServiceType) -> bool:
        return service_type in self._registry

    def list_types(self) -> list[ServiceType]:
        """Return list of registered service types (insertion order)."""
        return list(self._registry.keys())

    def create_all(
        self,
        engine: BaseLLMProvider,
        prompt_loader: "PromptLoader",
        validator: ContentValidator,
        config: GenerationConfig,
    ) -> dict[ServiceType, BaseAIService]:
        """Instantiate every registered service with the given dependencies."""
        services: dict[ServiceType, BaseAIService] = {}
        for stype, reg in self._registry.items():
            services[stype] = reg.service_class(
                engine=engine,
                prompt_loader=prompt_loader,
                validator=validator,
                config=config,
            )
            logger.debug(
                "ServiceRegistry: created %s for '%s'",
                reg.service_class.__name__,
                stype.value,
            )
        return services

    def __len__(self) -> int:
        return len(self._registry)


# ── Default registry — the 4 built-in Sprint 5 services ──────────────────────
#
# Imports are local to avoid circular imports at module level:
# registry.py is in generation/services/, same package as the concrete classes.
#
# To add a new AI service in a future sprint:
#   1. Create generation/services/<name>.py (subclass BaseAIService)
#   2. Add a DEFAULT_SERVICE_REGISTRY.register(...) call here
#   Zero changes to AIServiceManager.

def _build_default_registry() -> ServiceRegistry:
    from generation.services.customer_update import CustomerUpdateService
    from generation.services.daily_report import DailyReportService
    from generation.services.material_reminder import MaterialReminderService
    from generation.services.safety_talk import SafetyTalkService

    reg = ServiceRegistry()
    reg.register(ServiceRegistration(
        service_type=ServiceType.DAILY_REPORT,
        service_class=DailyReportService,
        description="Formal Markdown daily site report for contractor records",
    ))
    reg.register(ServiceRegistration(
        service_type=ServiceType.CUSTOMER_UPDATE,
        service_class=CustomerUpdateService,
        description="Client-facing progress email (jargon-free)",
    ))
    reg.register(ServiceRegistration(
        service_type=ServiceType.SAFETY_TALK,
        service_class=SafetyTalkService,
        description="OSHA-referenced safety toolbox talk for crew briefing",
    ))
    reg.register(ServiceRegistration(
        service_type=ServiceType.MATERIAL_REMINDER,
        service_class=MaterialReminderService,
        description="Material procurement action list with priority levels",
    ))
    return reg


DEFAULT_SERVICE_REGISTRY = _build_default_registry()
