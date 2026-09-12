"""Plain dataclasses shared by every stage of the pipeline."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

SUPPORTED_PLATFORMS = ("linkedin", "x", "instagram", "facebook")

# Controlled vocabulary used on BOTH sides of the match: the chunk analyser
# maps article text onto these themes with a lexicon, and the vision tagger
# is constrained (via JSON schema enum) to the same list. Matching on a
# shared vocabulary is far more robust than free-text keyword overlap alone.
THEMES = (
    "city_streets",
    "nature_landscape",
    "mountains",
    "beach_water",
    "food_drink",
    "cafe_coworking",
    "home_daily_life",
    "transport_road",
    "people_community",
    "solo_moment",
    "work_laptop",
    "planning_paperwork",
    "markets_shopping",
    "temples_culture",
    "animals",
    "night_lights",
    "weather_seasons",
    "travel_moving",
    "health_wellbeing",
    "celebration",
)

MOODS = (
    "calm",
    "energetic",
    "inspiring",
    "adventurous",
    "reflective",
    "playful",
    "professional",
    "cozy",
    "melancholic",
    "celebratory",
)

PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".insv", ".lrv"}


def stable_id(*parts: str) -> str:
    """Deterministic short id from any number of string parts."""
    digest = hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()
    return digest[:16]


def normalize_term(term: str) -> str:
    """Lower-case, strip punctuation and do very light singularisation.

    Keeps "Mountains" / "mountain" / "mountain," comparable without a
    stemming dependency. Intentionally conservative.
    """
    t = re.sub(r"[^a-z0-9\s-]", "", term.lower()).strip()
    t = re.sub(r"\s+", " ", t)
    if len(t) > 4 and t.endswith("ies"):
        return t[:-3] + "y"
    if len(t) > 4 and t.endswith("sses"):
        return t[:-2]
    if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
        return t[:-1]
    return t


@dataclass
class Article:
    id: str
    title: str
    source_format: str  # "html" | "markdown"
    raw_content: str
    content_hash: str
    source_url: str | None = None

    @classmethod
    def create(
        cls,
        raw_content: str,
        *,
        title: str,
        source_format: str,
        source_url: str | None = None,
    ) -> "Article":
        content_hash = hashlib.sha256(raw_content.encode("utf-8")).hexdigest()
        # A URL identifies an article across re-runs even if it was edited;
        # otherwise the content itself is the identity.
        article_id = stable_id(source_url) if source_url else stable_id(content_hash)
        return cls(
            id=article_id,
            title=title,
            source_format=source_format,
            raw_content=raw_content,
            content_hash=content_hash,
            source_url=source_url,
        )


@dataclass
class Chunk:
    index: int
    kind: str  # "section" | "list" | "quote" | "hook"
    heading: str | None
    text: str
    context: str | None = None  # surrounding paragraph for hooks/quotes
    keywords: list[str] = field(default_factory=list)
    themes: list[str] = field(default_factory=list)
    moods: list[str] = field(default_factory=list)
    post_score: float = 0.0
    id: str | None = None
    article_id: str | None = None

    @property
    def char_count(self) -> int:
        return len(self.text)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "index": self.index,
            "kind": self.kind,
            "heading": self.heading,
            "text": self.text,
            "context": self.context,
            "keywords": list(self.keywords),
            "themes": list(self.themes),
            "moods": list(self.moods),
            "post_score": round(self.post_score, 3),
            "char_count": self.char_count,
        }


@dataclass
class ImageTags:
    """What the vision model says the photo shows. Absent until tagged."""

    subject: str
    description: str
    keywords: list[str]
    themes: list[str]
    moods: list[str]
    alt_text: str
    people_present: bool = False
    text_present: bool = False
    suitable_for_social: bool = True
    tagged_at: str | None = None
    tag_model: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ImageTags":
        return cls(
            subject=str(data.get("subject", "")),
            description=str(data.get("description", "")),
            keywords=[str(k) for k in data.get("keywords", [])],
            themes=[t for t in data.get("themes", []) if t in THEMES],
            moods=[m for m in data.get("moods", []) if m in MOODS],
            alt_text=str(data.get("alt_text", "")),
            people_present=bool(data.get("people_present", False)),
            text_present=bool(data.get("text_present", False)),
            suitable_for_social=bool(data.get("suitable_for_social", True)),
            tagged_at=data.get("tagged_at"),
            tag_model=data.get("tag_model"),
        )


@dataclass
class ImageAsset:
    id: str
    path: str  # relative to the library root, forward slashes
    file_name: str
    month: int  # 1-12, from the YYYY-MM folder
    year: int | None = None
    width: int | None = None
    height: int | None = None
    blur: float | None = None  # higher = blurrier (from blur2.csv)
    contrast: float | None = None
    brightness: float | None = None  # p99 column in blur2.csv
    quality_source: str = "none"  # "records" | "none"
    tags: ImageTags | None = None
    used_count: int = 0
    last_used_at: str | None = None

    @property
    def is_tagged(self) -> bool:
        return self.tags is not None

    @property
    def orientation(self) -> str | None:
        if not self.width or not self.height:
            return None
        if self.width > self.height * 1.1:
            return "landscape"
        if self.height > self.width * 1.1:
            return "portrait"
        return "square"

    def search_terms(self) -> dict[str, str]:
        """Normalised term -> attribute name it came from (tagged images only)."""
        terms: dict[str, str] = {}
        if not self.tags:
            return terms
        for kw in self.tags.keywords:
            n = normalize_term(kw)
            if n:
                terms.setdefault(n, "keyword")
                for part in n.split():
                    terms.setdefault(part, "keyword")
        if self.tags.subject:
            n = normalize_term(self.tags.subject)
            terms[n] = "subject"
            for part in n.split():
                terms.setdefault(part, "subject")
        for part in re.findall(r"[a-zA-Z][a-zA-Z-]{2,}", self.tags.description or ""):
            terms.setdefault(normalize_term(part), "description")
        return terms

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["orientation"] = self.orientation
        return d


@dataclass
class ImageMatch:
    image: ImageAsset
    score: float
    reasons: list[str] = field(default_factory=list)
    is_fallback: bool = False

    def to_dict(self) -> dict[str, Any]:
        img = self.image
        return {
            "image_id": img.id,
            "path": img.path,
            "month": img.month,
            "year": img.year,
            "orientation": img.orientation,
            "blur": img.blur,
            "subject": img.tags.subject if img.tags else None,
            "mood": list(img.tags.moods) if img.tags else [],
            "themes": list(img.tags.themes) if img.tags else [],
            "keywords": list(img.tags.keywords) if img.tags else [],
            "description": img.tags.description if img.tags else None,
            "match_score": round(self.score, 3),
            "match_reasons": list(self.reasons),
            "is_fallback": self.is_fallback,
        }


@dataclass
class PlatformPost:
    platform: str
    body: str
    hashtags: list[str]
    suggested_post_at: str | None = None  # ISO-8601 with timezone
    alternate_hooks: list[str] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        tags = " ".join(self.hashtags)
        if not tags:
            return self.body.strip()
        return f"{self.body.strip()}\n\n{tags}"

    @property
    def char_count(self) -> int:
        return len(self.full_text)

    @property
    def word_count(self) -> int:
        return len(self.body.split())

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "body": self.body,
            "hashtags": list(self.hashtags),
            "full_text": self.full_text,
            "char_count": self.char_count,
            "word_count": self.word_count,
            "suggested_post_at": self.suggested_post_at,
            "alternate_hooks": list(self.alternate_hooks),
        }


@dataclass
class PostPackage:
    id: str
    article_id: str
    chunk: Chunk
    match: ImageMatch
    suggested_post_date: date
    platforms: dict[str, PlatformPost]
    image_alt_text: str = ""
    theme: str = ""
    provider: str = ""
    model: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "post_id": self.id,
            "article_id": self.article_id,
            "theme": self.theme,
            "chunk": self.chunk.to_dict(),
            "image": self.match.to_dict(),
            "image_alt_text": self.image_alt_text,
            "suggested_post_date": self.suggested_post_date.isoformat(),
            "platforms": {name: post.to_dict() for name, post in self.platforms.items()},
            "generation": {"provider": self.provider, "model": self.model},
        }
