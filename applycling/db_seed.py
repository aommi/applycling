"""
Seed helper for local single-user mode.

Provides a function to ensure a local default user exists in the database.
This is called by PostgresStore (Ticket B) when resolving the local user.

Usage:
    from applycling.db_seed import seed_local_user
    seed_local_user(database_url)
"""

import os
import uuid

LOCAL_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def seed_local_user(database_url: str | None = None) -> uuid.UUID:
    """
    Ensure a local default user exists in the database.

    The user has no telegram_id or email — just a well-known UUID.
    This is idempotent: if a user already exists with the well-known
    UUID, the insert is a no-op.

    Args:
        database_url: Postgres connection URL. Defaults to
            DATABASE_URL env var or the alembic.ini value.

    Returns:
        The UUID of the local default user.
    """
    url = database_url or os.environ.get("DATABASE_URL")
    if not url:
        raise ValueError(
            "DATABASE_URL must be set or database_url must be provided"
        )

    # Lazy import to avoid psycopg dependency at module load time
    import psycopg

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (id)
                VALUES (%s)
                ON CONFLICT (id) DO NOTHING
                """,
                (str(LOCAL_USER_ID),),
            )
        conn.commit()

    return LOCAL_USER_ID


def get_local_user_id() -> uuid.UUID:
    """Return the well-known local default user UUID without touching the DB."""
    return LOCAL_USER_ID
