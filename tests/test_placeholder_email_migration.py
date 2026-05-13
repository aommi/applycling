"""Tests for legacy Telegram placeholder email cleanup migration."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace


def _load_migration():
    path = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "versions"
        / "008_null_telegram_placeholder_emails.py"
    )
    spec = importlib.util.spec_from_file_location("migration_008", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_placeholder_email_migration_predicate_is_conservative(monkeypatch):
    migration = _load_migration()
    executed: list[str] = []
    monkeypatch.setattr(
        migration,
        "op",
        SimpleNamespace(execute=lambda sql: executed.append(sql)),
    )

    migration.upgrade()

    assert len(executed) == 1
    sql = executed[0]
    assert "email = NULL" in sql
    assert "email ~ '^tg_[0-9]+@applycling[.]local$'" in sql
    assert "password_hash IS NULL" in sql


def test_placeholder_email_migration_downgrade_is_noop(monkeypatch):
    migration = _load_migration()
    calls: list[str] = []
    monkeypatch.setattr(
        migration,
        "op",
        SimpleNamespace(execute=lambda sql: calls.append(sql)),
    )

    migration.downgrade()

    assert calls == []
