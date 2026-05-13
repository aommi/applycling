"""Tests for admin user maintenance helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from applycling import user_admin


def test_merged_user_fields_prefers_target_but_fills_missing_values():
    source = {
        "telegram_id": 123,
        "chat_id": 456,
        "email": None,
        "display_name": "Telegram Name",
        "password_hash": None,
        "onboarding_state": "active",
        "profile": {"name": "Source Name", "phone": "111"},
        "config": {"provider": "anthropic"},
        "resume": "source resume",
        "stories": "source stories",
        "linkedin_profile": "source linkedin",
    }
    target = {
        "telegram_id": None,
        "chat_id": None,
        "email": "web@example.com",
        "display_name": "Web Name",
        "password_hash": "hash",
        "onboarding_state": "new",
        "profile": {"name": "Target Name", "email": "web@example.com"},
        "config": {"model": "claude"},
        "resume": "",
        "stories": None,
        "linkedin_profile": "",
    }

    merged = user_admin._merged_user_fields(source, target)

    assert merged["telegram_id"] == 123
    assert merged["chat_id"] == 456
    assert merged["email"] == "web@example.com"
    assert merged["display_name"] == "Web Name"
    assert merged["password_hash"] == "hash"
    assert merged["onboarding_state"] == "active"
    assert merged["profile"] == {
        "name": "Target Name",
        "phone": "111",
        "email": "web@example.com",
    }
    assert merged["config"] == {"provider": "anthropic", "model": "claude"}
    assert merged["resume"] == "source resume"
    assert merged["stories"] == "source stories"
    assert merged["linkedin_profile"] == "source linkedin"


def test_merge_users_rejects_same_user():
    user_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

    try:
        user_admin.merge_users(user_id, user_id, database_url="postgresql://example")
    except user_admin.UserMergeError as exc:
        assert "must differ" in str(exc)
    else:
        raise AssertionError("expected UserMergeError")


def test_parse_telegram_link_code_accepts_link_commands():
    assert user_admin.parse_telegram_link_code("link ABC123") == "ABC123"
    assert user_admin.parse_telegram_link_code("connect abc123") == "ABC123"
    assert user_admin.parse_telegram_link_code("hello ABC123") is None
    assert user_admin.parse_telegram_link_code("link short") is None


def test_generate_link_code_is_parseable(monkeypatch):
    values = iter(["__----__", "ABCDEF12345"])
    monkeypatch.setattr("secrets.token_urlsafe", lambda n: next(values))

    assert user_admin._generate_link_code() == "ABCDEF12"


def test_users_merge_cli_invokes_service(monkeypatch):
    from applycling import cli

    called = {}

    def _fake_merge_users(source_user_id, target_user_id, *, dry_run=False):
        called["args"] = (source_user_id, target_user_id)
        called["dry_run"] = dry_run
        return {
            "source_user_id": source_user_id,
            "target_user_id": target_user_id,
            "dry_run": dry_run,
            "moved": {"jobs": 1, "pipeline_runs": 2, "artifacts": 3},
            "merged_fields": {
                "email": "web@example.com",
                "telegram_id": 123,
                "chat_id": 456,
                "onboarding_state": "active",
            },
        }

    monkeypatch.setattr("applycling.user_admin.merge_users", _fake_merge_users)

    result = CliRunner().invoke(
        cli.main,
        [
            "users",
            "merge",
            "--source-user-id",
            "source-id",
            "--target-user-id",
            "target-id",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert called == {"args": ("source-id", "target-id"), "dry_run": True}
    assert "DRY RUN" in result.output
    assert "jobs=1" in result.output


def test_users_link_code_cli_invokes_service(monkeypatch):
    from datetime import datetime, timezone

    from applycling import cli

    called = {}

    def _fake_create_link_code(user_id, *, ttl_minutes=30):
        called["args"] = (user_id, ttl_minutes)
        return {
            "user_id": user_id,
            "email": "web@example.com",
            "display_name": "Web User",
            "telegram_id": None,
            "code": "ABC12345",
            "expires_at": datetime(2026, 5, 13, tzinfo=timezone.utc),
        }

    monkeypatch.setattr(
        "applycling.user_admin.create_telegram_link_code",
        _fake_create_link_code,
    )

    result = CliRunner().invoke(
        cli.main,
        [
            "users",
            "link-code",
            "--user-id",
            "target-id",
            "--ttl-minutes",
            "15",
        ],
    )

    assert result.exit_code == 0
    assert called == {"args": ("target-id", 15)}
    assert "ABC12345" in result.output
    assert "link ABC12345" in result.output


# ── reset_password ────────────────────────────────────────────────────


class _FakeCursor:
    def __init__(self, rowcount: int):
        self.rowcount = rowcount


class _FakeConn:
    def __init__(self, rowcount: int):
        self._cursor = _FakeCursor(rowcount)
        self.executed: list[tuple] = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def execute(self, sql, params):
        self.executed.append((sql, params))
        return self._cursor


def test_reset_password_updates_hash_and_returns_plaintext(monkeypatch):
    fake_conn = _FakeConn(rowcount=1)

    def _connect(_url):
        return fake_conn

    import psycopg
    monkeypatch.setattr(psycopg, "connect", _connect)

    password = user_admin.reset_password(
        "11111111-1111-1111-1111-111111111111",
        database_url="postgresql://example",
    )

    assert isinstance(password, str)
    assert len(password) >= 12
    # The stored hash is the second-to-last param (sql, params) tuple.
    _, params = fake_conn.executed[0]
    stored_hash = params[0]
    # Hash should not equal the plaintext.
    assert stored_hash != password
    # And the hashed plaintext should verify successfully.
    from applycling.auth import verify_password
    assert verify_password(password, stored_hash)


def test_reset_password_rejects_missing_user(monkeypatch):
    fake_conn = _FakeConn(rowcount=0)
    import psycopg
    monkeypatch.setattr(psycopg, "connect", lambda _url: fake_conn)

    with pytest.raises(ValueError, match="user not found"):
        user_admin.reset_password(
            "11111111-1111-1111-1111-111111111111",
            database_url="postgresql://example",
        )


def test_reset_password_rejects_non_uuid():
    with pytest.raises(ValueError, match="UUID"):
        user_admin.reset_password("not-a-uuid", database_url="postgresql://x")


def test_reset_password_requires_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValueError, match="DATABASE_URL"):
        user_admin.reset_password("11111111-1111-1111-1111-111111111111")
