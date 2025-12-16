"""Observability module for F1 Race Intelligence Agent.

Provides:
- Langfuse integration for LLM tracing and prompt analytics (v3 API)
- Sentry integration for error monitoring and alerting
- Structured logging with correlation IDs
"""

from observability.langfuse_tracer import (
    LangfuseTracer,
    get_langfuse_handler,
    get_tracer,
    observe,
    LANGCHAIN_CALLBACK_AVAILABLE,
)
from observability.sentry_integration import (
    init_sentry,
    capture_exception,
    set_user_context,
    add_breadcrumb,
    span,
)

__all__ = [
    # Langfuse
    "LangfuseTracer",
    "get_langfuse_handler",
    "get_tracer",
    "observe",
    "LANGCHAIN_CALLBACK_AVAILABLE",
    # Sentry
    "init_sentry",
    "capture_exception",
    "set_user_context",
    "add_breadcrumb",
    "span",
]
