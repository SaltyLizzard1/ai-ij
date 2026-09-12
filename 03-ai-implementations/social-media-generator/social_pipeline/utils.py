"""Small shared helpers."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TypeVar

from .errors import PipelineError

T = TypeVar("T")
log = logging.getLogger(__name__)


def with_retries(
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 30.0,
    sleep: Callable[[float], None] = time.sleep,
    label: str = "operation",
) -> T:
    """Call ``fn`` until it succeeds, retrying only on ``retryable`` PipelineErrors."""
    attempt = 0
    while True:
        attempt += 1
        try:
            return fn()
        except PipelineError as exc:
            if not exc.retryable or attempt >= attempts:
                raise
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            log.warning("%s failed (attempt %d/%d): %s; retrying in %.0fs", label, attempt, attempts, exc, delay)
            sleep(delay)
