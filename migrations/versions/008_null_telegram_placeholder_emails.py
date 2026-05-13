"""null legacy Telegram placeholder emails.

Revision ID: 008_null_telegram_placeholder_emails
Revises: 007_add_telegram_link_code
Create Date: 2026-05-13
"""
from typing import Sequence, Union

from alembic import op


revision: str = "008_null_telegram_placeholder_emails"
down_revision: Union[str, Sequence[str], None] = "007_add_telegram_link_code"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE users
        SET email = NULL,
            updated_at = NOW()
        WHERE email ~ '^tg_[0-9]+@applycling[.]local$'
          AND password_hash IS NULL
        """
    )


def downgrade() -> None:
    # Intentionally irreversible cleanup: these were synthetic placeholders,
    # not user-supplied email addresses.
    pass
