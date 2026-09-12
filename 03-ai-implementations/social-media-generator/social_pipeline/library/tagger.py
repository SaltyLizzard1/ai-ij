"""Vision tagging: turn an unlabelled photo into subject / mood / themes.

The Anthropic tagger sends a downscaled copy of the photo to Claude with a
JSON-schema-constrained response, so the tags always use the shared
THEMES / MOODS vocabulary the matcher expects.
"""

from __future__ import annotations

import base64
import io
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from ..errors import CaptionGenerationError, ImageIndexError
from ..models import MOODS, THEMES, ImageAsset, ImageTags

log = logging.getLogger(__name__)

TAG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "subject": {"type": "string", "description": "3-8 word noun phrase: what the photo is of"},
        "description": {"type": "string", "description": "One factual sentence describing the scene"},
        "keywords": {
            "type": "array",
            "items": {"type": "string"},
            "description": "8-20 lowercase search keywords incl. synonyms (objects, place type, activity, colours, time of day)",
        },
        "themes": {"type": "array", "items": {"type": "string", "enum": list(THEMES)}, "description": "1-4 themes, most dominant first"},
        "moods": {"type": "array", "items": {"type": "string", "enum": list(MOODS)}, "description": "1-3 moods, strongest first"},
        "alt_text": {"type": "string", "description": "Accessible alt text, under 125 characters"},
        "people_present": {"type": "boolean"},
        "text_present": {"type": "boolean", "description": "Readable text, signs, screens or documents visible"},
        "suitable_for_social": {
            "type": "boolean",
            "description": "false for screenshots, receipts, documents, accidental shots, private/identifying content, or very poor quality",
        },
    },
    "required": [
        "subject", "description", "keywords", "themes", "moods", "alt_text",
        "people_present", "text_present", "suitable_for_social",
    ],
    "additionalProperties": False,
}

TAG_PROMPT = (
    "Tag this photo for a personal travel/lifestyle social media library. "
    "Describe only what is visible. Use the allowed theme and mood values. "
    "Keywords should be plain, lowercase, and include obvious synonyms so text "
    "search can find the image (e.g. 'motorbike', 'scooter', 'moped')."
)


def prepare_image(path: str | Path, *, max_edge: int = 1024, quality: int = 85) -> tuple[bytes, str]:
    """Load, orient, downscale and JPEG-encode a photo for the vision API.

    Returns ``(jpeg_bytes, "image/jpeg")``. HEIC is supported when
    ``pillow-heif`` is installed.
    """
    p = Path(path)
    if not p.is_file():
        raise ImageIndexError(f"Image not found: {p}")
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:  # pragma: no cover - dependency declared in pyproject
        raise ImageIndexError("Pillow is required for vision tagging: pip install Pillow") from exc

    if p.suffix.lower() == ".heic":
        try:
            import pillow_heif  # type: ignore

            pillow_heif.register_heif_opener()
        except ImportError as exc:
            raise ImageIndexError(
                f"{p.name}: HEIC needs 'pillow-heif' (pip install pillow-heif)"
            ) from exc
    try:
        with Image.open(p) as im:
            im = ImageOps.exif_transpose(im)  # respect camera rotation
            im = im.convert("RGB")
            im.thumbnail((max_edge, max_edge))
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=quality, optimize=True)
    except OSError as exc:
        raise ImageIndexError(f"Could not decode image {p.name}: {exc}") from exc
    return buf.getvalue(), "image/jpeg"


class VisionTagger(Protocol):
    model_name: str

    def tag(self, image_bytes: bytes, media_type: str, *, hint: str | None = None) -> ImageTags: ...


class MockVisionTagger:
    """Deterministic tagger for tests and dry runs (no network)."""

    model_name = "mock-vision"

    def __init__(self, fixed: dict[str, Any] | None = None) -> None:
        self.fixed = fixed or {}
        self.calls = 0

    def tag(self, image_bytes: bytes, media_type: str, *, hint: str | None = None) -> ImageTags:
        self.calls += 1
        data = {
            "subject": "unlabelled photo",
            "description": f"A photo ({len(image_bytes)} bytes).",
            "keywords": ["photo"],
            "themes": ["home_daily_life"],
            "moods": ["calm"],
            "alt_text": "A photo.",
            "people_present": False,
            "text_present": False,
            "suitable_for_social": True,
        }
        data.update(self.fixed)
        tags = ImageTags.from_dict(data)
        tags.tagged_at = datetime.now(timezone.utc).isoformat()
        tags.tag_model = self.model_name
        return tags


class AnthropicVisionTagger:
    """Tags photos with Claude's vision input and structured JSON output."""

    def __init__(
        self,
        *,
        model: str = "claude-opus-5",
        api_key: str | None = None,
        effort: str = "low",
        timeout: float = 120.0,
        server_fallbacks: bool = True,
    ) -> None:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover
            raise ImageIndexError("Install the 'anthropic' package to use vision tagging") from exc
        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=2)
        self.model_name = model
        self.effort = effort
        self.server_fallbacks = server_fallbacks

    def tag(self, image_bytes: bytes, media_type: str, *, hint: str | None = None) -> ImageTags:
        anthropic = self._anthropic
        prompt = TAG_PROMPT if not hint else f"{TAG_PROMPT}\nContext: {hint}"
        request: dict[str, Any] = dict(
            model=self.model_name,
            max_tokens=8000,
            thinking={"type": "adaptive"},
            output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": TAG_SCHEMA}},
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": base64.standard_b64encode(image_bytes).decode("ascii"),
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
        try:
            if self.server_fallbacks:
                response = self._client.beta.messages.create(
                    betas=["server-side-fallback-2026-07-01"], fallbacks="default", **request
                )
            else:
                response = self._client.messages.create(**request)
        except anthropic.RateLimitError as exc:
            raise CaptionGenerationError(f"Vision tagging rate limited: {exc.message}", retryable=True) from exc
        except anthropic.APIStatusError as exc:
            raise CaptionGenerationError(
                f"Vision tagging API error {exc.status_code}: {exc.message}", retryable=exc.status_code >= 500
            ) from exc
        except anthropic.APIConnectionError as exc:
            raise CaptionGenerationError(f"Vision tagging connection error: {exc}", retryable=True) from exc

        if response.stop_reason == "refusal":
            raise CaptionGenerationError("Vision tagging refused by the model", retryable=False)
        if response.stop_reason == "max_tokens":
            raise CaptionGenerationError("Vision tagging output truncated (max_tokens)", retryable=False)
        text = next((b.text for b in response.content if b.type == "text"), None)
        if not text:
            raise CaptionGenerationError("Vision tagging returned no text block", retryable=True)
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise CaptionGenerationError(f"Vision tagging returned invalid JSON: {exc}", retryable=True) from exc
        tags = ImageTags.from_dict(data)
        tags.tagged_at = datetime.now(timezone.utc).isoformat()
        tags.tag_model = response.model
        return tags


def select_tag_candidates(
    images: list[ImageAsset],
    *,
    target_month: int,
    max_blur: float,
    min_contrast: float = 0.0,
    require_quality_record: bool = False,
    limit: int = 60,
) -> list[ImageAsset]:
    """Untagged photos worth spending API calls on: sharp, right month first."""
    def eligible(img: ImageAsset) -> bool:
        if img.is_tagged:
            return False
        if img.quality_source == "none":
            return not require_quality_record
        if img.blur is not None and img.blur > max_blur:
            return False
        if min_contrast and img.contrast is not None and img.contrast < min_contrast:
            return False
        return True

    def month_distance(img: ImageAsset) -> int:
        d = abs(img.month - target_month)
        return min(d, 12 - d)

    pool = [img for img in images if eligible(img)]
    pool.sort(key=lambda i: (month_distance(i), i.blur if i.blur is not None else 0.5, i.path))
    return pool[:limit]
