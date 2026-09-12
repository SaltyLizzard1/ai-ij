from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class JSONRequest:
    """A single 'give me JSON matching this schema' call."""

    system: str
    user: str
    schema: dict[str, Any]
    payload: dict[str, Any] = field(default_factory=dict)  # structured copy for the mock provider
    max_tokens: int = 16000


@dataclass
class LLMResult:
    data: dict[str, Any]
    provider: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)


class CaptionProvider(Protocol):
    name: str
    model_name: str

    def complete_json(self, request: JSONRequest) -> LLMResult: ...
