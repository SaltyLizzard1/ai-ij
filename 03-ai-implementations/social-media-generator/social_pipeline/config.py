"""Runtime settings, loaded from environment variables (and an optional .env).

Nothing here reads files other than ``.env`` and the brand-voice file; secrets
stay in the environment.
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

DEFAULT_BANNED_PHRASES: tuple[str, ...] = (
    "game-changer", "game changer", "unlock", "level up", "secret", "hack",
    "transform your life", "this is your reminder", "keep showing up",
    "setbacks are part of the journey", "wanderlust", "living my best life", "blessed",
)

DEFAULT_BRAND_VOICE = (
    "Warm, direct and practical. Speak to one reader in full sentences. "
    "Real numbers over adjectives. No corporate jargon, no clickbait, no fake "
    "urgency, no hype words (game-changer, unlock, level up, secret, hack)."
)


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


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {raw!r}") from exc


@dataclass
class Settings:
    # ---- LLM (captions + vision tagging) ----
    llm_provider: str = "anthropic"  # anthropic | openai | mock
    llm_model: str | None = None  # None -> provider default
    llm_effort: str | None = None  # Anthropic only: low|medium|high|xhigh|max
    llm_max_retries: int = 3
    llm_timeout_seconds: float = 180.0
    anthropic_api_key: str | None = None
    anthropic_server_fallbacks: bool = True  # server-side refusal fallbacks
    openai_api_key: str | None = None

    # ---- Storage / assets ----
    db_path: str = "social_pipeline.db"
    image_root: str = "./images"  # e.g. X:\  (camera roll with YYYY-MM folders)
    records_dir: str | None = None  # photo-organizer\records (blur2.csv lives here)
    skip_folders: tuple[str, ...] = ("blurred", "$RECYCLE.BIN", "System Volume Information")
    output_dir: str = "./output"

    # ---- Image quality pre-filter (uses your existing blur scores) ----
    max_blur: float = 0.42  # same cut-off your organiser uses; higher = blurrier
    min_contrast: float = 0.0  # 0 disables
    require_quality_record: bool = False  # True -> ignore photos with no blur2.csv row

    # ---- Vision tagging ----
    tag_max_per_run: int = 60  # cap on new images tagged during one `run`
    tag_image_max_edge: int = 1024  # downscale before sending to the API
    tag_candidates_per_chunk: int = 40  # how many quality-ranked photos to consider

    # ---- Content ----
    brand_voice: str = DEFAULT_BRAND_VOICE
    brand_voice_file: str | None = None  # markdown file appended to the system prompt
    brand_name: str | None = None
    chunk_min_chars: int = 150
    chunk_max_chars: int = 700
    max_posts_per_article: int = 6
    hook_chunks: int = 2
    forbid_em_dashes: bool = True
    forbid_financial_figures: bool = False
    allow_hashtags: bool = True
    banned_phrases: tuple[str, ...] = field(default_factory=lambda: DEFAULT_BANNED_PHRASES)

    # ---- Matching / scheduling ----
    strict_month: bool = False  # True -> only images from the target month
    timezone: str = "UTC"
    weekdays_only: bool = True
    seasonal_scheduling: bool = False

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
        skip = tuple(
            s.strip()
            for s in env.get("SKIP_FOLDERS", "blurred,$RECYCLE.BIN,System Volume Information").split(",")
            if s.strip()
        )
        settings = cls(
            llm_provider=env.get("LLM_PROVIDER", "anthropic").strip().lower(),
            llm_model=env.get("LLM_MODEL") or None,
            llm_effort=env.get("LLM_EFFORT") or None,
            llm_max_retries=_env_int("LLM_MAX_RETRIES", 3),
            llm_timeout_seconds=_env_float("LLM_TIMEOUT_SECONDS", 180.0),
            anthropic_api_key=env.get("ANTHROPIC_API_KEY") or None,
            anthropic_server_fallbacks=_env_bool("ANTHROPIC_SERVER_FALLBACKS", True),
            openai_api_key=env.get("OPENAI_API_KEY") or None,
            db_path=env.get("DB_PATH", "social_pipeline.db"),
            image_root=env.get("IMAGE_ROOT", "./images"),
            records_dir=env.get("RECORDS_DIR") or None,
            skip_folders=skip,
            output_dir=env.get("OUTPUT_DIR", "./output"),
            max_blur=_env_float("MAX_BLUR", 0.42),
            min_contrast=_env_float("MIN_CONTRAST", 0.0),
            require_quality_record=_env_bool("REQUIRE_QUALITY_RECORD", False),
            tag_max_per_run=_env_int("TAG_MAX_PER_RUN", 60),
            tag_image_max_edge=_env_int("TAG_IMAGE_MAX_EDGE", 1024),
            tag_candidates_per_chunk=_env_int("TAG_CANDIDATES_PER_CHUNK", 40),
            brand_voice=env.get("BRAND_VOICE", DEFAULT_BRAND_VOICE),
            brand_voice_file=env.get("BRAND_VOICE_FILE") or None,
            brand_name=env.get("BRAND_NAME") or None,
            chunk_min_chars=_env_int("CHUNK_MIN_CHARS", 150),
            chunk_max_chars=_env_int("CHUNK_MAX_CHARS", 700),
            max_posts_per_article=_env_int("MAX_POSTS_PER_ARTICLE", 6),
            hook_chunks=_env_int("HOOK_CHUNKS", 2),
            forbid_em_dashes=_env_bool("FORBID_EM_DASHES", True),
            forbid_financial_figures=_env_bool("FORBID_FINANCIAL_FIGURES", False),
            allow_hashtags=_env_bool("ALLOW_HASHTAGS", True),
            banned_phrases=tuple(
                b.strip().lower() for b in env.get("BANNED_PHRASES", "").split("|") if b.strip()
            ) or DEFAULT_BANNED_PHRASES,
            strict_month=_env_bool("STRICT_MONTH", False),
            timezone=env.get("TIMEZONE", "UTC"),
            weekdays_only=_env_bool("WEEKDAYS_ONLY", True),
            seasonal_scheduling=_env_bool("SEASONAL_SCHEDULING", False),
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
        if not 0 < self.max_blur <= 1:
            raise ValueError("MAX_BLUR must be between 0 and 1")
        from .platforms import PLATFORMS  # local import to avoid a cycle

        unknown = [p for p in self.platforms if p not in PLATFORMS]
        if unknown:
            raise ValueError(f"Unknown platform(s) in PLATFORMS: {unknown}")

    @property
    def resolved_model(self) -> str:
        return self.llm_model or DEFAULT_MODELS[self.llm_provider]

    def brand_voice_text(self) -> str:
        """Brand voice: inline setting plus the optional markdown file."""
        parts = [self.brand_voice.strip()]
        if self.brand_voice_file:
            p = Path(self.brand_voice_file)
            if not p.is_file():
                raise FileNotFoundError(f"BRAND_VOICE_FILE not found: {p}")
            parts.append(p.read_text(encoding="utf-8").strip())
        return "\n\n".join(x for x in parts if x)
