"""Plain dataclasses shared by every stage of the pipeline."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

SUPPORTED_PLATFORMS = ("linkedin", "x", "instagram")


def stable_id(*parts: str) -> str:
    """Deterministic short id from any number of string parts."""
    digest = hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()
    return digest[:16]


def normalize_term(term: str) -> str:
    """Lower-case, strip punctuation and do very light singularisation.

    This keeps "Mountains" / "mountain" / "mountain," comparable without a
    stemming dependency. It is intentionally conservative.
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
            "moods": list(self.moods),
            "post_score": round(self.post_score, 3),
            "char_count": self.char_count,
        }


@dataclass
class ImageAsset:
    id: str
    path: str  # relative to the library root (portable across machines)
    file_name: str
    month: int  # 1-12
    year: int | None = None
    subject: str | None = None
    mood: str | None = None
    description: str | None = None
    keywords: list[str] = field(default_factory=list)
    used_count: int = 0
    last_used_at: str | None = None

    def search_terms(self) -> dict[str, str]:
        """Normalised term -> attribute name it came from."""
        terms: dict[str, str] = {}
        for kw in self.keywords:
            n = normalize_term(kw)
            if n:
                terms.setdefault(n, "keyword")
                for part in n.split():
                    terms.setdefault(part, "keyword")
        if self.subject:
            n = normalize_term(self.subject)
            terms[n] = "subject"
            for part in n.split():
                terms.setdefault(part, "subject")
        if self.description:
            for part in re.findall(r"[a-zA-Z][a-zA-Z-]{2,}", self.description):
                terms.setdefault(normalize_term(part), "description")
        return terms

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ImageMatch:
    image: ImageAsset
    score: float
    reasons: list[str] = field(default_factory=list)
    is_fallback: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "image_id": self.image.id,
            "path": self.image.path,
            "month": self.image.month,
            "year": self.image.year,
            "subject": self.image.subject,
            "mood": self.image.mood,
            "keywords": list(self.image.keywords),
            "description": self.image.description,
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

    @property
    def full_text(self) -> str:
        tags = " ".join(self.hashtags)
        if not tags:
            return self.body.strip()
        return f"{self.body.strip()}\n\n{tags}"

    @property
    def char_count(self) -> int:
        return len(self.full_text)

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "body": self.body,
            "hashtags": list(self.hashtags),
            "full_text": self.full_text,
            "char_count": self.char_count,
            "suggested_post_at": self.suggested_post_at,
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
