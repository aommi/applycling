"""Pluggable storage backends for the job tracker.

A `TrackerStore` is the abstraction the CLI talks to. It hides whether jobs
live in Notion, SQLite, or somewhere else. Adding a new backend means writing
one class that implements this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

STATUSES: tuple[str, ...] = (
    "tailored",
    "applied",
    "interview",
    "offer",
    "rejected",
)

# Fields the CLI is allowed to mutate after a job is first saved. The
# date_updated field is set automatically by the store on every update.
ALLOWED_UPDATE_FIELDS: frozenset[str] = frozenset(
    {
        "status",
        "source_url",
        "application_url",
        "fit_summary",
        "package_folder",
    }
)


class TrackerError(Exception):
    """Raised when the tracker store cannot satisfy a request."""


@dataclass
class Job:
    """A single tracked job application."""

    id: str
    title: str
    company: str
    date_added: str
    date_updated: str
    status: str = "tailored"
    source_url: Optional[str] = None
    application_url: Optional[str] = None
    fit_summary: Optional[str] = None
    package_folder: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "company": self.company,
            "date_added": self.date_added,
            "date_updated": self.date_updated,
            "status": self.status,
            "source_url": self.source_url,
            "application_url": self.application_url,
            "fit_summary": self.fit_summary,
            "package_folder": self.package_folder,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Job":
        return cls(
            id=data["id"],
            title=data["title"],
            company=data["company"],
            date_added=data["date_added"],
            date_updated=data["date_updated"],
            status=data.get("status") or "tailored",
            source_url=data.get("source_url"),
            application_url=data.get("application_url"),
            fit_summary=data.get("fit_summary"),
            package_folder=data.get("package_folder"),
        )


class TrackerStore(ABC):
    """Abstract storage backend for the job tracker."""

    @abstractmethod
    def save_job(self, job: Job) -> Job:
        """Persist a new job. If `job.id` is empty the store assigns one.
        Sets `date_added` and `date_updated` to now if not already set.
        Returns the saved Job (with id and dates populated).
        """

    @abstractmethod
    def load_jobs(self) -> list[Job]:
        """Return all jobs ordered by date_added descending."""

    @abstractmethod
    def load_job(self, job_id: str) -> Job:
        """Return one job by id. Raise `TrackerError` if not found."""

    @abstractmethod
    def update_job(self, job_id: str, **fields: Any) -> Job:
        """Update fields on an existing job and bump `date_updated`.
        Allowed fields: see `ALLOWED_UPDATE_FIELDS`.
        Returns the updated Job. Raises `TrackerError` if id not found or if
        any field is not in `ALLOWED_UPDATE_FIELDS`.
        """


def get_store() -> TrackerStore:
    """Return the configured tracker store.

    Resolution order:
    1. NotionStore if `applycling notion connect` has been run and the local
       Notion config is present.
    2. SQLiteStore otherwise (zero-config local default).
    """
    # Lazy imports to avoid pulling in optional deps until they're needed.
    from . import sqlite_store

    try:
        from . import notion_store

        if notion_store.is_connected():
            store = notion_store.NotionStore()
            # Verify the database is reachable before committing to it.
            store.load_jobs()
            return store
    except ImportError:
        # NotionStore module exists but its optional dependency isn't
        # installed; fall back silently.
        pass
    except (TrackerError, Exception):
        # Notion database is unreachable (deleted, unshared, etc.).
        # Fall back to SQLite so the user isn't blocked.
        import sys
        print(
            "\033[33mWarning: Notion database is unreachable — "
            "falling back to local SQLite tracker.\033[0m",
            file=sys.stderr,
        )

    return sqlite_store.SQLiteStore()
