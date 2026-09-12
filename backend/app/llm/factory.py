"""Factory that builds the configured LLM provider from settings."""
from __future__ import annotations

from functools import lru_cache

from ..config import Settings, get_settings
from ..logging_config import get_logger
from .base import LLMProvider
from .mock import MockLLMProvider

logger = get_logger(__name__)


def build_llm_provider(settings: Settings) -> LLMProvider:
    provider = (settings.llm_provider or "mock").strip().lower()

    if provider == "mock":
        return MockLLMProvider(
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )

    if provider == "openai":
        from .openai_provider import OpenAIProvider

        return OpenAIProvider(
            model=settings.llm_model,
            api_key=settings.openai_api_key,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )

    if provider == "anthropic":
        from .anthropic_provider import AnthropicProvider

        return AnthropicProvider(
            model=settings.llm_model,
            api_key=settings.anthropic_api_key,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )

    raise ValueError(
        f"Unknown LLM_PROVIDER '{settings.llm_provider}'. "
        "Expected one of: mock, openai, anthropic."
    )


@lru_cache
def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    provider = build_llm_provider(settings)
    logger.info(
        "Initialized LLM provider=%s model=%s", provider.name, provider.model
    )
    return provider
