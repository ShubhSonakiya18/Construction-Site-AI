"""generation.services — Four AI service implementations."""

from generation.services.customer_update import CustomerUpdateService
from generation.services.daily_report import DailyReportService
from generation.services.material_reminder import MaterialReminderService
from generation.services.safety_talk import SafetyTalkService

__all__ = [
    "DailyReportService",
    "CustomerUpdateService",
    "SafetyTalkService",
    "MaterialReminderService",
]
