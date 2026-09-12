"""Tiny in-process job runner for long operations (scan, score, tag, run).

One job at a time: the pipeline talks to a single SQLite file and a single
API key, so serialising is the safe default. Log lines emitted while the job
runs are captured so the UI can show progress.
"""

from __future__ import annotations

import logging
import threading
import traceback
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Job:
    id: str
    kind: str
    status: str = "queued"  # queued | running | succeeded | failed
    started_at: str | None = None
    finished_at: str | None = None
    result: Any = None
    error: str | None = None
    log: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "kind": self.kind, "status": self.status, "started_at": self.started_at,
            "finished_at": self.finished_at, "result": self.result, "error": self.error, "log": self.log[-200:],
        }


class _JobLogHandler(logging.Handler):
    def __init__(self, job: Job) -> None:
        super().__init__(level=logging.INFO)
        self.job = job
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith("social_pipeline"):
            self.job.log.append(self.format(record))


class JobRunner:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._current: Job | None = None

    def submit(self, kind: str, fn: Callable[[Job], Any]) -> Job:
        with self._lock:
            if self._current is not None and self._current.status in ("queued", "running"):
                raise RuntimeError(f"A {self._current.kind} job is already running ({self._current.id})")
            job = Job(id=uuid.uuid4().hex[:12], kind=kind)
            self._jobs[job.id] = job
            self._current = job

        def _run() -> None:
            handler = _JobLogHandler(job)
            root = logging.getLogger("social_pipeline")
            root.addHandler(handler)
            job.status = "running"
            job.started_at = datetime.now(timezone.utc).isoformat()
            try:
                job.result = fn(job)
                job.status = "succeeded"
            except Exception as exc:  # noqa: BLE001 - surface anything to the UI
                job.status = "failed"
                job.error = f"{type(exc).__name__}: {exc}"
                job.log.append(traceback.format_exc().strip().splitlines()[-1])
            finally:
                job.finished_at = datetime.now(timezone.utc).isoformat()
                root.removeHandler(handler)

        threading.Thread(target=_run, name=f"job-{kind}-{job.id}", daemon=True).start()
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def current(self) -> Job | None:
        return self._current

    def recent(self, limit: int = 20) -> list[Job]:
        return list(self._jobs.values())[-limit:][::-1]
