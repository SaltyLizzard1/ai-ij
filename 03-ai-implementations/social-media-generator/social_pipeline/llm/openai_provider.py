"""OpenAI Chat Completions with a strict JSON schema response format."""

from __future__ import annotations

import json

from ..errors import CaptionGenerationError
from .base import JSONRequest, LLMResult


class OpenAICaptionProvider:
    name = "openai"

    def __init__(self, *, model: str = "gpt-4o", api_key: str | None = None, timeout: float = 180.0) -> None:
        try:
            import openai
        except ImportError as exc:  # pragma: no cover
            raise CaptionGenerationError("Install the 'openai' package: pip install openai") from exc
        self._openai = openai
        self._client = openai.OpenAI(api_key=api_key, timeout=timeout, max_retries=2)
        self.model_name = model

    def complete_json(self, request: JSONRequest) -> LLMResult:
        openai = self._openai
        try:
            response = self._client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": request.system},
                    {"role": "user", "content": request.user},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "social_posts", "schema": request.schema, "strict": True},
                },
                max_tokens=min(request.max_tokens, 8192),
            )
        except openai.AuthenticationError as exc:
            raise CaptionGenerationError(f"OpenAI auth failed: {exc}", retryable=False) from exc
        except openai.BadRequestError as exc:
            raise CaptionGenerationError(f"OpenAI rejected the request: {exc}", retryable=False) from exc
        except openai.RateLimitError as exc:
            raise CaptionGenerationError(f"OpenAI rate limit: {exc}", retryable=True) from exc
        except openai.APIStatusError as exc:
            raise CaptionGenerationError(f"OpenAI API error {exc.status_code}: {exc}", retryable=exc.status_code >= 500) from exc
        except openai.APIConnectionError as exc:
            raise CaptionGenerationError(f"OpenAI connection error: {exc}", retryable=True) from exc

        choice = response.choices[0]
        if getattr(choice.message, "refusal", None):
            raise CaptionGenerationError(f"Model refused: {choice.message.refusal}", retryable=False)
        if choice.finish_reason == "length":
            raise CaptionGenerationError("Response truncated (finish_reason=length)", retryable=False)
        try:
            data = json.loads(choice.message.content or "")
        except json.JSONDecodeError as exc:
            raise CaptionGenerationError(f"Model returned invalid JSON: {exc}", retryable=True) from exc
        usage = response.usage
        return LLMResult(
            data=data,
            provider=self.name,
            model=response.model,
            usage={
                "input_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                "output_tokens": getattr(usage, "completion_tokens", 0) or 0,
            },
        )
