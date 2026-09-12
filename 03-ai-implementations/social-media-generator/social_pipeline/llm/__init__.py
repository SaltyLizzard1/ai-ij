"""LLM providers behind one small interface (see ``base.py``)."""

from .base import CaptionProvider, JSONRequest, LLMResult
from .mock_provider import MockCaptionProvider

__all__ = ["CaptionProvider", "JSONRequest", "LLMResult", "MockCaptionProvider", "build_provider"]


def build_provider(settings):  # type: ignore[no-untyped-def]
    """Instantiate the provider named in ``settings.llm_provider``."""
    name = settings.llm_provider
    if name == "anthropic":
        from .anthropic_provider import AnthropicCaptionProvider

        return AnthropicCaptionProvider(
            model=settings.resolved_model,
            api_key=settings.anthropic_api_key,
            effort=settings.llm_effort,
            timeout=settings.llm_timeout_seconds,
            server_fallbacks=settings.anthropic_server_fallbacks,
        )
    if name == "openai":
        from .openai_provider import OpenAICaptionProvider

        return OpenAICaptionProvider(
            model=settings.resolved_model,
            api_key=settings.openai_api_key,
            timeout=settings.llm_timeout_seconds,
        )
    if name == "mock":
        return MockCaptionProvider()
    raise ValueError(f"Unknown LLM provider {name!r}")
