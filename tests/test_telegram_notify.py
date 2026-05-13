"""Tests for Telegram notification helpers."""

from __future__ import annotations

from applycling import telegram_notify


class _FakeCursor:
    def __init__(self, row):
        self.row = row

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def execute(self, *args, **kwargs):  # noqa: ARG002
        return None

    def fetchone(self):
        return self.row


class _FakeConn:
    def __init__(self, row):
        self.row = row

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def cursor(self):
        return _FakeCursor(self.row)


def test_get_chat_id_for_user_treats_zero_as_missing(monkeypatch):
    """Legacy chat_id=0 rows should not send Telegram requests to chat 0."""
    import psycopg

    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    monkeypatch.setattr(psycopg, "connect", lambda *args, **kwargs: _FakeConn((0,)))

    assert telegram_notify._get_chat_id_for_user("user-1") is None


def test_get_chat_id_for_user_missing_row(monkeypatch):
    import psycopg

    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    monkeypatch.setattr(psycopg, "connect", lambda *args, **kwargs: _FakeConn(None))

    assert telegram_notify._get_chat_id_for_user("user-1") is None
