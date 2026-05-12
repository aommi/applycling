"""add onboarding_state and display_name to users.

Revision ID: 005_add_onboarding
Revises: 4de3ace06e94
Create Date: 2026-05-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "005_add_onboarding"
down_revision: Union[str, Sequence[str], None] = "4de3ace06e94"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "onboarding_state",
            sa.String(20),
            nullable=False,
            server_default="new",
        ),
    )
    op.add_column("users", sa.Column("display_name", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "display_name")
    op.drop_column("users", "onboarding_state")
