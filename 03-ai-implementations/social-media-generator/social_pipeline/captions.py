"""Turn a (chunk, image) pair into platform-specific posts via an LLM.

Flow: build prompt -> provider.complete_json -> validate against platform and
brand rules -> one corrective retry with the violations spelled out ->
auto-fix what can be fixed mechanically -> return PlatformPosts + warnings.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from .errors import CaptionGenerationError
from .llm.base import CaptionProvider, JSONRequest
from .models import Chunk, ImageMatch, PlatformPost
from .platforms import PLATFORMS, PlatformSpec
from .utils import with_retries

log = logging.getLogger(__name__)

EM_DASH = "—"
_FINANCIAL = re.compile(r"(\$|€|£|฿)\s?\d|\b\d[\d,\.]*\s?(baht|dollars?|usd|eur|gbp|thb|bucks|k\b)", re.I)


@dataclass
class CaptionRules:
    brand_voice: str
    brand_name: str | None = None
    forbid_em_dashes: bool = True
    forbid_financial_figures: bool = False
    allow_hashtags: bool = True
    banned_phrases: tuple[str, ...] = ()


@dataclass
class CaptionResult:
    posts: dict[str, PlatformPost]
    image_alt_text: str
    theme: str
    provider: str
    model: str
    warnings: list[str] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)


def build_schema(platforms: list[str]) -> dict[str, Any]:
    post_schema = {
        "type": "object",
        "properties": {
            "body": {"type": "string", "description": "The full post text, hook as the first line"},
            "hashtags": {"type": "array", "items": {"type": "string"}, "description": "Each starting with #, may be empty"},
            "alternate_hooks": {"type": "array", "items": {"type": "string"}, "description": "Exactly 4 unused alternative first lines"},
        },
        "required": ["body", "hashtags", "alternate_hooks"],
        "additionalProperties": False,
    }
    properties: dict[str, Any] = {p: post_schema for p in platforms}
    properties["image_alt_text"] = {"type": "string", "description": "Alt text for the paired photo, under 125 characters"}
    properties["theme"] = {"type": "string", "description": "2-5 word label for the post's angle"}
    return {
        "type": "object",
        "properties": properties,
        "required": list(platforms) + ["image_alt_text", "theme"],
        "additionalProperties": False,
    }


def build_system_prompt(rules: CaptionRules, platforms: list[str]) -> str:
    lines = [
        "You write social media posts for a real person from excerpts of their own long-form articles.",
        "Rewrite the excerpt as a native post for each requested platform. Keep the author's facts, numbers and",
        "first-person voice; never invent events, places, prices or people that are not in the excerpt.",
        "The paired photo context tells you what the reader will see; reference it naturally when it fits, never describe it literally.",
        "",
        "Method: write five candidate hooks first, pick the strongest as the first line of the post,",
        "then return the four you did not use as alternate_hooks.",
        "",
        "BRAND VOICE",
        rules.brand_voice.strip(),
        "",
        "HARD RULES",
    ]
    if rules.forbid_em_dashes:
        lines.append("- Never use an em dash (—) or en dash (–). Use a comma, a full stop, or rewrite the sentence.")
    if rules.forbid_financial_figures:
        lines.append("- No financial figures of any kind: no prices, costs, revenue, currency amounts or money numbers.")
    if not rules.allow_hashtags:
        lines.append("- No hashtags at all: return an empty hashtags list for every platform.")
    if rules.banned_phrases:
        lines.append("- Never use these words or phrases: " + "; ".join(rules.banned_phrases) + ".")
    lines.append("- Respect every platform's character limit including hashtags.")
    lines.append("- Do not mention that the text comes from an article unless the excerpt itself does.")
    lines.append("")
    lines.append("PLATFORM RULES")
    for p in platforms:
        s: PlatformSpec = PLATFORMS[p]
        tag_rule = (
            f"{s.hashtags[0]}-{s.hashtags[1]} hashtags" if rules.allow_hashtags and s.hashtags[1] > 0 else "no hashtags"
        )
        words = f", max {s.max_words} words" if s.max_words else ""
        lines.append(
            f"- {s.display_name} ({p}): max {s.max_chars} characters{words}, ideal {s.ideal_chars[0]}-{s.ideal_chars[1]} characters, "
            f"{tag_rule}, first {s.hook_chars} characters must work as a standalone hook. {s.style}"
        )
    return "\n".join(lines)


def build_user_prompt(article_title: str, chunk: Chunk, match: ImageMatch, platforms: list[str]) -> str:
    img = match.image
    tags = img.tags
    parts = [
        f"ARTICLE TITLE: {article_title}",
        f"SECTION HEADING: {chunk.heading or '(none)'}",
        f"EXCERPT TYPE: {chunk.kind}",
        "EXCERPT:",
        chunk.text,
    ]
    if chunk.context and chunk.context != chunk.text:
        parts += ["", "SURROUNDING PARAGRAPH (for context only):", chunk.context]
    parts += ["", "PAIRED PHOTO:"]
    if tags:
        parts += [
            f"- subject: {tags.subject}",
            f"- description: {tags.description}",
            f"- mood: {', '.join(tags.moods) or 'n/a'}",
            f"- themes: {', '.join(tags.themes) or 'n/a'}",
            f"- orientation: {img.orientation or 'unknown'}",
        ]
    else:
        parts.append(f"- untagged photo from {img.year or ''}-{img.month:02d} (orientation {img.orientation or 'unknown'})")
    parts += ["", f"PLATFORMS: {', '.join(platforms)}", "Return JSON only."]
    return "\n".join(parts)


def _violations(platform: str, post: PlatformPost, rules: CaptionRules) -> list[str]:
    s = PLATFORMS[platform]
    problems: list[str] = []
    full = post.full_text
    if len(full) > s.max_chars:
        problems.append(f"{platform}: {len(full)} characters exceeds the {s.max_chars} limit")
    if s.max_words and post.word_count > s.max_words:
        problems.append(f"{platform}: {post.word_count} words exceeds the {s.max_words} word cap")
    if rules.forbid_em_dashes and (EM_DASH in post.body or "–" in post.body):
        problems.append(f"{platform}: contains an em/en dash")
    if rules.forbid_financial_figures and _FINANCIAL.search(post.body):
        problems.append(f"{platform}: contains a financial figure")
    if not rules.allow_hashtags and post.hashtags:
        problems.append(f"{platform}: hashtags are not allowed")
    if rules.allow_hashtags and len(post.hashtags) > s.hashtags[1]:
        problems.append(f"{platform}: {len(post.hashtags)} hashtags exceeds the max of {s.hashtags[1]}")
    lowered = post.body.lower()
    for phrase in rules.banned_phrases:
        if re.search(r"\b" + re.escape(phrase) + r"\b", lowered):
            problems.append(f"{platform}: uses banned phrase '{phrase}'")
    return problems


def _truncate_to_sentence(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for mark in (". ", "! ", "? ", "\n"):
        idx = cut.rfind(mark)
        if idx > limit * 0.5:
            return cut[: idx + 1].rstrip()
    return cut.rsplit(" ", 1)[0].rstrip() + "…"


def _auto_fix(platform: str, post: PlatformPost, rules: CaptionRules) -> list[str]:
    """Mechanical fixes for anything the model still got wrong. Returns notes."""
    s = PLATFORMS[platform]
    notes: list[str] = []
    if rules.forbid_em_dashes and (EM_DASH in post.body or "–" in post.body):
        post.body = re.sub(r"\s*[—–]\s*", ", ", post.body)
        notes.append(f"{platform}: replaced dashes with commas")
    if not rules.allow_hashtags and post.hashtags:
        post.hashtags = []
        notes.append(f"{platform}: dropped hashtags")
    if rules.allow_hashtags and len(post.hashtags) > s.hashtags[1]:
        post.hashtags = post.hashtags[: s.hashtags[1]]
        notes.append(f"{platform}: trimmed hashtags to {s.hashtags[1]}")
    if len(post.full_text) > s.max_chars:
        while post.hashtags and len(post.full_text) > s.max_chars:
            post.hashtags.pop()
        if len(post.full_text) > s.max_chars:
            room = s.max_chars - (len(post.full_text) - len(post.body.strip()))
            post.body = _truncate_to_sentence(post.body.strip(), room)
        notes.append(f"{platform}: truncated to fit {s.max_chars} characters")
    if s.max_words and post.word_count > s.max_words:
        words = post.body.split()
        post.body = _truncate_to_sentence(" ".join(words[: s.max_words + 5]), len(" ".join(words[: s.max_words])))
        notes.append(f"{platform}: trimmed to {s.max_words} words")
    return notes


def _parse_posts(data: dict[str, Any], platforms: list[str]) -> dict[str, PlatformPost]:
    posts: dict[str, PlatformPost] = {}
    for p in platforms:
        raw = data.get(p)
        if not isinstance(raw, dict) or not str(raw.get("body", "")).strip():
            raise CaptionGenerationError(f"Model output is missing a usable '{p}' post", retryable=True)
        tags = [str(t).strip() for t in raw.get("hashtags", []) if str(t).strip()]
        tags = [t if t.startswith("#") else "#" + t.lstrip("#") for t in tags]
        tags = [re.sub(r"\s+", "", t) for t in tags]
        posts[p] = PlatformPost(
            platform=p,
            body=str(raw["body"]).strip(),
            hashtags=tags,
            alternate_hooks=[str(h).strip() for h in raw.get("alternate_hooks", []) if str(h).strip()][:4],
        )
    return posts


class CaptionGenerator:
    def __init__(
        self,
        provider: CaptionProvider,
        rules: CaptionRules,
        platforms: list[str],
        *,
        max_retries: int = 3,
        corrective_rounds: int = 1,
        sleep=None,
    ) -> None:
        unknown = [p for p in platforms if p not in PLATFORMS]
        if unknown:
            raise ValueError(f"Unknown platforms: {unknown}")
        self.provider = provider
        self.rules = rules
        self.platforms = list(platforms)
        self.max_retries = max_retries
        self.corrective_rounds = corrective_rounds
        self._sleep = sleep
        self.system_prompt = build_system_prompt(rules, self.platforms)
        self.schema = build_schema(self.platforms)

    def _request(self, article_title: str, chunk: Chunk, match: ImageMatch, feedback: str | None) -> JSONRequest:
        user = build_user_prompt(article_title, chunk, match, self.platforms)
        if feedback:
            user += "\n\nYOUR PREVIOUS ATTEMPT BROKE THESE RULES, FIX THEM:\n" + feedback
        tags = match.image.tags
        payload = {
            "chunk_text": chunk.text,
            "keywords": list(chunk.keywords),
            "platforms": self.platforms,
            "char_limits": {p: PLATFORMS[p].max_chars for p in self.platforms},
            "allow_hashtags": self.rules.allow_hashtags,
            "image_alt_text": tags.alt_text if tags else "",
        }
        return JSONRequest(system=self.system_prompt, user=user, schema=self.schema, payload=payload)

    def generate(self, article_title: str, chunk: Chunk, match: ImageMatch) -> CaptionResult:
        feedback: str | None = None
        warnings: list[str] = []
        posts: dict[str, PlatformPost] = {}
        result = None
        for round_no in range(self.corrective_rounds + 1):
            req = self._request(article_title, chunk, match, feedback)
            kwargs = {"attempts": self.max_retries, "label": f"caption chunk {chunk.index}"}
            if self._sleep is not None:
                kwargs["sleep"] = self._sleep
            result = with_retries(lambda: self.provider.complete_json(req), **kwargs)
            posts = _parse_posts(result.data, self.platforms)
            problems = [v for p in self.platforms for v in _violations(p, posts[p], self.rules)]
            if not problems:
                break
            log.info("Caption round %d for chunk %d had violations: %s", round_no + 1, chunk.index, problems)
            feedback = "\n".join(f"- {v}" for v in problems)
            if round_no == self.corrective_rounds:
                for p in self.platforms:
                    warnings.extend(_auto_fix(p, posts[p], self.rules))
                leftover = [v for p in self.platforms for v in _violations(p, posts[p], self.rules)]
                warnings.extend(f"unresolved: {v}" for v in leftover)
        assert result is not None
        return CaptionResult(
            posts=posts,
            image_alt_text=str(result.data.get("image_alt_text", "")).strip(),
            theme=str(result.data.get("theme", "")).strip(),
            provider=result.provider,
            model=result.model,
            warnings=warnings,
            usage=result.usage,
        )
