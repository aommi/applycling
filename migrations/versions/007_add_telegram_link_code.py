"""add telegram link code fields to users.

Revision ID: 007_add_telegram_link_code
Revises: 006_add_password_hash
Create Date: 2026-05-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "007_add_telegram_link_code"
down_revision: Union[str, Sequence[str], None] = "006_add_password_hash"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("telegram_link_code_hash", sa.Text(), nullable=True))
    op.add_column(
        "users",
        sa.Column("telegram_link_code_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint(
        "uq_users_telegram_link_code_hash",
        "users",
        ["telegram_link_code_hash"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_users_telegram_link_code_hash", "users", type_="unique")
    op.drop_column("users", "telegram_link_code_expires_at")
    op.drop_column("users", "telegram_link_code_hash")
