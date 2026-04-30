"""Pluggable storage backends for the job tracker.

A `TrackerStore` is the abstraction the CLI talks to. It hides whether jobs
live in Notion, SQLite, or somewhere else. Adding a new backend means writing
one class that implements this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

from applycling.statuses import STATUS_VALUES as STATUSES, migrate_old_status

# Fields the CLI is allowed to mutate after a job is first saved. The
# date_updated field is set automatically by the store on every update.
ALLOWED_UPDATE_FIELDS: frozenset[str] = frozenset(
    {
        "title",
        "company",
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
    status: str = "new"
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
        status = migrate_old_status(data.get("status") or "new")
        return cls(
            id=data["id"],
            title=data["title"],
            company=data["company"],
            date_added=data["date_added"],
            date_updated=data["date_updated"],
            status=status,
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

    def load_job_notes(self, job_id: str) -> str:
        """Return free-text notes attached to a job (e.g. Notion page body).
        Default: returns empty string. Override in backends that support notes.
        """
        return ""


def get_store() -> TrackerStore:
    """Return the configured tracker store.

    Resolution order:
    1. If APPLYCLING_DB_BACKEND=postgres, require DATABASE_URL, return
       PostgresStore. The Notion probe is skipped.
    2. If APPLYCLING_DB_BACKEND=sqlite, return SQLiteStore (existing behavior
       with Notion probe).
    3. If unset, fall back to legacy resolution (Notion probe → SQLite).
    """
    import os

    db_backend = os.environ.get("APPLYCLING_DB_BACKEND", "").strip().lower()

    # ── Postgres path (no Notion probe) ────────────────────────────────
    if db_backend == "postgres":
        from . import postgres_store

        return postgres_store.PostgresStore()

    # ── SQLite path (Notion probe still runs for backward compat) ──────
    # Lazy imports to avoid pulling in optional deps until they're needed.
    from . import sqlite_store

    if db_backend == "sqlite":
        # Explicit sqlite — skip the Notion probe entirely.
        return sqlite_store.SQLiteStore()

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


def _is_postgres() -> bool:
    """Return True if the configured backend is Postgres."""
    import os

    return os.environ.get("APPLYCLING_DB_BACKEND", "").strip().lower() == "postgres"


def check_active_run() -> bool:
    """UX pre-check: return True if a pipeline run is currently active.

    This is a simple SELECT — it CAN race with another request that starts
    a run between the check and the subsequent ``create_run()`` call.  The
    atomic ``create_run()`` INSERT is the authoritative guard.  This function
    only exists to give the UI a fast pre-check before creating a job or
    changing status, so 99 % of double-clicks get a friendly message rather
    than a database-level conflict.

    Always returns ``False`` when the backend is not Postgres.
    """
    if not _is_postgres():
        return False
    store = get_store()
    return store.get_active_run() is not None


def register_startup_sweep(app: Any) -> None:
    """Register startup and periodic stale-run sweep handlers on *app*.

    Attaches:
    - A one-time startup event that marks ALL ``running`` rows as ``failed``
      (unconditional — crash recovery).
    - A periodic background task (every 5 minutes) that sweeps rows whose
      ``heartbeat_at`` is older than ``APPLYCLING_STALE_RUN_TIMEOUT_MINUTES``.

    Does nothing when the backend is not Postgres.

    .. warning::
       Single-instance assumption — ``sweep_all_running()`` marks EVERY
       running row as failed on startup.  Do not run multiple replicas of
       the applycling workbench against the same Postgres database.
    """
    if not _is_postgres():
        return

    import asyncio

    store = get_store()

    @app.on_event("startup")
    async def _startup() -> None:
        # Unconditional startup sweep — crash recovery.
        # Marks ALL running rows as failed because any background task is dead.
        try:
            swept = store.sweep_all_running()
            if swept:
                import sys
                print(
                    f"[startup] Swept {swept} running pipeline run(s) — crash recovery.",
                    file=sys.stderr,
                )
        except Exception as e:
            import sys
            print(
                f"[startup] Sweep failed: {e}",
                file=sys.stderr, flush=True,
            )

        # Periodic heartbeat-based stale-run sweep (every 5 minutes).
        async def _periodic_sweep() -> None:
            while True:
                try:
                    await asyncio.sleep(300)
                    store.sweep_stale_runs()
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    import sys
                    print(
                        f"[sweep] Periodic stale-run sweep failed: {e}",
                        file=sys.stderr, flush=True,
                    )

        task = asyncio.create_task(_periodic_sweep())
        app.state._periodic_sweep_task = task

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        task = getattr(app.state, "_periodic_sweep_task", None)
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
