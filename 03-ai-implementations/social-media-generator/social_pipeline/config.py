"""Runtime settings, loaded from environment variables (and an optional .env).

Nothing here reads files other than ``.env``; secrets stay in the environment.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_MODELS = {
    "anthropic": "claude-opus-5",
    "openai": "gpt-4o",
    "mock": "mock-1",
}


def load_dotenv(path: str | os.PathLike[str] = ".env", *, override: bool = False) -> None:
    """Minimal .env loader (KEY=VALUE, quotes optional, # comments)."""
    p = Path(path)
    if not p.is_file():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if override or key not in os.environ:
            os.environ[key] = value


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc


@dataclass
class Settings:
    # LLM
    llm_provider: str = "anthropic"  # anthropic | openai | mock
    llm_model: str | None = None  # None -> provider default
    llm_effort: str | None = None  # Anthropic only: low|medium|high|xhigh|max
    llm_max_retries: int = 3
    llm_timeout_seconds: float = 120.0
    anthropic_api_key: str | None = None
    anthropic_server_fallbacks: bool = True  # server-side refusal fallbacks
    openai_api_key: str | None = None

    # Storage / assets
    db_path: str = "social_pipeline.db"
    image_library: str = "./images"
    output_dir: str = "./output"

    # Content
    brand_voice: str = (
        "Warm, direct and practical. Speak to one reader. No corporate jargon, "
        "no clickbait, no fake urgency."
    )
    brand_name: str | None = None
    chunk_min_chars: int = 150
    chunk_max_chars: int = 700
    max_posts_per_article: int = 6
    hook_chunks: int = 2

    # Matching / scheduling
    strict_month: bool = False  # True -> only images from the target month
    timezone: str = "UTC"
    weekdays_only: bool = True

    platforms: tuple[str, ...] = field(default=("linkedin", "x", "instagram"))

    @classmethod
    def from_env(cls, dotenv_path: str | None = ".env") -> "Settings":
        if dotenv_path:
            load_dotenv(dotenv_path)
        env = os.environ
        platforms = tuple(
            p.strip().lower()
            for p in env.get("PLATFORMS", "linkedin,x,instagram").split(",")
            if p.strip()
        )
        settings = cls(
            llm_provider=env.get("LLM_PROVIDER", "anthropic").strip().lower(),
            llm_model=env.get("LLM_MODEL") or None,
            llm_effort=env.get("LLM_EFFORT") or None,
            llm_max_retries=_env_int("LLM_MAX_RETRIES", 3),
            llm_timeout_seconds=float(env.get("LLM_TIMEOUT_SECONDS", "120")),
            anthropic_api_key=env.get("ANTHROPIC_API_KEY") or None,
            anthropic_server_fallbacks=_env_bool("ANTHROPIC_SERVER_FALLBACKS", True),
            openai_api_key=env.get("OPENAI_API_KEY") or None,
            db_path=env.get("DB_PATH", "social_pipeline.db"),
            image_library=env.get("IMAGE_LIBRARY", "./images"),
            output_dir=env.get("OUTPUT_DIR", "./output"),
            brand_voice=env.get("BRAND_VOICE", cls.brand_voice),
            brand_name=env.get("BRAND_NAME") or None,
            chunk_min_chars=_env_int("CHUNK_MIN_CHARS", 150),
            chunk_max_chars=_env_int("CHUNK_MAX_CHARS", 700),
            max_posts_per_article=_env_int("MAX_POSTS_PER_ARTICLE", 6),
            hook_chunks=_env_int("HOOK_CHUNKS", 2),
            strict_month=_env_bool("STRICT_MONTH", False),
            timezone=env.get("TIMEZONE", "UTC"),
            weekdays_only=_env_bool("WEEKDAYS_ONLY", True),
            platforms=platforms,
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.llm_provider not in DEFAULT_MODELS:
            raise ValueError(
                f"LLM_PROVIDER must be one of {sorted(DEFAULT_MODELS)}, got {self.llm_provider!r}"
            )
        if self.chunk_min_chars >= self.chunk_max_chars:
            raise ValueError("CHUNK_MIN_CHARS must be smaller than CHUNK_MAX_CHARS")
        if self.max_posts_per_article < 1:
            raise ValueError("MAX_POSTS_PER_ARTICLE must be >= 1")
        from .platforms import PLATFORMS  # local import to avoid a cycle

        unknown = [p for p in self.platforms if p not in PLATFORMS]
        if unknown:
            raise ValueError(f"Unknown platform(s) in PLATFORMS: {unknown}")

    @property
    def resolved_model(self) -> str:
        return self.llm_model or DEFAULT_MODELS[self.llm_provider]
