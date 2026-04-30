"""add pipeline_runs unique index

Revision ID: de27a01135bc
Revises: 64437a34178f
Create Date: 2026-04-29 15:10:28.174236

Adds a partial unique index on pipeline_runs(user_id) WHERE status = 'running'.
This ensures at most one active run exists per user at the database level,
enabling atomic INSERT ... ON CONFLICT for race-free active-run guarding.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'de27a01135bc'
down_revision: Union[str, Sequence[str], None] = '64437a34178f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_pipeline_runs_active "
        "ON pipeline_runs (user_id) WHERE status = 'running'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_pipeline_runs_active")
