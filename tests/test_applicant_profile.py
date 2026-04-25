"""Regression tests for applicant profile persistence and prompt injection."""

from __future__ import annotations

import json

from applycling import pipeline, storage


def test_save_applicant_profile_can_clear_merged_fields(tmp_path, monkeypatch):
    profile_path = tmp_path / "applicant_profile.json"
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setattr(storage, "APPLICANT_PROFILE_PATH", profile_path)

    storage.save_applicant_profile(
        {
            "work_auth": "Canadian PR",
            "sponsorship_needed": True,
            "relocation": True,
            "relocation_cities": ["Toronto", "Vancouver"],
            "comp_expectation": "$150k CAD",
            "notice_period": "2 weeks",
            "earliest_start_date": "2026-05-01",
        }
    )
    storage.save_applicant_profile(
        {
            "work_auth": "",
            "sponsorship_needed": None,
            "relocation": None,
            "relocation_cities": [],
            "comp_expectation": "",
            "notice_period": "",
            "earliest_start_date": "",
        }
    )

    saved = json.loads(profile_path.read_text(encoding="utf-8"))
    assert saved["work_auth"] == ""
    assert saved["sponsorship_needed"] is None
    assert saved["relocation"] is None
    assert saved["relocation_cities"] == []
    assert saved["comp_expectation"] == ""
    assert saved["notice_period"] == ""
    assert saved["earliest_start_date"] == ""


def test_applicant_profile_block_skips_cleared_values():
    block = pipeline._applicant_profile_block(
        {
            "work_auth": "",
            "sponsorship_needed": None,
            "relocation": False,
            "relocation_cities": [],
            "remote_preference": "flexible",
            "comp_expectation": "",
            "notice_period": "",
            "earliest_start_date": "",
        }
    )

    assert "Work authorization" not in block
    assert "Sponsorship needed" not in block
    assert "Relocation cities" not in block
    assert "Compensation expectations" not in block
    assert "Notice period" not in block
    assert "Earliest start date" not in block
    assert "Open to relocation: no" in block
    assert "Remote preference: flexible" in block
