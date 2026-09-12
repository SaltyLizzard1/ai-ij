"""Score tagged photos against a text chunk.

Signals, in order of weight:

1. Shared **themes** (controlled vocabulary on both sides)
2. Shared **moods**
3. Keyword / subject overlap (free text, normalised)
4. **Month**: exact match preferred, neighbouring months tolerated, or
   strictly enforced with ``strict_month``
5. Quality: sharper photos win ties; blurry ones sink
6. Reuse penalty so the same photo is not picked for every post
"""

from __future__ import annotations

from dataclasses import dataclass

from ..errors import NoImageMatchError
from ..models import Chunk, ImageAsset, ImageMatch, normalize_term


@dataclass(frozen=True)
class MatchWeights:
    theme: float = 3.0
    theme_primary_bonus: float = 1.0  # both sides agree on the dominant theme
    mood: float = 1.0
    keyword: float = 0.6
    keyword_cap: float = 3.0
    subject: float = 1.0
    month_exact: float = 2.0
    month_adjacent: float = 0.5
    month_other: float = -1.0
    blur: float = -2.0  # multiplied by blur score (0..1)
    used: float = -1.0  # per previous use
    text_present: float = -0.5
    people_present_solo: float = -1.0  # chunk is a "solo_moment" but photo has people


def month_distance(a: int, b: int) -> int:
    d = abs(a - b) % 12
    return min(d, 12 - d)


class ImageMatcher:
    def __init__(self, *, weights: MatchWeights | None = None, strict_month: bool = False) -> None:
        self.w = weights or MatchWeights()
        self.strict_month = strict_month

    def score(self, chunk: Chunk, image: ImageAsset, target_month: int) -> tuple[float, list[str]]:
        w = self.w
        reasons: list[str] = []
        score = 0.0

        dist = month_distance(image.month, target_month)
        if dist == 0:
            score += w.month_exact
            reasons.append("same month")
        elif dist == 1:
            score += w.month_adjacent
            reasons.append("adjacent month")
        else:
            score += w.month_other

        if image.blur is not None:
            score += w.blur * image.blur
        if image.used_count:
            score += w.used * image.used_count
            reasons.append(f"used {image.used_count}x before")

        tags = image.tags
        if tags is None:
            return score, reasons + ["untagged"]

        shared_themes = [t for t in chunk.themes if t in tags.themes]
        if shared_themes:
            score += w.theme * len(shared_themes)
            reasons.append("themes: " + ", ".join(shared_themes))
            if chunk.themes and tags.themes and chunk.themes[0] == tags.themes[0]:
                score += w.theme_primary_bonus
                reasons.append("primary theme agrees")

        shared_moods = [m for m in chunk.moods if m in tags.moods]
        if shared_moods:
            score += w.mood * len(shared_moods)
            reasons.append("moods: " + ", ".join(shared_moods))

        chunk_terms: set[str] = set()
        for kw in chunk.keywords:
            n = normalize_term(kw)
            if n:
                chunk_terms.add(n)
                chunk_terms.update(p for p in n.split() if len(p) > 2)
        image_terms = image.search_terms()
        hits = sorted(t for t in chunk_terms if t in image_terms)
        if hits:
            kw_score = min(w.keyword * len(hits), w.keyword_cap)
            subj_hits = [t for t in hits if image_terms[t] == "subject"]
            score += kw_score + (w.subject if subj_hits else 0.0)
            reasons.append("keywords: " + ", ".join(hits[:5]))

        if tags.text_present:
            score += w.text_present
        if "solo_moment" in chunk.themes and tags.people_present:
            score += w.people_present_solo
        return score, reasons

    def rank(
        self,
        chunk: Chunk,
        images: list[ImageAsset],
        *,
        target_month: int,
        exclude_ids: set[str] | None = None,
        top_k: int = 5,
    ) -> list[ImageMatch]:
        exclude_ids = exclude_ids or set()
        matches: list[ImageMatch] = []
        for img in images:
            if img.id in exclude_ids:
                continue
            if img.tags is not None and not img.tags.suitable_for_social:
                continue
            if self.strict_month and img.month != target_month:
                continue
            s, reasons = self.score(chunk, img, target_month)
            matches.append(ImageMatch(image=img, score=s, reasons=reasons))
        matches.sort(key=lambda m: (m.score, -(m.image.blur or 0.0), m.image.path), reverse=True)
        return matches[:top_k]

    def best(
        self,
        chunk: Chunk,
        images: list[ImageAsset],
        *,
        target_month: int,
        exclude_ids: set[str] | None = None,
    ) -> ImageMatch:
        """Best tagged match, else the sharpest untagged photo of the month as a fallback."""
        tagged = [i for i in images if i.is_tagged]
        ranked = self.rank(chunk, tagged, target_month=target_month, exclude_ids=exclude_ids, top_k=1)
        if ranked:
            return ranked[0]
        untagged = [i for i in images if not i.is_tagged and i.id not in (exclude_ids or set())]
        if self.strict_month:
            untagged = [i for i in untagged if i.month == target_month]
        if not untagged:
            raise NoImageMatchError("No eligible images in the library for this chunk")
        untagged.sort(key=lambda i: (month_distance(i.month, target_month), i.blur if i.blur is not None else 0.5, i.used_count))
        img = untagged[0]
        return ImageMatch(image=img, score=0.0, reasons=["fallback: sharpest untagged photo"], is_fallback=True)
