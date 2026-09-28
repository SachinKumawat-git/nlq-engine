"""
In-memory async job manager.

Ingestion and NL queries can both take several seconds (CSV scan, LLM
round-trip), so the API never blocks a caller on either: it enqueues
work on a bounded thread pool, hands back a job_id immediately, and the
caller polls (or streams via SSE) for status/result.

This is intentionally the simplest thing that satisfies the "submit a
job, get an id, poll or stream, retrieve when ready" requirement for a
single-process take-home. See docs/SYSTEM_DESIGN.md for how this would
change under real concurrent load (Redis + RQ/Celery, persistent job
store, multiple worker processes) -- an in-memory dict does not survive
a process restart and does not fan out across workers, which is exactly
the tradeoff called out there.
"""
from __future__ import annotations
import time
import uuid
import threading
import queue as _queue
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from app.config import settings

_executor = ThreadPoolExecutor(max_workers=settings.max_job_workers)
_jobs: dict[str, "Job"] = {}
_lock = threading.Lock()


@dataclass
class Job:
    job_id: str
    type: str
    status: str = "queued"  # queued -> running -> done | failed
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    # each job gets its own subscriber queues for SSE streaming
    _subscribers: list[_queue.Queue] = field(default_factory=list, repr=False)

    def to_public(self) -> dict:
        return {
            "job_id": self.job_id,
            "type": self.type,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "result": self.result,
            "error": self.error,
        }


def _set_status(job: Job, status: str, **kwargs):
    with _lock:
        job.status = status
        job.updated_at = time.time()
        for k, v in kwargs.items():
            setattr(job, k, v)
        for sub in job._subscribers:
            sub.put(job.to_public())


def submit_job(job_type: str, fn: Callable[[], dict]) -> Job:
    job = Job(job_id=uuid.uuid4().hex[:12], type=job_type)
    with _lock:
        _jobs[job.job_id] = job

    def _run():
        _set_status(job, "running")
        try:
            result = fn()
            _set_status(job, "done", result=result)
        except Exception as e:
            _set_status(job, "failed", error=str(e))

    _executor.submit(_run)
    return job


def get_job(job_id: str) -> Optional[Job]:
    with _lock:
        return _jobs.get(job_id)


def subscribe(job_id: str) -> Optional[_queue.Queue]:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return None
        q: _queue.Queue = _queue.Queue()
        q.put(job.to_public())
        job._subscribers.append(q)
        return q
