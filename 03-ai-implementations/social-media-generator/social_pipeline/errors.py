"""Exception hierarchy for the pipeline.

Every stage raises a subclass of ``PipelineError`` so callers can catch one
type at the boundary. ``retryable`` tells the retry helper whether a second
attempt has any chance of succeeding (rate limits, timeouts) or not
(bad input, auth failure, refusal).
"""


class PipelineError(Exception):
    """Base class for all pipeline failures."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class ArticleLoadError(PipelineError):
    """The article could not be fetched or read."""


class ChunkingError(PipelineError):
    """The article parsed but produced no usable content."""


class ImageIndexError(PipelineError):
    """The image library could not be scanned or its metadata is invalid."""


class NoImageMatchError(PipelineError):
    """No image in the library is eligible for a chunk (empty library)."""


class CaptionGenerationError(PipelineError):
    """The LLM provider failed or returned an unusable response."""


class StorageError(PipelineError):
    """SQLite read/write failure."""
