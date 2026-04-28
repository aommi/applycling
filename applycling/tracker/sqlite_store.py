"""SQLite-backed implementation of TrackerStore.

Single file at `data/tracker.db`. Zero config, ships with Python's stdlib.
This is the default store when Notion has not been connected.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path
from typing import Any, Optional

from . import ALLOWED_UPDATE_FIELDS, Job, TrackerError, TrackerStore

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB_PATH = ROOT / "data" / "tracker.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    date_added TEXT NOT NULL,
    date_updated TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',
    source_url TEXT,
    application_url TEXT,
    fit_summary TEXT,
    package_folder TEXT
);
CREATE INDEX IF NOT EXISTS jobs_status_idx ON jobs(status);
CREATE INDEX IF NOT EXISTS jobs_date_added_idx ON jobs(date_added);
"""


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


class SQLiteStore(TrackerStore):
    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    def _next_id(self, conn: sqlite3.Connection) -> str:
        # Find the highest existing job_NNN id and increment.
        rows = conn.execute(
            "SELECT id FROM jobs WHERE id LIKE 'job_%'"
        ).fetchall()
        max_n = 0
        for row in rows:
            try:
                n = int(row["id"].split("_", 1)[1])
            except (IndexError, ValueError):
                continue
            if n > max_n:
                max_n = n
        return f"job_{max_n + 1:03d}"

    def save_job(self, job: Job) -> Job:
        with self._conn() as conn:
            if not job.id:
                job.id = self._next_id(conn)
            now = _now()
            if not job.date_added:
                job.date_added = now
            if not job.date_updated:
                job.date_updated = now
            try:
                conn.execute(
                    """INSERT INTO jobs
                    (id, title, company, date_added, date_updated, status,
                     source_url, application_url, fit_summary, package_folder)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        job.id,
                        job.title,
                        job.company,
                        job.date_added,
                        job.date_updated,
                        job.status,
                        job.source_url,
                        job.application_url,
                        job.fit_summary,
                        job.package_folder,
                    ),
                )
            except sqlite3.IntegrityError as e:
                raise TrackerError(
                    f"Could not save job '{job.id}': {e}"
                ) from e
        return job

    def load_jobs(self) -> list[Job]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY date_added DESC"
            ).fetchall()
        return [Job.from_dict(dict(row)) for row in rows]

    def load_job(self, job_id: str) -> Job:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
        if row is None:
            raise TrackerError(f"No job found with id '{job_id}'.")
        return Job.from_dict(dict(row))

    def update_job(self, job_id: str, **fields: Any) -> Job:
        invalid = set(fields) - ALLOWED_UPDATE_FIELDS
        if invalid:
            raise TrackerError(
                f"Cannot update fields: {sorted(invalid)}. "
                f"Allowed: {sorted(ALLOWED_UPDATE_FIELDS)}"
            )
        if not fields:
            return self.load_job(job_id)
        fields["date_updated"] = _now()
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values: list[Any] = [*fields.values(), job_id]
        with self._conn() as conn:
            cur = conn.execute(
                f"UPDATE jobs SET {set_clause} WHERE id = ?", values
            )
            if cur.rowcount == 0:
                raise TrackerError(f"No job found with id '{job_id}'.")
        return self.load_job(job_id)
