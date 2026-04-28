"""initial_workflow_schema

Revision ID: 64437a34178f
Revises:
Create Date: 2026-04-28 02:33:46.865155

Creates the core workflow schema: users, jobs, pipeline_runs, artifacts.
Includes CHECK constraints and performance indexes per DB_TECH_DESIGN.md §9.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "64437a34178f"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── users ─────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            telegram_id BIGINT UNIQUE NULL,
            email TEXT UNIQUE NULL,
            is_blocked BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            deleted_at TIMESTAMPTZ NULL
        );
    """)

    # ── jobs ──────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE jobs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id),
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'inbox',
            status_reason TEXT NULL,
            source_url TEXT NULL,
            application_url TEXT NULL,
            fit_summary TEXT NULL,
            package_folder TEXT NULL,
            notion_page_id TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            deleted_at TIMESTAMPTZ NULL,
            CONSTRAINT chk_jobs_status CHECK (
                status IN (
                    'inbox',
                    'running',
                    'generated',
                    'reviewing',
                    'applied',
                    'skipped',
                    'failed'
                )
            )
        );
    """)

    # ── pipeline_runs ─────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE pipeline_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id),
            job_id UUID NULL REFERENCES jobs(id) ON DELETE SET NULL,
            status TEXT NOT NULL,
            status_reason TEXT NULL,
            source_url TEXT NULL,
            package_path TEXT NULL,
            model TEXT NULL,
            provider TEXT NULL,
            heartbeat_at TIMESTAMPTZ NULL,
            started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            finished_at TIMESTAMPTZ NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT chk_pipeline_runs_status CHECK (
                status IN (
                    'running',
                    'generated',
                    'artifacts_persisted',
                    'delivered',
                    'failed'
                )
            )
        );
    """)

    # ── artifacts ─────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE artifacts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id),
            job_id UUID NULL REFERENCES jobs(id) ON DELETE SET NULL,
            pipeline_run_id UUID NULL REFERENCES pipeline_runs(id) ON DELETE SET NULL,
            kind TEXT NOT NULL,
            path TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)

    # ── Indexes ───────────────────────────────────────────────────────
    op.execute("""
        CREATE INDEX jobs_user_created_idx
            ON jobs(user_id, created_at DESC)
            WHERE deleted_at IS NULL;
    """)
    op.execute("""
        CREATE INDEX jobs_user_status_idx
            ON jobs(user_id, status)
            WHERE deleted_at IS NULL;
    """)
    op.execute("""
        CREATE INDEX pipeline_runs_user_started_idx
            ON pipeline_runs(user_id, started_at DESC);
    """)
    op.execute("""
        CREATE INDEX pipeline_runs_user_status_idx
            ON pipeline_runs(user_id, status);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS pipeline_runs_user_status_idx;")
    op.execute("DROP INDEX IF EXISTS pipeline_runs_user_started_idx;")
    op.execute("DROP INDEX IF EXISTS jobs_user_status_idx;")
    op.execute("DROP INDEX IF EXISTS jobs_user_created_idx;")
    op.execute("DROP TABLE IF EXISTS artifacts;")
    op.execute("DROP TABLE IF EXISTS pipeline_runs;")
    op.execute("DROP TABLE IF EXISTS jobs;")
    op.execute("DROP TABLE IF EXISTS users;")
