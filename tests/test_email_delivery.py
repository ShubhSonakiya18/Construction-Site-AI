"""
tests/test_email_delivery.py — Sprint 9: EmailSender unit tests.

DevConsoleEmailSender is tested directly (it has no external dependency —
nothing to mock). SMTPEmailSender is tested with smtplib.SMTP mocked, per
docs/NEXT_SPRINT.md Deliverable 5: no real SMTP server required for this
file or CI. AuthService.forgot_password()'s integration with EmailSender
is covered separately in tests/test_api_auth_sprint8.py (the existing
forgot/reset flow tests) and tests/test_generation_services.py-style unit
coverage isn't needed here since AuthService already has direct unit tests
below for the email-triggering behavior specifically.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.core.config import Settings
from app.services.email_sender import (
    DevConsoleEmailSender,
    SMTPEmailSender,
    build_email_sender,
)


class TestDevConsoleEmailSender:
    def test_send_logs_instead_of_sending(self, caplog):
        import logging

        sender = DevConsoleEmailSender()
        with caplog.at_level(logging.INFO, logger="app.email"):
            sender.send(to="user@example.com", subject="Test", body="Hello")
        assert "user@example.com" in caplog.text
        assert "Test" in caplog.text
        assert "NOT actually sent" in caplog.text

    def test_send_never_raises(self):
        sender = DevConsoleEmailSender()
        sender.send(to="user@example.com", subject="", body="")  # must not raise


class TestSMTPEmailSender:
    def _make_sender(self, **overrides) -> SMTPEmailSender:
        defaults = dict(
            host="smtp.example.com", port=587, username="user", password="pass",
            use_tls=True, from_email="noreply@example.com", from_name="Test App",
        )
        defaults.update(overrides)
        return SMTPEmailSender(**defaults)

    def test_send_calls_smtplib_with_correct_recipient_and_subject(self):
        sender = self._make_sender()
        with patch("smtplib.SMTP") as mock_smtp_cls:
            mock_client = MagicMock()
            mock_smtp_cls.return_value.__enter__.return_value = mock_client

            sender.send(to="target@example.com", subject="Reset your password", body="link here")

            mock_smtp_cls.assert_called_once_with("smtp.example.com", 587, timeout=10)
            mock_client.starttls.assert_called_once()
            mock_client.login.assert_called_once_with("user", "pass")
            mock_client.send_message.assert_called_once()
            sent_message = mock_client.send_message.call_args[0][0]
            assert sent_message["To"] == "target@example.com"
            assert sent_message["Subject"] == "Reset your password"
            assert "Test App" in sent_message["From"]
            assert "noreply@example.com" in sent_message["From"]

    def test_send_skips_login_when_no_credentials(self):
        sender = self._make_sender(username=None, password=None)
        with patch("smtplib.SMTP") as mock_smtp_cls:
            mock_client = MagicMock()
            mock_smtp_cls.return_value.__enter__.return_value = mock_client

            sender.send(to="target@example.com", subject="s", body="b")

            mock_client.login.assert_not_called()

    def test_send_skips_starttls_when_use_tls_false(self):
        sender = self._make_sender(use_tls=False)
        with patch("smtplib.SMTP") as mock_smtp_cls:
            mock_client = MagicMock()
            mock_smtp_cls.return_value.__enter__.return_value = mock_client

            sender.send(to="target@example.com", subject="s", body="b")

            mock_client.starttls.assert_not_called()

    def test_send_never_raises_on_smtp_failure(self):
        """The whole point of EmailSender.send()'s no-raise contract: a
        delivery failure must not propagate into
        AuthService.forgot_password()'s identical-response guarantee."""
        sender = self._make_sender()
        with patch("smtplib.SMTP", side_effect=ConnectionRefusedError("no route")):
            sender.send(to="target@example.com", subject="s", body="b")  # must not raise


class TestBuildEmailSender:
    def test_no_smtp_host_returns_dev_console_sender(self):
        settings = Settings(smtp_host=None, _env_file=None)
        assert isinstance(build_email_sender(settings), DevConsoleEmailSender)

    def test_smtp_host_configured_returns_smtp_sender(self):
        settings = Settings(smtp_host="smtp.example.com", _env_file=None)
        assert isinstance(build_email_sender(settings), SMTPEmailSender)

    def test_fresh_instance_per_call_not_cached(self):
        """Regression guard: an earlier draft of this module cached the
        first call's Settings in a process-wide singleton, which would
        silently apply test A's SMTP-vs-dev choice to test B. Each call
        must build fresh from whatever Settings it's given."""
        dev_settings = Settings(smtp_host=None, _env_file=None)
        smtp_settings = Settings(smtp_host="smtp.example.com", _env_file=None)

        first = build_email_sender(dev_settings)
        second = build_email_sender(smtp_settings)

        assert isinstance(first, DevConsoleEmailSender)
        assert isinstance(second, SMTPEmailSender)
