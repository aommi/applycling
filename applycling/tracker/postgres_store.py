"""Postgres-backed implementation of TrackerStore.

Uses psycopg v3. Reads DATABASE_URL from env. All queries are scoped
to the local default user resolved on init via db_seed.get_local_user_id().
"""

from __future__ import annotations

import datetime as dt
import os
import uuid
from typing import Any

import psycopg
import psycopg.rows

from applycling.db_seed import get_local_user_id, seed_local_user

from . import ALLOWED_UPDATE_FIELDS, Job, TrackerError, TrackerStore
from applycling.statuses import migrate_old_status


class PostgresStore(TrackerStore):
    def __init__(self, database_url: str | None = None) -> None:
        self._database_url = database_url or os.environ.get("DATABASE_URL")
        if not self._database_url:
            raise TrackerError(
                "DATABASE_URL must be set when APPLYCLING_DB_BACKEND=postgres. "
                "Set it to your Postgres connection string, e.g. "
                "postgresql://applycling:password@localhost:5432/applycling"
            )
        self._user_uuid = get_local_user_id()
        self._user_id = str(self._user_uuid)
        # Ensure the local default user exists (idempotent — ON CONFLICT DO NOTHING).
        seed_local_user(self._database_url)

    def _conn(self) -> psycopg.Connection:
        return psycopg.connect(self._database_url, row_factory=psycopg.rows.dict_row)

    def _row_to_job(self, row: dict) -> Job:
        """Map a Postgres jobs row to a Job dataclass."""
        created_at = row["created_at"]
        updated_at = row["updated_at"]

        if isinstance(created_at, dt.datetime):
            date_added = created_at.isoformat(timespec="microseconds")
        else:
            date_added = str(created_at) if created_at else ""

        if isinstance(updated_at, dt.datetime):
            date_updated = updated_at.isoformat(timespec="microseconds")
        else:
            date_updated = str(updated_at) if updated_at else ""

        return Job(
            id=str(row["id"]),
            title=row["title"],
            company=row["company"],
            date_added=date_added,
            date_updated=date_updated,
            status=row["status"],
            source_url=row.get("source_url"),
            application_url=row.get("application_url"),
            fit_summary=row.get("fit_summary"),
            package_folder=row.get("package_folder"),
        )

    def save_job(self, job: Job) -> Job:
        now = dt.datetime.now(dt.timezone.utc)

        if not job.id:
            job.id = str(uuid.uuid4())

        # Persist caller-supplied timestamps when provided, falling back to now.
        # This matches the SQLite/Notion contract: if the caller sets dates,
        # they are honoured; otherwise they are assigned at save time.
        def _parse_iso_or_now(iso_str: str, fallback: dt.datetime) -> dt.datetime:
            if iso_str:
                try:
                    return dt.datetime.fromisoformat(iso_str)
                except (ValueError, TypeError):
                    pass
            return fallback

        created_dt = _parse_iso_or_now(job.date_added, now)
        updated_dt = _parse_iso_or_now(job.date_updated, now)

        job.date_added = created_dt.isoformat(timespec="microseconds")
        job.date_updated = updated_dt.isoformat(timespec="microseconds")

        # Map legacy statuses (inbox, tailored, etc.) to canonical states.
        status = migrate_old_status(job.status)

        try:
            with self._conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO jobs (
                            id, user_id, title, company, status,
                            source_url, application_url, fit_summary,
                            package_folder, created_at, updated_at
                        ) VALUES (
                            %s, %s, %s, %s, %s,
                            %s, %s, %s,
                            %s, %s, %s
                        )
                        """,
                        (
                            uuid.UUID(job.id),
                            self._user_uuid,
                            job.title,
                            job.company,
                            status,
                            job.source_url,
                            job.application_url,
                            job.fit_summary,
                            job.package_folder,
                            created_dt,
                            updated_dt,
                        ),
                    )
            return job
        except psycopg.errors.UniqueViolation as e:
            raise TrackerError(
                f"Could not save job '{job.id}': {e}"
            ) from e

    _COLUMNS = (
        "id, title, company, status, source_url, application_url, "
        "fit_summary, package_folder, created_at, updated_at"
    )

    def load_jobs(self) -> list[Job]:
        with self._conn() as conn:
            with conn.execute(
                f"""
                SELECT {self._COLUMNS}
                FROM jobs
                WHERE user_id = %s AND deleted_at IS NULL
                ORDER BY created_at DESC
                """,
                (self._user_uuid,),
            ) as cur:
                rows = cur.fetchall()
        return [self._row_to_job(row) for row in rows]

    def load_job(self, job_id: str) -> Job:
        try:
            job_uuid = uuid.UUID(job_id)
        except ValueError as e:
            raise TrackerError(
                f"No job found with id '{job_id}'."
            ) from e

        with self._conn() as conn:
            row = conn.execute(
                f"""
                SELECT {self._COLUMNS}
                FROM jobs
                WHERE id = %s AND user_id = %s AND deleted_at IS NULL
                """,
                (job_uuid, self._user_uuid),
            ).fetchone()

        if row is None:
            raise TrackerError(f"No job found with id '{job_id}'.")
        return self._row_to_job(row)

    def update_job(self, job_id: str, **fields: Any) -> Job:
        invalid = set(fields) - ALLOWED_UPDATE_FIELDS
        if invalid:
            raise TrackerError(
                f"Cannot update fields: {sorted(invalid)}. "
                f"Allowed: {sorted(ALLOWED_UPDATE_FIELDS)}"
            )
        if not fields:
            return self.load_job(job_id)

        try:
            job_uuid = uuid.UUID(job_id)
        except ValueError as e:
            raise TrackerError(
                f"No job found with id '{job_id}'."
            ) from e

        now = dt.datetime.now(dt.timezone.utc)

        set_parts = []
        params: list[Any] = []
        for k, v in fields.items():
            if k == "status":
                v = migrate_old_status(v)
            set_parts.append(f"{k} = %s")
            params.append(v)
        set_parts.append("updated_at = %s")
        params.append(now)

        params.extend([job_uuid, self._user_uuid])

        with self._conn() as conn:
            cur = conn.execute(
                f"""
                UPDATE jobs
                SET {', '.join(set_parts)}
                WHERE id = %s AND user_id = %s AND deleted_at IS NULL
                """,
                params,
            )
            if cur.rowcount == 0:
                raise TrackerError(f"No job found with id '{job_id}'.")

        return self.load_job(job_id)
