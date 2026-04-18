"""Job queue abstraction for applycling background processing.

A QueueStore is the abstraction for managing a queue of jobs to be processed
(e.g., by a background worker or OpenClaw orchestrator). It mirrors the style
of TrackerStore with a simple, pluggable interface.

Implementations:
  - MemoryQueue: in-memory queue (for v1, fast for single-process testing)
  - SQLiteQueue: persistent queue (for robustness, can be added post-sprint)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional
import uuid
import datetime as dt


def _utcnow_iso() -> str:
    """UTC timestamp in 'YYYY-MM-DDTHH:MM:SS...Z' form via non-deprecated API."""
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None).isoformat() + "Z"


@dataclass
class QueuedJob:
    """A job waiting to be processed."""

    id: str
    url: str
    source: str  # e.g., "url_queue", "notion_inbox", "email"
    metadata: dict[str, Any]  # Extra context (user_id, priority, etc.)
    created_at: str
    claimed_by: Optional[str] = None
    claimed_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None


class QueueError(Exception):
    """Raised when the queue cannot satisfy a request."""


class QueueStore(ABC):
    """Abstract storage backend for the job queue."""

    @abstractmethod
    def enqueue(self, url: str, source: str = "url_queue", metadata: Optional[dict[str, Any]] = None) -> QueuedJob:
        """Add a job to the queue.

        Args:
            url: Job posting URL or text (job description).
            source: Source identifier (e.g., "url_queue", "notion_inbox", "email").
            metadata: Optional extra context (user_id, priority, etc.).

        Returns:
            The QueuedJob with id and created_at populated.
        """

    @abstractmethod
    def dequeue(self, claimer_id: str = "default") -> Optional[QueuedJob]:
        """Claim and return the next unclaimed job.

        If a job is already claimed by another worker, skip it. This ensures
        at-most-once semantics (a job is only processed by one worker).

        Args:
            claimer_id: Worker identifier claiming the job (e.g., "worker_1").

        Returns:
            A QueuedJob if one is available, or None if the queue is empty.
        """

    @abstractmethod
    def mark_completed(self, job_id: str) -> None:
        """Mark a job as successfully completed and remove it from the queue.

        Args:
            job_id: ID of the job to mark complete.

        Raises:
            QueueError: If job not found.
        """

    @abstractmethod
    def mark_failed(self, job_id: str, error: str) -> None:
        """Mark a job as failed and keep it in the queue for retry.

        Args:
            job_id: ID of the job that failed.
            error: Error message explaining the failure.

        Raises:
            QueueError: If job not found.
        """

    def list_pending(self) -> list[QueuedJob]:
        """Return all unclaimed jobs.

        Default implementation returns empty list. Override if backend supports it.
        """
        return []

    def list_failed(self) -> list[QueuedJob]:
        """Return all failed jobs awaiting retry.

        Default implementation returns empty list. Override if backend supports it.
        """
        return []


class MemoryQueue(QueueStore):
    """In-memory queue implementation for testing and single-process use.

    Not suitable for multi-process or distributed scenarios. Use SQLiteQueue
    for production robustness.
    """

    def __init__(self) -> None:
        self._queue: list[QueuedJob] = []
        self._completed: list[str] = []
        self._failed: dict[str, str] = {}

    def enqueue(self, url: str, source: str = "url_queue", metadata: Optional[dict[str, Any]] = None) -> QueuedJob:
        job = QueuedJob(
            id=f"job_{uuid.uuid4().hex[:12]}",
            url=url,
            source=source,
            metadata=metadata or {},
            created_at=_utcnow_iso(),
        )
        self._queue.append(job)
        return job

    def dequeue(self, claimer_id: str = "default") -> Optional[QueuedJob]:
        for job in self._queue:
            if job.claimed_by is None and job.id not in self._completed:
                job.claimed_by = claimer_id
                job.claimed_at = _utcnow_iso()
                return job
        return None

    def mark_completed(self, job_id: str) -> None:
        if job_id not in [j.id for j in self._queue]:
            raise QueueError(f"Job not found: {job_id}")
        self._completed.append(job_id)
        self._queue = [j for j in self._queue if j.id != job_id]

    def mark_failed(self, job_id: str, error: str) -> None:
        for job in self._queue:
            if job.id == job_id:
                job.error = error
                job.claimed_by = None  # Release the claim so it can be retried
                self._failed[job_id] = error
                return
        raise QueueError(f"Job not found: {job_id}")

    def list_pending(self) -> list[QueuedJob]:
        return [j for j in self._queue if j.claimed_by is None]

    def list_failed(self) -> list[QueuedJob]:
        return [j for j in self._queue if j.id in self._failed]
