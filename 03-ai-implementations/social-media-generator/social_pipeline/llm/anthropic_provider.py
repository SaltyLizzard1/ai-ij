"""Claude via the official ``anthropic`` SDK with structured JSON output."""

from __future__ import annotations

import json
from typing import Any

from ..errors import CaptionGenerationError
from .base import JSONRequest, LLMResult


class AnthropicCaptionProvider:
    name = "anthropic"

    def __init__(
        self,
        *,
        model: str = "claude-opus-5",
        api_key: str | None = None,
        effort: str | None = None,
        timeout: float = 180.0,
        server_fallbacks: bool = True,
    ) -> None:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover
            raise CaptionGenerationError("Install the 'anthropic' package: pip install anthropic") from exc
        self._anthropic = anthropic
        # The SDK resolves credentials itself (ANTHROPIC_API_KEY or an `ant auth login` profile).
        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=2)
        self.model_name = model
        self.effort = effort
        self.server_fallbacks = server_fallbacks

    def complete_json(self, request: JSONRequest) -> LLMResult:
        anthropic = self._anthropic
        output_config: dict[str, Any] = {"format": {"type": "json_schema", "schema": request.schema}}
        if self.effort:
            output_config["effort"] = self.effort
        kwargs: dict[str, Any] = dict(
            model=self.model_name,
            max_tokens=request.max_tokens,
            # The system prompt is identical for every chunk of an article, so it
            # is cached; only the user turn changes.
            system=[{"type": "text", "text": request.system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": request.user}],
            thinking={"type": "adaptive"},
            output_config=output_config,
        )
        try:
            if self.server_fallbacks:
                response = self._client.beta.messages.create(
                    betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs
                )
            else:
                response = self._client.messages.create(**kwargs)
        except anthropic.AuthenticationError as exc:
            raise CaptionGenerationError(f"Anthropic auth failed: {exc.message}", retryable=False) from exc
        except anthropic.BadRequestError as exc:
            raise CaptionGenerationError(f"Anthropic rejected the request: {exc.message}", retryable=False) from exc
        except anthropic.RateLimitError as exc:
            raise CaptionGenerationError(f"Anthropic rate limit: {exc.message}", retryable=True) from exc
        except anthropic.APIStatusError as exc:
            raise CaptionGenerationError(
                f"Anthropic API error {exc.status_code}: {exc.message}", retryable=exc.status_code >= 500
            ) from exc
        except anthropic.APIConnectionError as exc:  # includes timeouts
            raise CaptionGenerationError(f"Anthropic connection error: {exc}", retryable=True) from exc

        if response.stop_reason == "refusal":
            detail = getattr(response, "stop_details", None)
            category = getattr(detail, "category", None) if detail else None
            raise CaptionGenerationError(f"Model refused the request (category={category})", retryable=False)
        if response.stop_reason == "max_tokens":
            raise CaptionGenerationError("Response truncated at max_tokens; raise JSONRequest.max_tokens", retryable=False)

        text = next((b.text for b in response.content if b.type == "text"), None)
        if not text:
            raise CaptionGenerationError("No text block in the model response", retryable=True)
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise CaptionGenerationError(f"Model returned invalid JSON: {exc}", retryable=True) from exc
        usage = response.usage
        return LLMResult(
            data=data,
            provider=self.name,
            model=response.model,
            usage={
                "input_tokens": getattr(usage, "input_tokens", 0) or 0,
                "output_tokens": getattr(usage, "output_tokens", 0) or 0,
                "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
                "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", 0) or 0,
            },
        )
