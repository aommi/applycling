"""Admin-only user maintenance helpers."""

from __future__ import annotations

import os
import secrets
import hashlib
import uuid
import datetime as dt
from typing import Any


class UserMergeError(ValueError):
    """Raised when two user rows cannot be merged safely."""


class TelegramLinkError(ValueError):
    """Raised when a Telegram account link cannot be completed."""


def _hash_link_code(code: str) -> str:
    return hashlib.sha256(code.strip().upper().encode()).hexdigest()


def _generate_link_code() -> str:
    """Return a Telegram-friendly one-time code."""
    while True:
        code = secrets.token_urlsafe(8).replace("_", "").replace("-", "").upper()[:8]
        if len(code) >= 6:
            return code


def parse_telegram_link_code(text: str) -> str | None:
    """Return a link code from a Telegram message, if it is a link command."""
    parts = text.strip().split()
    if len(parts) != 2:
        return None
    if parts[0].lower() not in {"link", "connect"}:
        return None
    code = parts[1].strip().upper()
    return code if len(code) >= 6 else None


def _missing(value: Any) -> bool:
    return value in (None, "", [], {})


def _prefer_target(source: Any, target: Any) -> Any:
    """Return target unless it is empty, otherwise source."""
    return source if _missing(target) else target


def _merge_dict(source: dict | None, target: dict | None) -> dict:
    """Merge JSON objects, preserving target values on conflict."""
    merged: dict = {}
    if source:
        merged.update(source)
    if target:
        merged.update(target)
    return merged


def _merge_onboarding_state(source: str | None, target: str | None) -> str:
    """Keep the most progressed onboarding state."""
    order = {"new": 0, "confirming": 1, "active": 2}
    source_state = source or "new"
    target_state = target or "new"
    return source_state if order[source_state] > order[target_state] else target_state


def _merged_user_fields(source: dict, target: dict) -> dict[str, Any]:
    return {
        "telegram_id": _prefer_target(source.get("telegram_id"), target.get("telegram_id")),
        "chat_id": _prefer_target(source.get("chat_id"), target.get("chat_id")),
        "email": _prefer_target(source.get("email"), target.get("email")),
        "display_name": _prefer_target(source.get("display_name"), target.get("display_name")),
        "password_hash": _prefer_target(source.get("password_hash"), target.get("password_hash")),
        "onboarding_state": _merge_onboarding_state(
            source.get("onboarding_state"),
            target.get("onboarding_state"),
        ),
        "profile": _merge_dict(source.get("profile"), target.get("profile")),
        "config": _merge_dict(source.get("config"), target.get("config")),
        "resume": _prefer_target(source.get("resume"), target.get("resume")),
        "stories": _prefer_target(source.get("stories"), target.get("stories")),
        "linkedin_profile": _prefer_target(
            source.get("linkedin_profile"),
            target.get("linkedin_profile"),
        ),
    }


def _user_columns() -> str:
    return (
        "id, telegram_id, email, chat_id, display_name, password_hash, "
        "onboarding_state, profile, resume, stories, linkedin_profile, config"
    )


def create_telegram_link_code(
    user_id: str,
    *,
    database_url: str | None = None,
    ttl_minutes: int = 30,
) -> dict[str, Any]:
    """Create a one-time Telegram link code for an existing web user."""
    if ttl_minutes <= 0:
        raise TelegramLinkError("ttl_minutes must be positive")

    db_url = database_url or os.environ.get("DATABASE_URL")
    if not db_url:
        raise TelegramLinkError("DATABASE_URL must be set")

    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError as exc:
        raise TelegramLinkError("user ID must be a UUID") from exc

    import psycopg
    import psycopg.rows

    code = _generate_link_code()
    expires_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=ttl_minutes)

    with psycopg.connect(db_url, row_factory=psycopg.rows.dict_row) as conn:
        row = conn.execute(
            """
            UPDATE users
            SET telegram_link_code_hash = %s,
                telegram_link_code_expires_at = %s,
                updated_at = NOW()
            WHERE id = %s AND deleted_at IS NULL
            RETURNING id, email, display_name, telegram_id
            """,
            (_hash_link_code(code), expires_at, user_uuid),
        ).fetchone()
    if row is None:
        raise TelegramLinkError("user not found")

    return {
        "user_id": str(row["id"]),
        "email": row["email"],
        "display_name": row["display_name"],
        "telegram_id": row["telegram_id"],
        "code": code,
        "expires_at": expires_at,
    }


def consume_telegram_link_code(
    code: str,
    *,
    telegram_id: int,
    chat_id: int | None = None,
    first_name: str | None = None,
    database_url: str | None = None,
) -> dict[str, Any]:
    """Attach a Telegram identity to the user row identified by *code*.

    If the Telegram identity already created a duplicate source row, that row
    is merged into the target user before being soft-deleted.
    """
    db_url = database_url or os.environ.get("DATABASE_URL")
    if not db_url:
        raise TelegramLinkError("DATABASE_URL must be set")

    normalized_chat_id = chat_id if chat_id not in (None, 0) else None

    import psycopg
    import psycopg.rows
    from psycopg.types.json import Jsonb

    code_hash = _hash_link_code(code)

    with psycopg.connect(db_url, row_factory=psycopg.rows.dict_row) as conn:
        with conn.transaction():
            target = conn.execute(
                f"""
                SELECT {_user_columns()}
                FROM users
                WHERE telegram_link_code_hash = %s
                  AND telegram_link_code_expires_at > NOW()
                  AND deleted_at IS NULL
                FOR UPDATE
                """,
                (code_hash,),
            ).fetchone()
            if target is None:
                raise TelegramLinkError("link code is invalid or expired")

            target_uuid = target["id"]
            existing = conn.execute(
                f"""
                SELECT {_user_columns()}
                FROM users
                WHERE telegram_id = %s AND deleted_at IS NULL
                FOR UPDATE
                """,
                (telegram_id,),
            ).fetchone()

            target_telegram_id = target["telegram_id"]
            if target_telegram_id not in (None, telegram_id):
                raise TelegramLinkError("target user is already linked to another Telegram account")

            source_uuid = None
            moved = {"jobs": 0, "pipeline_runs": 0, "artifacts": 0}
            if existing is not None and existing["id"] != target_uuid:
                source_uuid = existing["id"]
                running = conn.execute(
                    """
                    SELECT user_id
                    FROM pipeline_runs
                    WHERE user_id = ANY(%s) AND status = 'running'
                    LIMIT 1
                    """,
                    ([source_uuid, target_uuid],),
                ).fetchone()
                if running is not None:
                    raise TelegramLinkError("cannot link while a pipeline is running")

                moved = {
                    "jobs": conn.execute(
                        "SELECT COUNT(*) AS count FROM jobs WHERE user_id = %s",
                        (source_uuid,),
                    ).fetchone()["count"],
                    "pipeline_runs": conn.execute(
                        "SELECT COUNT(*) AS count FROM pipeline_runs WHERE user_id = %s",
                        (source_uuid,),
                    ).fetchone()["count"],
                    "artifacts": conn.execute(
                        "SELECT COUNT(*) AS count FROM artifacts WHERE user_id = %s",
                        (source_uuid,),
                    ).fetchone()["count"],
                }
                merged = _merged_user_fields(existing, target)

                conn.execute(
                    "UPDATE jobs SET user_id = %s, updated_at = NOW() WHERE user_id = %s",
                    (target_uuid, source_uuid),
                )
                conn.execute(
                    """
                    UPDATE pipeline_runs
                    SET user_id = %s, updated_at = NOW()
                    WHERE user_id = %s
                    """,
                    (target_uuid, source_uuid),
                )
                conn.execute(
                    """
                    UPDATE artifacts
                    SET user_id = %s, updated_at = NOW()
                    WHERE user_id = %s
                    """,
                    (target_uuid, source_uuid),
                )
                conn.execute(
                    """
                    UPDATE users
                    SET telegram_id = NULL,
                        email = NULL,
                        chat_id = NULL,
                        deleted_at = NOW(),
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (source_uuid,),
                )
            else:
                merged = _merged_user_fields({}, target)

            if normalized_chat_id is not None:
                merged["chat_id"] = normalized_chat_id
            merged["telegram_id"] = telegram_id
            merged["display_name"] = _prefer_target(first_name, merged["display_name"])
            merged["onboarding_state"] = _merge_onboarding_state(
                "active",
                merged["onboarding_state"],
            )

            conn.execute(
                """
                UPDATE users
                SET telegram_id = %s,
                    chat_id = %s,
                    display_name = %s,
                    onboarding_state = %s,
                    profile = %s,
                    resume = %s,
                    stories = %s,
                    linkedin_profile = %s,
                    config = %s,
                    telegram_link_code_hash = NULL,
                    telegram_link_code_expires_at = NULL,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (
                    merged["telegram_id"],
                    merged["chat_id"],
                    merged["display_name"],
                    merged["onboarding_state"],
                    Jsonb(merged["profile"]),
                    merged["resume"],
                    merged["stories"],
                    merged["linkedin_profile"],
                    Jsonb(merged["config"]),
                    target_uuid,
                ),
            )
            # Email is intentionally not updated here. Link codes attach a
            # Telegram channel to an existing canonical user, whose web email
            # remains authoritative. The admin merge path may fill missing
            # target email from a source row because it is a repair operation.

    return {
        "user_id": str(target_uuid),
        "telegram_id": telegram_id,
        "chat_id": normalized_chat_id,
        "merged_source_user_id": str(source_uuid) if source_uuid else None,
        "moved": moved,
    }


def merge_users(
    source_user_id: str,
    target_user_id: str,
    *,
    database_url: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Merge a duplicate source user into a canonical target user.

    The target wins on conflicting profile/config/text fields. Missing target
    identity/profile data is filled from the source. Jobs, pipeline runs, and
    artifact rows move to the target, then the source is soft-deleted with its
    unique identity fields cleared.
    """
    if source_user_id == target_user_id:
        raise UserMergeError("source and target user IDs must differ")

    db_url = database_url or os.environ.get("DATABASE_URL")
    if not db_url:
        raise UserMergeError("DATABASE_URL must be set")

    try:
        source_uuid = uuid.UUID(source_user_id)
        target_uuid = uuid.UUID(target_user_id)
    except ValueError as exc:
        raise UserMergeError("source and target user IDs must be UUIDs") from exc

    import psycopg
    import psycopg.rows
    from psycopg.types.json import Jsonb

    with psycopg.connect(db_url, row_factory=psycopg.rows.dict_row) as conn:
        with conn.transaction():
            rows = conn.execute(
                f"""
                SELECT {_user_columns()}
                FROM users
                WHERE id = ANY(%s) AND deleted_at IS NULL
                FOR UPDATE
                """,
                ([source_uuid, target_uuid],),
            ).fetchall()
            by_id = {str(row["id"]): row for row in rows}
            source = by_id.get(str(source_uuid))
            target = by_id.get(str(target_uuid))
            if source is None or target is None:
                raise UserMergeError("source and target users must both exist")

            running = conn.execute(
                """
                SELECT user_id
                FROM pipeline_runs
                WHERE user_id = ANY(%s) AND status = 'running'
                LIMIT 1
                """,
                ([source_uuid, target_uuid],),
            ).fetchone()
            if running is not None:
                raise UserMergeError("cannot merge users while a pipeline is running")

            counts = {
                "jobs": conn.execute(
                    "SELECT COUNT(*) AS count FROM jobs WHERE user_id = %s",
                    (source_uuid,),
                ).fetchone()["count"],
                "pipeline_runs": conn.execute(
                    "SELECT COUNT(*) AS count FROM pipeline_runs WHERE user_id = %s",
                    (source_uuid,),
                ).fetchone()["count"],
                "artifacts": conn.execute(
                    "SELECT COUNT(*) AS count FROM artifacts WHERE user_id = %s",
                    (source_uuid,),
                ).fetchone()["count"],
            }
            merged = _merged_user_fields(source, target)

            if dry_run:
                return {
                    "source_user_id": str(source_uuid),
                    "target_user_id": str(target_uuid),
                    "dry_run": True,
                    "moved": counts,
                    "merged_fields": merged,
                }

            conn.execute(
                "UPDATE jobs SET user_id = %s, updated_at = NOW() WHERE user_id = %s",
                (target_uuid, source_uuid),
            )
            conn.execute(
                """
                UPDATE pipeline_runs
                SET user_id = %s, updated_at = NOW()
                WHERE user_id = %s
                """,
                (target_uuid, source_uuid),
            )
            conn.execute(
                """
                UPDATE artifacts
                SET user_id = %s, updated_at = NOW()
                WHERE user_id = %s
                """,
                (target_uuid, source_uuid),
            )
            conn.execute(
                """
                UPDATE users
                SET telegram_id = NULL,
                    email = NULL,
                    chat_id = NULL,
                    deleted_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
                """,
                (source_uuid,),
            )
            conn.execute(
                """
                UPDATE users
                SET telegram_id = %s,
                    chat_id = %s,
                    email = %s,
                    display_name = %s,
                    password_hash = %s,
                    onboarding_state = %s,
                    profile = %s,
                    resume = %s,
                    stories = %s,
                    linkedin_profile = %s,
                    config = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (
                    merged["telegram_id"],
                    merged["chat_id"],
                    merged["email"],
                    merged["display_name"],
                    merged["password_hash"],
                    merged["onboarding_state"],
                    Jsonb(merged["profile"]),
                    merged["resume"],
                    merged["stories"],
                    merged["linkedin_profile"],
                    Jsonb(merged["config"]),
                    target_uuid,
                ),
            )

    return {
        "source_user_id": str(source_uuid),
        "target_user_id": str(target_uuid),
        "dry_run": False,
        "moved": counts,
        "merged_fields": merged,
    }
