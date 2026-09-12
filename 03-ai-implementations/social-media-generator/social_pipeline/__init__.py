"""Automated social media generator pipeline.

Article (HTML/Markdown) -> chunks -> keyword/theme extraction -> vision-tagged
photo match (month-aware, quality-filtered) -> LLM captions per platform ->
scheduled JSON packages.
"""

from .models import Article, Chunk, ImageAsset, ImageMatch, ImageTags, PlatformPost, PostPackage
from .pipeline import PipelineResult, RunOptions, SocialPipeline

__all__ = [
    "Article",
    "Chunk",
    "ImageAsset",
    "ImageMatch",
    "ImageTags",
    "PlatformPost",
    "PostPackage",
    "PipelineResult",
    "RunOptions",
    "SocialPipeline",
]

__version__ = "0.1.0"
