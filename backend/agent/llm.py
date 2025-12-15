"""
LLM Router

Implements fallback chain: DeepSeek (primary) -> Groq -> Gemini -> Ollama.
Handles rate limiting, errors, and automatic failover.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from langchain_community.chat_models import ChatOllama
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI  # DeepSeek uses OpenAI-compatible API
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)


class LLMProvider(str, Enum):
    """Available LLM providers."""

    DEEPSEEK = "deepseek"
    GROQ = "groq"
    GEMINI = "gemini"
    OLLAMA = "ollama"


@dataclass
class LLMConfig:
    """Configuration for LLM providers."""

    # DeepSeek (primary - excellent reasoning, free tier)
    deepseek_api_key: str | None = None
    deepseek_model: str = "deepseek-reasoner"  # R1 reasoning model
    deepseek_base_url: str = "https://api.deepseek.com"

    # Groq (fast backup - free tier)
    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    groq_fast_model: str = "llama-3.1-8b-instant"  # Fast planning model

    # Gemini (backup - free tier)
    google_api_key: str | None = None
    gemini_model: str = "gemini-2.0-flash-exp"

    # Ollama (local - can run DeepSeek R1 locally!)
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "deepseek-r1:8b"  # Best local reasoning model

    # General settings
    temperature: float = 0.7
    max_tokens: int = 4096


class RateLimitError(Exception):
    """Raised when rate limited by provider."""

    pass


class LLMRouter:
    """
    Routes LLM requests through fallback chain.

    Priority: DeepSeek -> Groq -> Gemini -> Ollama

    Supports two-stage routing:
    - Stage 1 (Planning): Fast 8B model for query understanding and tool selection
    - Stage 2 (Analysis): Capable 70B model for reasoning over retrieved data
    """

    def __init__(self, config: LLMConfig | None = None):
        """Initialize the LLM router."""
        self.config = config or LLMConfig()
        self._providers: dict[LLMProvider, BaseChatModel | None] = {}
        self._fast_providers: dict[LLMProvider, BaseChatModel | None] = {}  # Fast models for planning
        self._initialize_providers()
        self._current_provider: LLMProvider | None = None

    def _initialize_providers(self):
        """Initialize available LLM providers."""
        # DeepSeek (primary - best reasoning)
        if self.config.deepseek_api_key:
            try:
                self._providers[LLMProvider.DEEPSEEK] = ChatOpenAI(
                    api_key=self.config.deepseek_api_key,
                    base_url=self.config.deepseek_base_url,
                    model=self.config.deepseek_model,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                )
                logger.info(f"DeepSeek initialized with model {self.config.deepseek_model}")
            except Exception as e:
                logger.warning(f"Failed to initialize DeepSeek: {e}")
                self._providers[LLMProvider.DEEPSEEK] = None
        else:
            logger.info("DeepSeek API key not provided, skipping")
            self._providers[LLMProvider.DEEPSEEK] = None

        # Groq (fast backup)
        if self.config.groq_api_key:
            try:
                # Main capable model (70B)
                self._providers[LLMProvider.GROQ] = ChatGroq(
                    api_key=self.config.groq_api_key,
                    model=self.config.groq_model,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                )
                logger.info(f"Groq initialized with model {self.config.groq_model}")

                # Fast planning model (8B) - for two-stage routing
                self._fast_providers[LLMProvider.GROQ] = ChatGroq(
                    api_key=self.config.groq_api_key,
                    model=self.config.groq_fast_model,
                    temperature=0.3,  # Lower temp for planning
                    max_tokens=1024,  # Shorter responses for planning
                )
                logger.info(f"Groq fast model initialized: {self.config.groq_fast_model}")
            except Exception as e:
                logger.warning(f"Failed to initialize Groq: {e}")
                self._providers[LLMProvider.GROQ] = None
                self._fast_providers[LLMProvider.GROQ] = None
        else:
            logger.info("Groq API key not provided, skipping")
            self._providers[LLMProvider.GROQ] = None
            self._fast_providers[LLMProvider.GROQ] = None

        # Gemini (backup)
        if self.config.google_api_key:
            try:
                self._providers[LLMProvider.GEMINI] = ChatGoogleGenerativeAI(
                    google_api_key=self.config.google_api_key,
                    model=self.config.gemini_model,
                    temperature=self.config.temperature,
                    max_output_tokens=self.config.max_tokens,
                )
                logger.info(f"Gemini initialized with model {self.config.gemini_model}")
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini: {e}")
                self._providers[LLMProvider.GEMINI] = None
        else:
            logger.info("Google API key not provided, skipping Gemini")
            self._providers[LLMProvider.GEMINI] = None

        # Ollama (local fallback - always try to initialize)
        try:
            self._providers[LLMProvider.OLLAMA] = ChatOllama(
                base_url=self.config.ollama_base_url,
                model=self.config.ollama_model,
                temperature=self.config.temperature,
            )
            logger.info(f"Ollama initialized with model {self.config.ollama_model}")
        except Exception as e:
            logger.warning(f"Failed to initialize Ollama: {e}")
            self._providers[LLMProvider.OLLAMA] = None

    def get_available_providers(self) -> list[LLMProvider]:
        """Get list of available providers in priority order."""
        # Priority: Groq (fast, free) -> DeepSeek API -> Gemini -> Ollama (local fallback)
        # Note: Ollama with DeepSeek R1 on CPU is too slow for real-time chat (3+ min/query)
        # Only prioritize Ollama if running on GPU in the future
        priority_order = [
            LLMProvider.GROQ,  # Fast and free - best for real-time chat
            LLMProvider.DEEPSEEK,  # DeepSeek API (if key provided)
            LLMProvider.GEMINI,  # Google Gemini backup
            LLMProvider.OLLAMA,  # Local fallback (slow on CPU)
        ]
        return [p for p in priority_order if self._providers.get(p) is not None]

    def get_llm(self, provider: LLMProvider | None = None) -> BaseChatModel:
        """
        Get an LLM instance.

        Args:
            provider: Specific provider to use, or None for auto-selection

        Returns:
            LLM instance

        Raises:
            RuntimeError: If no providers are available
        """
        if provider and self._providers.get(provider):
            return self._providers[provider]

        # Auto-select based on priority
        for p in self.get_available_providers():
            if self._providers.get(p):
                self._current_provider = p
                return self._providers[p]

        raise RuntimeError("No LLM providers available")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((RateLimitError,)),
    )
    async def ainvoke(
        self,
        messages: list[BaseMessage],
        **kwargs: Any,
    ) -> BaseMessage:
        """
        Invoke LLM with automatic fallback.

        Args:
            messages: Messages to send to LLM
            **kwargs: Additional arguments for the LLM

        Returns:
            LLM response message
        """
        providers = self.get_available_providers()

        for provider in providers:
            try:
                llm = self._providers[provider]
                logger.debug(f"Trying provider: {provider.value}")

                response = await llm.ainvoke(messages, **kwargs)
                self._current_provider = provider
                logger.info(f"Success with provider: {provider.value}")
                return response

            except Exception as e:
                error_str = str(e).lower()

                # Check for rate limiting
                if "rate" in error_str or "limit" in error_str or "429" in error_str:
                    logger.warning(f"Rate limited by {provider.value}: {e}")
                    continue

                # Check for quota exceeded
                if "quota" in error_str or "exceeded" in error_str:
                    logger.warning(f"Quota exceeded for {provider.value}: {e}")
                    continue

                # Other errors - log and try next provider
                logger.error(f"Error with {provider.value}: {e}")
                continue

        raise RuntimeError("All LLM providers failed")

    def invoke(
        self,
        messages: list[BaseMessage],
        **kwargs: Any,
    ) -> BaseMessage:
        """
        Synchronous invoke with automatic fallback.

        Args:
            messages: Messages to send to LLM
            **kwargs: Additional arguments for the LLM

        Returns:
            LLM response message
        """
        providers = self.get_available_providers()

        for provider in providers:
            try:
                llm = self._providers[provider]
                logger.debug(f"Trying provider: {provider.value}")

                response = llm.invoke(messages, **kwargs)
                self._current_provider = provider
                logger.info(f"Success with provider: {provider.value}")
                return response

            except Exception as e:
                error_str = str(e).lower()

                if "rate" in error_str or "limit" in error_str or "429" in error_str:
                    logger.warning(f"Rate limited by {provider.value}: {e}")
                    continue

                if "quota" in error_str or "exceeded" in error_str:
                    logger.warning(f"Quota exceeded for {provider.value}: {e}")
                    continue

                logger.error(f"Error with {provider.value}: {e}")
                continue

        raise RuntimeError("All LLM providers failed")

    @property
    def current_provider(self) -> LLMProvider | None:
        """Get the currently active provider."""
        return self._current_provider

    def get_fast_llm(self, provider: LLMProvider | None = None) -> BaseChatModel:
        """
        Get a fast LLM instance for planning/routing tasks.

        Uses smaller, faster models (e.g., 8B instead of 70B) for:
        - Query understanding
        - Tool selection
        - Data filtering decisions

        Args:
            provider: Specific provider to use, or None for auto-selection

        Returns:
            Fast LLM instance
        """
        if provider and self._fast_providers.get(provider):
            return self._fast_providers[provider]

        # Auto-select - prefer Groq for fastest inference
        for p in [LLMProvider.GROQ, LLMProvider.GEMINI]:
            if self._fast_providers.get(p):
                return self._fast_providers[p]

        # Fallback to main providers if no fast models available
        return self.get_llm(provider)

    async def ainvoke_fast(
        self,
        messages: list[BaseMessage],
        **kwargs: Any,
    ) -> BaseMessage:
        """
        Invoke fast LLM for planning tasks.

        Use this for:
        - Understanding what data is needed
        - Selecting which tools to call
        - Quick classification tasks

        Args:
            messages: Messages to send to LLM
            **kwargs: Additional arguments

        Returns:
            LLM response message
        """
        providers = [LLMProvider.GROQ, LLMProvider.GEMINI]

        for provider in providers:
            if self._fast_providers.get(provider):
                try:
                    llm = self._fast_providers[provider]
                    logger.debug(f"Fast invoke with: {provider.value}")
                    response = await llm.ainvoke(messages, **kwargs)
                    return response
                except Exception as e:
                    logger.warning(f"Fast invoke failed for {provider.value}: {e}")
                    continue

        # Fallback to regular invoke
        logger.info("No fast models available, using regular invoke")
        return await self.ainvoke(messages, **kwargs)

    async def two_stage_invoke(
        self,
        planning_messages: list[BaseMessage],
        analysis_messages: list[BaseMessage],
        **kwargs: Any,
    ) -> tuple[BaseMessage, BaseMessage]:
        """
        Two-stage LLM invocation for optimal speed and quality.

        Stage 1: Fast model plans what data is needed
        Stage 2: Capable model analyzes the data

        Args:
            planning_messages: Messages for stage 1 (planning)
            analysis_messages: Messages for stage 2 (analysis)
            **kwargs: Additional arguments

        Returns:
            Tuple of (planning_response, analysis_response)
        """
        # Stage 1: Fast planning
        planning_response = await self.ainvoke_fast(planning_messages, **kwargs)

        # Stage 2: Deep analysis
        analysis_response = await self.ainvoke(analysis_messages, **kwargs)

        return planning_response, analysis_response


def create_llm_router(
    deepseek_api_key: str | None = None,
    groq_api_key: str | None = None,
    google_api_key: str | None = None,
    ollama_base_url: str = "http://ollama:11434",
) -> LLMRouter:
    """
    Factory function to create an LLM router.

    Args:
        deepseek_api_key: DeepSeek API key (primary)
        groq_api_key: Groq API key (fast backup)
        google_api_key: Google API key for Gemini
        ollama_base_url: Ollama server URL

    Returns:
        Configured LLM router
    """
    config = LLMConfig(
        deepseek_api_key=deepseek_api_key,
        groq_api_key=groq_api_key,
        google_api_key=google_api_key,
        ollama_base_url=ollama_base_url,
    )
    return LLMRouter(config)
