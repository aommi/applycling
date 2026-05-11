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


def seed_user_by_telegram(telegram_id: int, chat_id: int | None,
                          name: str, email: str | None = None,
                          intake_secret_hash: str | None = None,
                          daily_limit: int = 10) -> str:
    """Create a user with telegram_id and profile seed data. Returns UUID.

    Raises ValueError if a user with this telegram_id already exists.
    """
    import json
    import psycopg

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL must be set")

    user_id = str(uuid.uuid4())
    email = email or f"tg_{telegram_id}@applycling.local"

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            # Check for duplicate
            cur.execute(
                "SELECT id FROM users WHERE telegram_id = %s AND deleted_at IS NULL",
                (telegram_id,),
            )
            if cur.fetchone():
                raise ValueError(
                    f"User with telegram_id {telegram_id} already exists. "
                    f"Use 'applycling users list' to see existing users."
                )

            cur.execute(
                """INSERT INTO users (id, telegram_id, email, chat_id,
                   intake_secret_hash, daily_generation_limit,
                   profile, created_at, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), NOW())""",
                (user_id, telegram_id, email, chat_id, intake_secret_hash,
                 daily_limit,
                 json.dumps({"name": name, "schema_version": "1.0"})),
            )
        conn.commit()

    return user_id


def get_user_by_telegram(telegram_id: int) -> str | None:
    """Return user UUID for a telegram_id, or None if not found."""
    import psycopg

    url = os.environ.get("DATABASE_URL")
    if not url:
        return None

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM users WHERE telegram_id = %s AND deleted_at IS NULL",
                (telegram_id,),
            )
            row = cur.fetchone()
    return str(row[0]) if row else None
