"""add user profile columns

Revision ID: 4de3ace06e94
Revises: de27a01135bc
Create Date: 2026-05-10 23:16:39.174629

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '4de3ace06e94'
down_revision: Union[str, Sequence[str], None] = 'de27a01135bc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('profile', postgresql.JSONB, nullable=True))
    op.add_column('users', sa.Column('resume', sa.Text, nullable=True))
    op.add_column('users', sa.Column('stories', sa.Text, nullable=True))
    op.add_column('users', sa.Column('linkedin_profile', sa.Text, nullable=True))
    op.add_column('users', sa.Column('config', postgresql.JSONB, nullable=True))
    op.add_column('users', sa.Column('chat_id', sa.BigInteger, nullable=True))
    op.add_column('users', sa.Column('generation_count', sa.Integer, nullable=False, server_default='0'))
    op.add_column('users', sa.Column('generation_date', sa.Date, nullable=True))
    op.add_column('users', sa.Column('daily_generation_limit', sa.Integer, nullable=False, server_default='10'))
    op.add_column('users', sa.Column('intake_secret_hash', sa.String(64), nullable=True))
    op.create_unique_constraint('uq_users_intake_secret_hash', 'users', ['intake_secret_hash'])


def downgrade() -> None:
    op.drop_constraint('uq_users_intake_secret_hash', 'users', type_='unique')
    op.drop_column('users', 'intake_secret_hash')
    op.drop_column('users', 'daily_generation_limit')
    op.drop_column('users', 'generation_date')
    op.drop_column('users', 'generation_count')
    op.drop_column('users', 'chat_id')
    op.drop_column('users', 'config')
    op.drop_column('users', 'linkedin_profile')
    op.drop_column('users', 'stories')
    op.drop_column('users', 'resume')
    op.drop_column('users', 'profile')
