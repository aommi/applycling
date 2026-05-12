"""Tests for onboarding database support."""

from __future__ import annotations

import os
import random
import uuid

import pytest

from applycling.db_seed import get_or_create_user_by_telegram


@pytest.fixture
def db_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set")
    return url


@pytest.fixture
def telegram_id() -> int:
    return random.randint(90_000_000, 99_999_999)


def _delete_user_by_telegram(database_url: str, telegram_id: int) -> None:
    import psycopg

    with psycopg.connect(database_url) as conn:
        conn.execute("DELETE FROM users WHERE telegram_id = %s", (telegram_id,))


def test_get_or_create_user_by_telegram_creates_new_user(
    db_url: str,
    telegram_id: int,
) -> None:
    result = get_or_create_user_by_telegram(
        telegram_id=telegram_id,
        chat_id=telegram_id,
        first_name="Test User",
    )

    try:
        assert result["user_id"]
        assert result["telegram_id"] == telegram_id
        assert result["chat_id"] == telegram_id
        assert result["onboarding_state"] == "new"
        assert result["display_name"] == "Test User"
    finally:
        _delete_user_by_telegram(db_url, telegram_id)


def test_get_or_create_user_by_telegram_returns_existing_user(
    db_url: str,
    telegram_id: int,
) -> None:
    first = get_or_create_user_by_telegram(
        telegram_id=telegram_id,
        chat_id=telegram_id,
        first_name="Original",
    )
    second = get_or_create_user_by_telegram(
        telegram_id=telegram_id,
        chat_id=telegram_id + 1,
        first_name="Ignored",
    )

    try:
        assert second["user_id"] == first["user_id"]
        assert second["telegram_id"] == telegram_id
        assert second["chat_id"] == telegram_id
        assert second["display_name"] == "Original"
    finally:
        _delete_user_by_telegram(db_url, telegram_id)


def test_get_or_create_user_by_telegram_updates_missing_chat_id(
    db_url: str,
    telegram_id: int,
) -> None:
    first = get_or_create_user_by_telegram(telegram_id=telegram_id)
    second = get_or_create_user_by_telegram(
        telegram_id=telegram_id,
        chat_id=telegram_id,
    )

    try:
        assert first["chat_id"] is None
        assert second["user_id"] == first["user_id"]
        assert second["chat_id"] == telegram_id
    finally:
        _delete_user_by_telegram(db_url, telegram_id)


def test_save_and_load_onboarding_profile_fields(
    db_url: str,
    telegram_id: int,
) -> None:
    import psycopg

    user_id = str(uuid.uuid4())
    with psycopg.connect(db_url) as conn:
        conn.execute(
            """
            INSERT INTO users (id, telegram_id, email, onboarding_state)
            VALUES (%s, %s, %s, 'new')
            """,
            (user_id, telegram_id, f"test_{telegram_id}@applycling.local"),
        )

    try:
        from applycling.tracker.postgres_store import PostgresStore

        store = PostgresStore(database_url=db_url, user_id=user_id)
        store.save_user_profile(
            onboarding_state="confirming",
            display_name="Test User",
        )

        profile = store.load_user_profile()
        assert profile["onboarding_state"] == "confirming"
        assert profile["display_name"] == "Test User"
    finally:
        _delete_user_by_telegram(db_url, telegram_id)


def test_get_or_create_user_by_telegram_requires_database_url(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValueError, match="DATABASE_URL"):
        get_or_create_user_by_telegram(telegram_id=123)
