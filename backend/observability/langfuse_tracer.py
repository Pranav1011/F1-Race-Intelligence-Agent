"""Langfuse integration for LLM tracing.

Provides comprehensive tracing for:
- LangGraph agent executions
- Individual LLM calls
- Tool executions
- RAG retrievals

Uses Langfuse v3 API with OpenTelemetry-based tracing.
"""

import logging
import os
from contextlib import contextmanager
from typing import Any, Generator

from langfuse import Langfuse, observe

logger = logging.getLogger(__name__)

# Try to import LangChain callback handler (optional - requires langfuse[langchain])
try:
    from langfuse.callback import CallbackHandler
    LANGCHAIN_CALLBACK_AVAILABLE = True
except ImportError:
    CallbackHandler = None
    LANGCHAIN_CALLBACK_AVAILABLE = False
    logger.debug("LangChain callback handler not available (install langfuse[langchain])")


class LangfuseTracer:
    """
    Langfuse tracer for F1 Race Intelligence Agent.

    Uses Langfuse v3 API with:
    - Direct trace/span creation
    - @observe decorator for automatic tracing
    - Optional LangChain callback integration
    - Score tracking for response quality
    """

    def __init__(
        self,
        public_key: str | None = None,
        secret_key: str | None = None,
        host: str | None = None,
        enabled: bool = True,
    ):
        """
        Initialize Langfuse tracer.

        Args:
            public_key: Langfuse public key (or LANGFUSE_PUBLIC_KEY env var)
            secret_key: Langfuse secret key (or LANGFUSE_SECRET_KEY env var)
            host: Langfuse host URL (or LANGFUSE_HOST env var)
            enabled: Whether tracing is enabled
        """
        self.enabled = enabled
        self.public_key = public_key or os.getenv("LANGFUSE_PUBLIC_KEY")
        self.secret_key = secret_key or os.getenv("LANGFUSE_SECRET_KEY")
        self.host = host or os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

        self._client: Langfuse | None = None
        self._initialized = False

    def initialize(self) -> bool:
        """
        Initialize Langfuse client.

        Returns:
            True if successfully initialized
        """
        if not self.enabled:
            logger.info("Langfuse tracing disabled")
            return False

        if not self.public_key or not self.secret_key:
            logger.warning(
                "Langfuse credentials not configured. "
                "Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY env vars."
            )
            self.enabled = False
            return False

        try:
            self._client = Langfuse(
                public_key=self.public_key,
                secret_key=self.secret_key,
                host=self.host,
            )

            # Verify authentication
            if self._client.auth_check():
                self._initialized = True
                logger.info(f"Langfuse initialized successfully (host: {self.host})")
                return True
            else:
                logger.warning("Langfuse authentication failed")
                self.enabled = False
                return False

        except Exception as e:
            logger.error(f"Failed to initialize Langfuse: {e}")
            self.enabled = False
            return False

    def get_callback_handler(
        self,
        session_id: str | None = None,
        user_id: str | None = None,
        trace_name: str = "f1-agent",
        metadata: dict | None = None,
        tags: list[str] | None = None,
    ) -> Any | None:
        """
        Get a LangChain callback handler for tracing.

        Args:
            session_id: Session identifier for grouping traces
            user_id: User identifier
            trace_name: Name for the trace
            metadata: Additional metadata
            tags: Tags for filtering

        Returns:
            CallbackHandler or None if tracing disabled or unavailable
        """
        if not self.enabled or not self._initialized:
            return None

        if not LANGCHAIN_CALLBACK_AVAILABLE:
            logger.debug("LangChain callback handler not available")
            return None

        try:
            handler = CallbackHandler(
                public_key=self.public_key,
                secret_key=self.secret_key,
                host=self.host,
                session_id=session_id,
                user_id=user_id,
                trace_name=trace_name,
                metadata=metadata or {},
                tags=tags or ["f1-ria"],
            )
            return handler
        except Exception as e:
            logger.error(f"Failed to create callback handler: {e}")
            return None

    def start_trace(
        self,
        name: str,
        session_id: str | None = None,
        user_id: str | None = None,
        input_data: Any = None,
        metadata: dict | None = None,
        tags: list[str] | None = None,
    ) -> Any:
        """
        Start a new trace for custom tracking.

        Args:
            name: Trace name
            session_id: Session identifier
            user_id: User identifier
            input_data: Input data for the trace
            metadata: Additional metadata
            tags: Tags for filtering

        Returns:
            Trace context or None
        """
        if not self.enabled or not self._client:
            return None

        try:
            # Use start_as_current_observation to create a trace
            trace = self._client.start_as_current_observation(
                name=name,
                session_id=session_id,
                user_id=user_id,
                input=input_data,
                metadata=metadata or {},
                tags=tags or ["f1-ria"],
            )
            return trace
        except Exception as e:
            logger.error(f"Failed to start trace: {e}")
            return None

    def start_span(
        self,
        name: str,
        input_data: Any = None,
        metadata: dict | None = None,
    ) -> Any:
        """
        Start a span within the current trace.

        Args:
            name: Span name
            input_data: Input data for the span
            metadata: Additional metadata

        Returns:
            Span context or None
        """
        if not self.enabled or not self._client:
            return None

        try:
            span = self._client.start_as_current_span(
                name=name,
                input=input_data,
                metadata=metadata or {},
            )
            return span
        except Exception as e:
            logger.error(f"Failed to start span: {e}")
            return None

    def start_generation(
        self,
        name: str,
        model: str,
        input_data: Any = None,
        metadata: dict | None = None,
    ) -> Any:
        """
        Start an LLM generation span.

        Args:
            name: Generation name
            model: Model identifier
            input_data: Input/prompt data
            metadata: Additional metadata

        Returns:
            Generation context or None
        """
        if not self.enabled or not self._client:
            return None

        try:
            gen = self._client.start_as_current_generation(
                name=name,
                model=model,
                input=input_data,
                metadata=metadata or {},
            )
            return gen
        except Exception as e:
            logger.error(f"Failed to start generation: {e}")
            return None

    @contextmanager
    def span(
        self,
        name: str,
        input_data: Any = None,
        metadata: dict | None = None,
    ) -> Generator[Any, None, None]:
        """
        Context manager for creating spans.

        Args:
            name: Span name
            input_data: Input data for the span
            metadata: Additional metadata

        Yields:
            Span object
        """
        if not self.enabled or not self._client:
            yield None
            return

        span_ctx = None
        try:
            span_ctx = self._client.start_as_current_span(
                name=name,
                input=input_data,
                metadata=metadata or {},
            )
            yield span_ctx
        except Exception as e:
            logger.error(f"Span error: {e}")
            yield None
        finally:
            if span_ctx:
                try:
                    span_ctx.__exit__(None, None, None)
                except Exception:
                    pass

    def score_current_trace(
        self,
        name: str,
        value: float,
        comment: str | None = None,
    ):
        """
        Add a score to the current trace.

        Args:
            name: Score name (e.g., "accuracy", "relevance")
            value: Score value (0-1)
            comment: Optional comment
        """
        if not self.enabled or not self._client:
            return

        try:
            self._client.score_current_trace(
                name=name,
                value=value,
                comment=comment,
            )
        except Exception as e:
            logger.error(f"Failed to score trace: {e}")

    def create_score(
        self,
        trace_id: str,
        name: str,
        value: float,
        comment: str | None = None,
    ):
        """
        Add a score to a specific trace.

        Args:
            trace_id: Trace identifier
            name: Score name (e.g., "accuracy", "relevance")
            value: Score value (0-1)
            comment: Optional comment
        """
        if not self.enabled or not self._client:
            return

        try:
            self._client.create_score(
                trace_id=trace_id,
                name=name,
                value=value,
                comment=comment,
            )
        except Exception as e:
            logger.error(f"Failed to create score: {e}")

    def get_current_trace_id(self) -> str | None:
        """Get the current trace ID."""
        if not self.enabled or not self._client:
            return None
        try:
            return self._client.get_current_trace_id()
        except Exception:
            return None

    def get_current_observation_id(self) -> str | None:
        """Get the current observation/span ID."""
        if not self.enabled or not self._client:
            return None
        try:
            return self._client.get_current_observation_id()
        except Exception:
            return None

    def flush(self):
        """Flush pending events to Langfuse."""
        if self._client:
            try:
                self._client.flush()
            except Exception as e:
                logger.error(f"Failed to flush Langfuse: {e}")

    def shutdown(self):
        """Shutdown Langfuse client."""
        if self._client:
            try:
                self._client.flush()
                self._client.shutdown()
            except Exception as e:
                logger.error(f"Failed to shutdown Langfuse: {e}")


# Global tracer instance
_tracer: LangfuseTracer | None = None


def get_tracer(
    public_key: str | None = None,
    secret_key: str | None = None,
    host: str | None = None,
    enabled: bool = True,
) -> LangfuseTracer:
    """Get or create the global Langfuse tracer."""
    global _tracer
    if _tracer is None:
        _tracer = LangfuseTracer(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
            enabled=enabled,
        )
        _tracer.initialize()
    return _tracer


def get_langfuse_handler(
    session_id: str | None = None,
    user_id: str | None = None,
    trace_name: str = "f1-agent",
    metadata: dict | None = None,
) -> Any | None:
    """
    Convenience function to get a LangChain callback handler.

    Args:
        session_id: Session identifier
        user_id: User identifier
        trace_name: Trace name
        metadata: Additional metadata

    Returns:
        CallbackHandler or None
    """
    tracer = get_tracer()
    return tracer.get_callback_handler(
        session_id=session_id,
        user_id=user_id,
        trace_name=trace_name,
        metadata=metadata,
    )


# Re-export observe decorator for use in other modules
__all__ = [
    "LangfuseTracer",
    "get_tracer",
    "get_langfuse_handler",
    "observe",
    "LANGCHAIN_CALLBACK_AVAILABLE",
]
