"""Tests for the unified Application Profile — PROFILE-T1."""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest

from applycling import storage


# ── profile_completeness ──────────────────────────────────────────────────

class TestProfileCompleteness:
    def test_returns_missing_contact_for_empty_profile(self):
        assert storage.profile_completeness({}) == "missing_contact"

    def test_returns_missing_contact_when_name_is_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(storage, "RESUME_PATH", tmp_path / "resume.md")
        (tmp_path / "resume.md").write_text("resume content")
        assert (
            storage.profile_completeness({"name": "", "email": "a@b.com"})
            == "missing_contact"
        )

    def test_returns_missing_resume_when_resume_path_does_not_exist(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(storage, "RESUME_PATH", tmp_path / "resume.md")
        assert (
            storage.profile_completeness({"name": "A", "email": "a@b.com"})
            == "missing_resume"
        )

    def test_returns_ready_when_name_email_and_resume_exist(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(storage, "RESUME_PATH", tmp_path / "resume.md")
        (tmp_path / "resume.md").write_text("resume")
        assert (
            storage.profile_completeness({"name": "A", "email": "a@b.com"})
            == "ready"
        )

    def test_returns_enriched_with_3_deferred_fields(self, tmp_path, monkeypatch):
        monkeypatch.setattr(storage, "RESUME_PATH", tmp_path / "resume.md")
        (tmp_path / "resume.md").write_text("resume")
        profile = {
            "name": "A",
            "email": "a@b.com",
            "work_auth": "PR",
            "sponsorship_needed": False,
            "relocation": True,
        }
        assert storage.profile_completeness(profile) == "enriched"

    def test_returns_complete_when_all_deferred_filled(self, tmp_path, monkeypatch):
        monkeypatch.setattr(storage, "RESUME_PATH", tmp_path / "resume.md")
        (tmp_path / "resume.md").write_text("resume")
        profile = {
            "name": "A",
            "email": "a@b.com",
        }
        for key in storage.DEFERRED_PROFILE_FIELDS:
            profile[key] = "set"
        # Boolean fields: False counts as non-empty, so use True to be safe
        profile["sponsorship_needed"] = False
        profile["relocation"] = True
        assert storage.profile_completeness(profile) == "complete"


# ── missing_required_fields ───────────────────────────────────────────────

class TestMissingRequiredFields:
    def test_returns_empty_list_when_all_present(self):
        assert (
            storage.missing_required_fields(
                {"name": "A", "email": "a@b.com"}, ["name", "email"]
            )
            == []
        )

    def test_returns_missing_fields_when_none_or_empty(self):
        result = storage.missing_required_fields(
            {"a": None, "b": "", "c": [], "d": "ok"},
            ["a", "b", "c", "d", "e"],
        )
        assert set(result) == {"a", "b", "c", "e"}

    def test_treats_false_as_present(self):
        result = storage.missing_required_fields(
            {"sponsorship_needed": False, "relocation": True},
            ["sponsorship_needed", "relocation"],
        )
        assert result == []

    def test_treats_empty_list_as_missing(self):
        result = storage.missing_required_fields(
            {"cities": []}, ["cities"]
        )
        assert result == ["cities"]


# ── deprecated wrappers ───────────────────────────────────────────────────

class TestOldApplicantProfileDeliberatelyIgnored:
    def test_old_file_is_not_merged(self, tmp_path, monkeypatch):
        profile_path = tmp_path / "profile.json"
        ap_path = tmp_path / "applicant_profile.json"

        monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
        monkeypatch.setattr(storage, "PROFILE_PATH", profile_path)
        monkeypatch.setattr(storage, "APPLICANT_PROFILE_PATH", ap_path)
        monkeypatch.setattr(storage, "RESUME_PATH", tmp_path / "resume.md")

        # Current unified profile.json
        profile_path.write_text(
            json.dumps({"name": "Test", "email": "t@t.com"}),
            encoding="utf-8",
        )
        # Old applicant_profile.json with data that should NOT be merged
        ap_path.write_text(
            json.dumps({"work_auth": "should-not-appear"}),
            encoding="utf-8",
        )

        unified = storage.load_profile()

        assert unified["name"] == "Test"
        assert unified.get("work_auth") in (None, "")  # NOT merged
        # No .migrated file created
        assert not (tmp_path / "applicant_profile.json.migrated").exists()

    def test_deprecated_loader_reads_from_unified_profile_not_old_file(
        self, tmp_path, monkeypatch
    ):
        profile_path = tmp_path / "profile.json"
        ap_path = tmp_path / "applicant_profile.json"

        monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
        monkeypatch.setattr(storage, "PROFILE_PATH", profile_path)
        monkeypatch.setattr(storage, "APPLICANT_PROFILE_PATH", ap_path)
        monkeypatch.setattr(storage, "RESUME_PATH", tmp_path / "resume.md")

        # Unified profile has work_auth
        profile_path.write_text(
            json.dumps({"name": "T", "email": "t@t.com", "work_auth": "from-profile"}),
            encoding="utf-8",
        )
        # Old file has stale data
        ap_path.write_text(
            json.dumps({"work_auth": "from-old-file"}),
            encoding="utf-8",
        )

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            ap = storage.load_applicant_profile()

        assert ap.get("work_auth") == "from-profile"  # from unified, not old file

class TestDeprecatedWrappers:
    def test_does_not_clobber_unrelated_fields(self, tmp_path, monkeypatch):
        profile_path = tmp_path / "profile.json"
        monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
        monkeypatch.setattr(storage, "PROFILE_PATH", profile_path)
        monkeypatch.setattr(storage, "APPLICANT_PROFILE_PATH",
                            tmp_path / "applicant_profile.json")
        monkeypatch.setattr(storage, "RESUME_PATH", tmp_path / "resume.md")

        # Set name via save_profile
        storage.save_profile({"name": "Test", "email": "t@t.com"})
        # Then save work_auth via deprecated wrapper
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            storage.save_applicant_profile({"work_auth": "PR"})

        unified = storage.load_profile()
        assert unified["name"] == "Test"  # not clobbered
        assert unified["work_auth"] == "PR"

    def test_returns_deferred_subset_from_deprecated_loader(
        self, tmp_path, monkeypatch
    ):
        profile_path = tmp_path / "profile.json"
        monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
        monkeypatch.setattr(storage, "PROFILE_PATH", profile_path)
        monkeypatch.setattr(storage, "APPLICANT_PROFILE_PATH",
                            tmp_path / "applicant_profile.json")
        monkeypatch.setattr(storage, "RESUME_PATH", tmp_path / "resume.md")

        storage.save_profile({
            "name": "Test",
            "email": "t@t.com",
            "work_auth": "PR",
            "relocation": True,
            "voice_tone": "casual",  # NOT in deferred set
        })

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            ap = storage.load_applicant_profile()

        assert ap["work_auth"] == "PR"
        assert ap["relocation"] is True
        assert "voice_tone" not in ap  # excluded: not in DEFERRED_PROFILE_FIELDS
        assert "name" not in ap  # not a deferred field


# ── schema version ────────────────────────────────────────────────────────

class TestSchemaVersion:
    def test_warns_on_future_version(self, tmp_path, monkeypatch):
        profile_path = tmp_path / "profile.json"
        monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
        monkeypatch.setattr(storage, "PROFILE_PATH", profile_path)
        monkeypatch.setattr(storage, "APPLICANT_PROFILE_PATH",
                            tmp_path / "applicant_profile.json")
        monkeypatch.setattr(storage, "RESUME_PATH", tmp_path / "resume.md")

        profile_path.write_text(
            json.dumps({"name": "T", "email": "t@t.com", "schema_version": "99.0"}),
            encoding="utf-8",
        )

        with pytest.warns(UserWarning, match="schema version"):
            unified = storage.load_profile()

        assert unified["name"] == "T"  # still loads, doesn't crash

    def test_no_warnings_on_fresh_profile(self, tmp_path, monkeypatch):
        profile_path = tmp_path / "profile.json"
        monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
        monkeypatch.setattr(storage, "PROFILE_PATH", profile_path)
        monkeypatch.setattr(storage, "APPLICANT_PROFILE_PATH",
                            tmp_path / "applicant_profile.json")
        monkeypatch.setattr(storage, "RESUME_PATH", tmp_path / "resume.md")

        profile_path.write_text(
            json.dumps({"name": "T", "email": "t@t.com"}),
            encoding="utf-8",
        )

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            storage.load_profile()
        deprecation_warnings = [
            x for x in w if issubclass(x.category, DeprecationWarning)
        ]
        assert len(deprecation_warnings) == 0


# ── pipeline integration ──────────────────────────────────────────────────

class TestPipelineContext:
    def test_has_applicant_profile_property(self):
        from applycling.pipeline import PipelineContext

        ctx = PipelineContext(
            data_dir=Path("/tmp"),
            output_dir=Path("/tmp"),
            profile={
                "name": "Test",
                "work_auth": "PR",
                "sponsorship_needed": False,
                "voice_tone": "casual",
            },
            resume="resume",
            stories="",
            linkedin_profile=None,
            config={},
            model="test",
            provider="test",
            tracker_store=None,
        )

        ap = ctx.applicant_profile
        assert ap["work_auth"] == "PR"
        assert ap["sponsorship_needed"] is False
        assert "voice_tone" not in ap  # not a deferred field
