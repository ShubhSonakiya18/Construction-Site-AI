"""
tests/test_service_registry.py — Unit tests for Sprint 5.1 ServiceRegistry.

Tests cover:
  - register() and get()
  - is_registered()
  - list_types()
  - create_all() instantiates all registered services with correct types
  - get() raises KeyError for unknown types
  - Overwrite on duplicate register
  - DEFAULT_SERVICE_REGISTRY has all 4 built-in services
  - AIServiceManager uses registry (via service_registry= parameter)
  - len() reflects count
"""
from __future__ import annotations

import pytest

from extraction.engines.base_engine import BaseLLMProvider
from generation.config import GenerationConfig
from generation.models.outputs import ServiceType
from generation.prompts.loader import PromptLoader
from generation.services.base_service import BaseAIService
from generation.services.customer_update import CustomerUpdateService
from generation.services.daily_report import DailyReportService
from generation.services.material_reminder import MaterialReminderService
from generation.services.registry import (
    DEFAULT_SERVICE_REGISTRY,
    ServiceRegistration,
    ServiceRegistry,
)
from generation.services.safety_talk import SafetyTalkService
from generation.validators.content_validator import ContentValidator


# ── Test double ──────────────────────────────────────────────────────────────

class _MockEngine(BaseLLMProvider):
    @property
    def model_name(self): return "mock"
    @property
    def host(self): return "mock://local"
    def is_available(self): return True
    def extract(self, prompt): return "text", {}


def _make_deps():
    return (
        _MockEngine(),
        PromptLoader("generation/prompts"),
        ContentValidator(),
        GenerationConfig(),
    )


# ── ServiceRegistry basic operations ─────────────────────────────────────────

class TestServiceRegistryBasics:
    def test_empty_registry_has_no_types(self):
        reg = ServiceRegistry()
        assert reg.list_types() == []

    def test_register_and_get(self):
        reg = ServiceRegistry()
        reg.register(ServiceRegistration(
            service_type=ServiceType.DAILY_REPORT,
            service_class=DailyReportService,
            description="Daily report",
        ))
        result = reg.get(ServiceType.DAILY_REPORT)
        assert result.service_type is ServiceType.DAILY_REPORT
        assert result.service_class is DailyReportService

    def test_register_returns_self_for_chaining(self):
        reg = ServiceRegistry()
        result = reg.register(ServiceRegistration(
            service_type=ServiceType.DAILY_REPORT,
            service_class=DailyReportService,
            description="",
        ))
        assert result is reg

    def test_is_registered_true_after_register(self):
        reg = ServiceRegistry()
        reg.register(ServiceRegistration(
            service_type=ServiceType.CUSTOMER_UPDATE,
            service_class=CustomerUpdateService,
            description="",
        ))
        assert reg.is_registered(ServiceType.CUSTOMER_UPDATE) is True

    def test_is_registered_false_for_unknown(self):
        reg = ServiceRegistry()
        assert reg.is_registered(ServiceType.DAILY_REPORT) is False

    def test_list_types_returns_all_registered(self):
        reg = ServiceRegistry()
        reg.register(ServiceRegistration(
            service_type=ServiceType.DAILY_REPORT,
            service_class=DailyReportService,
            description="",
        ))
        reg.register(ServiceRegistration(
            service_type=ServiceType.SAFETY_TALK,
            service_class=SafetyTalkService,
            description="",
        ))
        types = reg.list_types()
        assert ServiceType.DAILY_REPORT in types
        assert ServiceType.SAFETY_TALK in types
        assert len(types) == 2

    def test_len_reflects_count(self):
        reg = ServiceRegistry()
        assert len(reg) == 0
        reg.register(ServiceRegistration(
            service_type=ServiceType.DAILY_REPORT,
            service_class=DailyReportService,
            description="",
        ))
        assert len(reg) == 1


# ── create_all ────────────────────────────────────────────────────────────────

class TestCreateAll:
    def test_create_all_returns_dict_keyed_by_service_type(self):
        reg = ServiceRegistry()
        reg.register(ServiceRegistration(
            service_type=ServiceType.DAILY_REPORT,
            service_class=DailyReportService,
            description="",
        ))
        engine, loader, validator, config = _make_deps()
        services = reg.create_all(engine, loader, validator, config)
        assert ServiceType.DAILY_REPORT in services

    def test_create_all_instantiates_correct_class(self):
        reg = ServiceRegistry()
        reg.register(ServiceRegistration(
            service_type=ServiceType.DAILY_REPORT,
            service_class=DailyReportService,
            description="",
        ))
        engine, loader, validator, config = _make_deps()
        services = reg.create_all(engine, loader, validator, config)
        assert isinstance(services[ServiceType.DAILY_REPORT], DailyReportService)

    def test_create_all_injects_engine(self):
        reg = ServiceRegistry()
        reg.register(ServiceRegistration(
            service_type=ServiceType.DAILY_REPORT,
            service_class=DailyReportService,
            description="",
        ))
        engine, loader, validator, config = _make_deps()
        services = reg.create_all(engine, loader, validator, config)
        svc = services[ServiceType.DAILY_REPORT]
        assert svc._engine is engine

    def test_create_all_with_multiple_services(self):
        reg = ServiceRegistry()
        for stype, cls in [
            (ServiceType.DAILY_REPORT, DailyReportService),
            (ServiceType.CUSTOMER_UPDATE, CustomerUpdateService),
            (ServiceType.SAFETY_TALK, SafetyTalkService),
            (ServiceType.MATERIAL_REMINDER, MaterialReminderService),
        ]:
            reg.register(ServiceRegistration(
                service_type=stype, service_class=cls, description=""
            ))
        engine, loader, validator, config = _make_deps()
        services = reg.create_all(engine, loader, validator, config)
        assert len(services) == 4
        assert all(isinstance(svc, BaseAIService) for svc in services.values())


# ── Error cases ───────────────────────────────────────────────────────────────

class TestServiceRegistryErrors:
    def test_get_unknown_raises_key_error(self):
        reg = ServiceRegistry()
        with pytest.raises(KeyError, match="not registered"):
            reg.get(ServiceType.DAILY_REPORT)

    def test_duplicate_register_overwrites(self):
        reg = ServiceRegistry()
        reg.register(ServiceRegistration(
            service_type=ServiceType.DAILY_REPORT,
            service_class=DailyReportService,
            description="First",
        ))
        reg.register(ServiceRegistration(
            service_type=ServiceType.DAILY_REPORT,
            service_class=CustomerUpdateService,  # wrong class, just for test
            description="Second",
        ))
        result = reg.get(ServiceType.DAILY_REPORT)
        assert result.description == "Second"
        assert result.service_class is CustomerUpdateService


# ── DEFAULT_SERVICE_REGISTRY ──────────────────────────────────────────────────

class TestDefaultServiceRegistry:
    def test_has_four_built_in_services(self):
        assert len(DEFAULT_SERVICE_REGISTRY) == 4

    def test_all_four_service_types_registered(self):
        types = DEFAULT_SERVICE_REGISTRY.list_types()
        assert ServiceType.DAILY_REPORT in types
        assert ServiceType.CUSTOMER_UPDATE in types
        assert ServiceType.SAFETY_TALK in types
        assert ServiceType.MATERIAL_REMINDER in types

    def test_daily_report_class_is_correct(self):
        reg = DEFAULT_SERVICE_REGISTRY.get(ServiceType.DAILY_REPORT)
        assert reg.service_class is DailyReportService

    def test_customer_update_class_is_correct(self):
        reg = DEFAULT_SERVICE_REGISTRY.get(ServiceType.CUSTOMER_UPDATE)
        assert reg.service_class is CustomerUpdateService

    def test_safety_talk_class_is_correct(self):
        reg = DEFAULT_SERVICE_REGISTRY.get(ServiceType.SAFETY_TALK)
        assert reg.service_class is SafetyTalkService

    def test_material_reminder_class_is_correct(self):
        reg = DEFAULT_SERVICE_REGISTRY.get(ServiceType.MATERIAL_REMINDER)
        assert reg.service_class is MaterialReminderService

    def test_all_entries_have_descriptions(self):
        for stype in DEFAULT_SERVICE_REGISTRY.list_types():
            reg = DEFAULT_SERVICE_REGISTRY.get(stype)
            assert len(reg.description) > 0

    def test_create_all_with_default_registry(self):
        engine, loader, validator, config = _make_deps()
        services = DEFAULT_SERVICE_REGISTRY.create_all(engine, loader, validator, config)
        assert len(services) == 4
        for stype, svc in services.items():
            assert isinstance(svc, BaseAIService)
            assert svc.service_type is stype


# ── AIServiceManager uses registry ───────────────────────────────────────────

class TestManagerUsesRegistry:
    def test_manager_accepts_custom_registry(self):
        """AIServiceManager.service_registry= parameter works."""
        from generation.manager import AIServiceManager

        # Registry with only one service
        reg = ServiceRegistry()
        reg.register(ServiceRegistration(
            service_type=ServiceType.DAILY_REPORT,
            service_class=DailyReportService,
            description="",
        ))
        engine = _MockEngine()
        manager = AIServiceManager(
            engine=engine,
            service_registry=reg,
        )
        assert ServiceType.DAILY_REPORT in manager._services
        # Only daily_report was registered
        assert len(manager._services) == 1

    def test_manager_default_uses_all_four_services(self):
        """Default manager (no custom registry) has all 4 services."""
        from generation.manager import AIServiceManager

        engine = _MockEngine()
        manager = AIServiceManager(engine=engine)
        assert len(manager._services) == 4
