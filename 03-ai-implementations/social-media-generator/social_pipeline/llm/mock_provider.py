"""Deterministic provider for tests and ``--dry-run``: no network, no cost."""

from __future__ import annotations

import re

from .base import JSONRequest, LLMResult


class MockCaptionProvider:
    name = "mock"
    model_name = "mock-1"

    def __init__(self) -> None:
        self.calls: list[JSONRequest] = []

    def complete_json(self, request: JSONRequest) -> LLMResult:
        self.calls.append(request)
        payload = request.payload
        chunk_text: str = payload.get("chunk_text", "")
        platforms: list[str] = payload.get("platforms", [])
        keywords: list[str] = payload.get("keywords", [])
        limits: dict[str, int] = payload.get("char_limits", {})
        sentences = [s for s in re.split(r"(?<=[.!?])\s+", chunk_text.strip()) if s]
        hook = sentences[0] if sentences else chunk_text[:100]
        body = " ".join(sentences[:3]) if sentences else chunk_text
        out: dict[str, object] = {"image_alt_text": payload.get("image_alt_text") or "Photo", "theme": keywords[0] if keywords else "general"}
        for p in platforms:
            limit = limits.get(p, 2000)
            tags = ["#" + re.sub(r"[^a-z0-9]", "", k.lower()) for k in keywords[:2]] if payload.get("allow_hashtags", True) else []
            text = body if len(body) <= limit - 40 else hook[: limit - 40]
            out[p] = {"body": text, "hashtags": tags, "alternate_hooks": [hook, hook[:60] + "...", "Here is what changed.", "Not what I expected."]}
        return LLMResult(data=out, provider=self.name, model=self.model_name, usage={"input_tokens": 0, "output_tokens": 0})
