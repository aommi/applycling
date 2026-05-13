"""Tests for admin user maintenance helpers."""

from __future__ import annotations

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
