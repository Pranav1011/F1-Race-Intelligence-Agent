"""Sentry integration for error monitoring.

Provides:
- Error capture and alerting
- Performance monitoring
- User context tracking
- Custom breadcrumbs for debugging
"""

import logging
import os
from typing import Any

import sentry_sdk
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

logger = logging.getLogger(__name__)


def init_sentry(
    dsn: str | None = None,
    environment: str = "development",
    release: str | None = None,
    traces_sample_rate: float = 0.1,
    profiles_sample_rate: float = 0.1,
    enabled: bool = True,
) -> bool:
    """
    Initialize Sentry error monitoring.

    Args:
        dsn: Sentry DSN (or SENTRY_DSN env var)
        environment: Environment name (development, staging, production)
        release: Release version
        traces_sample_rate: Percentage of transactions to trace (0-1)
        profiles_sample_rate: Percentage of transactions to profile (0-1)
        enabled: Whether Sentry is enabled

    Returns:
        True if successfully initialized
    """
    if not enabled:
        logger.info("Sentry monitoring disabled")
        return False

    dsn = dsn or os.getenv("SENTRY_DSN")
    if not dsn:
        logger.warning(
            "Sentry DSN not configured. Set SENTRY_DSN env var to enable error monitoring."
        )
        return False

    try:
        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            release=release or os.getenv("APP_VERSION", "0.1.0"),
            # Performance monitoring
            traces_sample_rate=traces_sample_rate,
            profiles_sample_rate=profiles_sample_rate,
            # Integrations
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                StarletteIntegration(transaction_style="endpoint"),
                AsyncioIntegration(),
                LoggingIntegration(
                    level=logging.INFO,
                    event_level=logging.ERROR,
                ),
            ],
            # Additional settings
            send_default_pii=False,  # Don't send personally identifiable info
            attach_stacktrace=True,
            max_breadcrumbs=50,
            # Filter out health check noise
            before_send=_filter_events,
            before_send_transaction=_filter_transactions,
        )

        logger.info(f"Sentry initialized (environment: {environment})")
        return True

    except Exception as e:
        logger.error(f"Failed to initialize Sentry: {e}")
        return False


def _filter_events(event: dict, hint: dict) -> dict | None:
    """Filter out noisy or sensitive events."""
    # Filter out health check errors
    if "exception" in event:
        for exc in event.get("exception", {}).get("values", []):
            if "health" in str(exc.get("value", "")).lower():
                return None

    # Remove sensitive data from request
    if "request" in event:
        request = event["request"]
        # Remove auth headers
        if "headers" in request:
            headers = request["headers"]
            for sensitive_key in ["authorization", "x-api-key", "cookie"]:
                if sensitive_key in headers:
                    headers[sensitive_key] = "[Filtered]"

    return event


def _filter_transactions(event: dict, hint: dict) -> dict | None:
    """Filter out health check transactions."""
    transaction_name = event.get("transaction", "")
    if "/health" in transaction_name or "/ready" in transaction_name:
        return None
    return event


def capture_exception(
    exception: Exception,
    extra: dict | None = None,
    tags: dict | None = None,
    level: str = "error",
) -> str | None:
    """
    Capture an exception and send to Sentry.

    Args:
        exception: The exception to capture
        extra: Additional context data
        tags: Tags for categorization
        level: Severity level

    Returns:
        Event ID or None
    """
    try:
        with sentry_sdk.push_scope() as scope:
            if extra:
                for key, value in extra.items():
                    scope.set_extra(key, value)
            if tags:
                for key, value in tags.items():
                    scope.set_tag(key, value)
            scope.level = level

            event_id = sentry_sdk.capture_exception(exception)
            return event_id

    except Exception as e:
        logger.error(f"Failed to capture exception in Sentry: {e}")
        return None


def capture_message(
    message: str,
    level: str = "info",
    extra: dict | None = None,
    tags: dict | None = None,
) -> str | None:
    """
    Capture a message and send to Sentry.

    Args:
        message: The message to capture
        level: Severity level (info, warning, error)
        extra: Additional context data
        tags: Tags for categorization

    Returns:
        Event ID or None
    """
    try:
        with sentry_sdk.push_scope() as scope:
            if extra:
                for key, value in extra.items():
                    scope.set_extra(key, value)
            if tags:
                for key, value in tags.items():
                    scope.set_tag(key, value)

            event_id = sentry_sdk.capture_message(message, level=level)
            return event_id

    except Exception as e:
        logger.error(f"Failed to capture message in Sentry: {e}")
        return None


def set_user_context(
    user_id: str | None = None,
    email: str | None = None,
    username: str | None = None,
    ip_address: str | None = None,
):
    """
    Set user context for Sentry events.

    Args:
        user_id: User identifier
        email: User email
        username: Username
        ip_address: IP address
    """
    sentry_sdk.set_user({
        "id": user_id,
        "email": email,
        "username": username,
        "ip_address": ip_address,
    })


def clear_user_context():
    """Clear user context."""
    sentry_sdk.set_user(None)


def add_breadcrumb(
    message: str,
    category: str = "custom",
    level: str = "info",
    data: dict | None = None,
):
    """
    Add a breadcrumb for debugging.

    Args:
        message: Breadcrumb message
        category: Category (e.g., "agent", "tool", "llm")
        level: Level (debug, info, warning, error)
        data: Additional data
    """
    sentry_sdk.add_breadcrumb(
        message=message,
        category=category,
        level=level,
        data=data or {},
    )


def set_tag(key: str, value: str):
    """Set a tag on the current scope."""
    sentry_sdk.set_tag(key, value)


def set_context(name: str, data: dict):
    """Set context data on the current scope."""
    sentry_sdk.set_context(name, data)


class SentrySpan:
    """Context manager for Sentry performance spans."""

    def __init__(
        self,
        operation: str,
        description: str,
        data: dict | None = None,
    ):
        """
        Create a performance span.

        Args:
            operation: Operation type (e.g., "llm.call", "tool.execute")
            description: Human-readable description
            data: Additional span data
        """
        self.operation = operation
        self.description = description
        self.data = data or {}
        self._span = None

    def __enter__(self):
        self._span = sentry_sdk.start_span(
            op=self.operation,
            description=self.description,
        )
        if self._span:
            for key, value in self.data.items():
                self._span.set_data(key, value)
        return self._span

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._span:
            if exc_val:
                self._span.set_status("internal_error")
            else:
                self._span.set_status("ok")
            self._span.finish()
        return False


def span(operation: str, description: str, data: dict | None = None) -> SentrySpan:
    """
    Create a performance span context manager.

    Args:
        operation: Operation type
        description: Description
        data: Additional data

    Returns:
        SentrySpan context manager
    """
    return SentrySpan(operation, description, data)
