"""Automated social media generator pipeline (work in progress).

Article (HTML/Markdown) -> chunks -> keyword/mood extraction -> image match
(delegated to the user's existing search scripts) -> LLM captions
(LinkedIn / X / Instagram) -> scheduled JSON packages.
"""

from .models import Article, Chunk, ImageAsset, ImageMatch, PlatformPost, PostPackage

__all__ = [
    "Article",
    "Chunk",
    "ImageAsset",
    "ImageMatch",
    "PlatformPost",
    "PostPackage",
]

__version__ = "0.1.0"
