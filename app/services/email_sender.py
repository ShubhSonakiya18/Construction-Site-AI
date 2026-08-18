"""
app/services/email_sender.py — EmailSender protocol + implementations.

Sprint 9. Wires real (or dev-safe) email delivery into
AuthService.forgot_password() — see docs/AUTHENTICATION_ARCHITECTURE.md
"Forgot Password" for why Sprint 8 explicitly deferred this and returned
the raw reset token directly in non-production API responses instead.

Why a Protocol, not an ABC:
    Same reasoning as app/core/rate_limit.py's RateLimiter: one small
    method, no shared implementation to inherit, only a shared shape.
    Structural typing gets static checking on call sites without forcing
    every implementation through a common base class.

Why two implementations, chosen by whether Settings.smtp_host is set:
    - DevConsoleEmailSender: logs the email instead of sending it. Zero
      setup for local dev/CI — matches this project's existing "no paid
      services, sensible zero-config default" posture (e.g. MemoryRateLimiter
      needing no Redis, ADR-041). This is also what removes the raw-token-
      in-API-response behavior Sprint 8 used as its only way to test the
      reset flow: the token is still visible, just in the server log
      instead of the HTTP response — no longer something a client (or an
      attacker intercepting the response) can read.
    - SMTPEmailSender: real delivery via smtplib + a real SMTP account
      (any free-tier provider, or a self-hosted relay) — no paid SaaS
      dependency, consistent with ADR-005/ADR-007's constraint.

Why the choice is made once, in get_email_sender() (mirroring
get_rate_limiter()'s process-wide-singleton pattern), not per-call:
    Settings.smtp_host doesn't change mid-process; constructing a fresh
    SMTPEmailSender per email would be wasted allocation for no benefit
    (smtplib.SMTP itself opens a fresh connection per send() call
    regardless — see SMTPEmailSender.send() for why persistent connections
    are deliberately NOT used here).
"""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from typing import Protocol

from fastapi import Depends

from app.api.dependencies import get_app_settings
from app.core.config import Settings

logger = logging.getLogger("app.email")


class EmailSender(Protocol):
    """Structural interface every email delivery implementation satisfies."""

    def send(self, *, to: str, subject: str, body: str) -> None:
        """Send a plain-text email. Must not raise for the caller's sake —
        implementations catch their own delivery errors and log them,
        matching safe_log_event()'s fail-open posture (ADR-040): a reset
        email failing to send must never surface as a 500 to the user who
        submitted forgot-password, since AuthService.forgot_password()'s
        whole design is "always return the same generic response whether
        or not the email exists" — an email-delivery exception propagating
        out would be a different, distinguishable failure mode and reopen
        the account-enumeration side channel that method's docstring
        specifically closes.
        """
        ...


class DevConsoleEmailSender:
    """Logs the email instead of sending it. The Sprint 9 replacement for
    Sprint 8's raw-token-in-API-response dev-mode behavior — the token is
    still visible for manual testing, just in the server log instead of
    the HTTP response body.
    """

    def send(self, *, to: str, subject: str, body: str) -> None:
        logger.info(
            "DevConsoleEmailSender: email NOT actually sent (no SMTP_HOST "
            "configured). to=%s subject=%r\n%s",
            to, subject, body,
        )


class SMTPEmailSender:
    """Real delivery via smtplib. Works with any SMTP provider (Gmail SMTP
    with an app password, a free-tier transactional-email provider, or a
    self-hosted relay for on-prem deployments) — nothing here is tied to a
    specific vendor.
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        use_tls: bool,
        from_email: str,
        from_name: str,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._use_tls = use_tls
        self._from_email = from_email
        self._from_name = from_name

    def send(self, *, to: str, subject: str, body: str) -> None:
        # A fresh connection per send(), not a persistent/pooled one: this
        # method fires at most once per forgot-password request (already
        # rate-limited upstream, Settings.rate_limit_forgot_password_attempts),
        # so connection-pooling overhead is not worth the added statefulness
        # (idle-connection expiry, thread-safety) for a class constructed
        # once per process and called rarely.
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = f"{self._from_name} <{self._from_email}>"
        message["To"] = to
        message.set_content(body)

        try:
            with smtplib.SMTP(self._host, self._port, timeout=10) as client:
                if self._use_tls:
                    client.starttls()
                if self._username and self._password:
                    client.login(self._username, self._password)
                client.send_message(message)
            logger.info("SMTPEmailSender: sent to=%s subject=%r", to, subject)
        except Exception:
            # Never raises — see EmailSender.send()'s docstring on why a
            # delivery failure must not propagate into
            # AuthService.forgot_password()'s generic-response contract.
            logger.exception("SMTPEmailSender: failed to send to=%s", to)


def build_email_sender(settings: Settings) -> EmailSender:
    """Build the EmailSender for these Settings — SMTPEmailSender if
    settings.smtp_host is configured, DevConsoleEmailSender otherwise.

    Deliberately NOT a process-wide singleton (unlike get_rate_limiter()
    in app/core/rate_limit.py): a RateLimiter's whole purpose is sharing
    counters across requests within one process, but an EmailSender has no
    cross-request state to share — SMTPEmailSender.send() opens its own
    fresh connection per call regardless (see that method's docstring).
    A singleton here would only add a bug: because Settings can differ per
    instance (tests build their own via the test_settings fixture, exactly
    like get_app_settings()'s own docstring explains), caching on first
    call would let whichever test ran first silently decide every later
    test's sender. Constructing fresh per call has no real cost and no
    such hazard — called from the get_email_sender() FastAPI dependency
    below, so "per call" in practice means "per request," which is
    exactly right.
    """
    if settings.smtp_host:
        return SMTPEmailSender(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            use_tls=settings.smtp_use_tls,
            from_email=settings.smtp_from_email,
            from_name=settings.smtp_from_name,
        )
    return DevConsoleEmailSender()


def get_email_sender(settings: Settings = Depends(get_app_settings)) -> EmailSender:
    """FastAPI dependency — Depends(get_email_sender) in app/api/v1/auth.py."""
    return build_email_sender(settings)
