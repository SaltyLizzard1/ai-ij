"""Per-platform formatting rules used in prompts and in output validation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlatformSpec:
    key: str
    display_name: str
    max_chars: int
    ideal_chars: tuple[int, int]
    max_words: int | None
    hashtags: tuple[int, int]  # (min, max) when hashtags are allowed
    hook_chars: int  # characters visible before the "see more" fold
    post_hour: int  # suggested local posting hour
    style: str  # guidance injected into the LLM prompt


PLATFORMS: dict[str, PlatformSpec] = {
    "linkedin": PlatformSpec(
        key="linkedin",
        display_name="LinkedIn",
        max_chars=3000,
        ideal_chars=(600, 1300),
        max_words=None,
        hashtags=(3, 5),
        hook_chars=210,
        post_hour=8,
        style=(
            "Professional but personal. First line is the hook and must stand alone. "
            "Short paragraphs separated by blank lines, one idea per paragraph. "
            "Lead with the story or the lesson, then the practical takeaway. "
            "End with one question or a soft invitation to comment. No emoji spam (0-2 total)."
        ),
    ),
    "x": PlatformSpec(
        key="x",
        display_name="X (Twitter)",
        max_chars=280,
        ideal_chars=(120, 260),
        max_words=None,
        hashtags=(0, 2),
        hook_chars=280,
        post_hour=12,
        style=(
            "One punchy idea. Plain sentences, no thread. The hook IS the post. "
            "Numbers and specifics beat adjectives. At most one emoji. Must fit in 280 characters "
            "including hashtags."
        ),
    ),
    "instagram": PlatformSpec(
        key="instagram",
        display_name="Instagram",
        max_chars=2200,
        ideal_chars=(300, 900),
        max_words=None,
        hashtags=(5, 12),
        hook_chars=125,
        post_hour=18,
        style=(
            "Conversational and visual. The first line must work before the '... more' cut at ~125 characters. "
            "Reference what is in the photo. Short lines, blank lines between thoughts, "
            "a light CTA (save, share, comment). Hashtags go on their own lines at the end."
        ),
    ),
    "facebook": PlatformSpec(
        key="facebook",
        display_name="Facebook",
        max_chars=6000,
        ideal_chars=(350, 800),
        max_words=150,
        hashtags=(0, 2),
        hook_chars=125,
        post_hour=19,
        style=(
            "Written as a story told to a friend: setup, a turn, a payoff. 60-120 words, hard cap 150. "
            "The hook is the first line and must survive the cut at ~125 characters. "
            "Full sentences with connective tissue; a standalone fragment only as a punchline (max two). "
            "One concrete closing line (an image, a number, a 'more on that later'), not a moral."
        ),
    ),
}


def spec(platform: str) -> PlatformSpec:
    try:
        return PLATFORMS[platform]
    except KeyError as exc:
        raise ValueError(f"Unknown platform {platform!r}; known: {sorted(PLATFORMS)}") from exc
