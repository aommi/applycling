"""initial_workflow_schema

Revision ID: 64437a34178f
Revises:
Create Date: 2026-04-28 02:33:46.865155

Creates the core workflow schema: users, jobs, pipeline_runs, artifacts.
Includes CHECK constraints and performance indexes per DB_TECH_DESIGN.md §9.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "64437a34178f"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STATUS_JOB = (
    "new", "generating", "reviewing", "reviewed", "applied",
    "interviewing", "offered", "accepted", "rejected", "failed", "archived",
)
STATUS_PIPELINE = ("running", "generated", "artifacts_persisted", "delivered", "failed")


def upgrade() -> None:
    # ── users ─────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("telegram_id", sa.BigInteger(), unique=True, nullable=True),
        sa.Column("email", sa.Text(), unique=True, nullable=True),
        sa.Column("is_blocked", sa.Boolean(), nullable=False,
                  server_default=sa.text("FALSE")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── jobs ──────────────────────────────────────────────────────────
    op.create_table(
        "jobs",
        sa.Column("id", sa.UUID(), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("company", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False,
                  server_default=sa.text("'new'")),
        sa.Column("status_reason", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("application_url", sa.Text(), nullable=True),
        sa.Column("fit_summary", sa.Text(), nullable=True),
        sa.Column("package_folder", sa.Text(), nullable=True),
        sa.Column("notion_page_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "chk_jobs_status", "jobs",
        sa.text(f"status IN {STATUS_JOB}"),
    )

    # ── pipeline_runs ─────────────────────────────────────────────────
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.UUID(), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("job_id", sa.UUID(), sa.ForeignKey("jobs.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("status_reason", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("package_path", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("provider", sa.Text(), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_check_constraint(
        "chk_pipeline_runs_status", "pipeline_runs",
        sa.text(f"status IN {STATUS_PIPELINE}"),
    )

    # ── artifacts ─────────────────────────────────────────────────────
    op.create_table(
        "artifacts",
        sa.Column("id", sa.UUID(), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("job_id", sa.UUID(), sa.ForeignKey("jobs.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("pipeline_run_id", sa.UUID(),
                  sa.ForeignKey("pipeline_runs.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    # ── Indexes ───────────────────────────────────────────────────────
    op.create_index(
        "jobs_user_created_idx", "jobs",
        ["user_id", sa.text("created_at DESC")],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "jobs_user_status_idx", "jobs",
        ["user_id", "status"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "pipeline_runs_user_started_idx", "pipeline_runs",
        ["user_id", sa.text("started_at DESC")],
    )
    op.create_index(
        "pipeline_runs_user_status_idx", "pipeline_runs",
        ["user_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("pipeline_runs_user_status_idx")
    op.drop_index("pipeline_runs_user_started_idx")
    op.drop_index("jobs_user_status_idx")
    op.drop_index("jobs_user_created_idx")
    op.drop_table("artifacts")
    op.drop_table("pipeline_runs")
    op.drop_table("jobs")
    op.drop_table("users")
