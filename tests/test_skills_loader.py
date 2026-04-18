"""Tests for the skill loader (applycling/skills/loader.py).

Covers: load, missing skill, render with valid kwargs, missing inputs,
inputs list validation, name mismatch, all 16 skills loadable.
"""

from __future__ import annotations

import pytest

from applycling.skills import Skill, SkillError, load_skill


# ---------------------------------------------------------------------------
# Basic load
# ---------------------------------------------------------------------------

def test_load_skill_returns_skill_instance():
    skill = load_skill("role_intel")
    assert isinstance(skill, Skill)
    assert skill.name == "role_intel"


def test_load_skill_has_description():
    skill = load_skill("cover_letter")
    assert skill.description, "description should be non-empty"


def test_load_skill_has_inputs():
    skill = load_skill("resume_tailor")
    assert "resume" in skill.inputs
    assert "job_description" in skill.inputs


def test_load_skill_has_output_file():
    skill = load_skill("fit_summary")
    assert skill.output_file == "fit_summary.md"


def test_load_skill_no_output_file_for_profile_summary():
    skill = load_skill("profile_summary")
    assert skill.output_file is None


# ---------------------------------------------------------------------------
# Missing skill
# ---------------------------------------------------------------------------

def test_load_skill_missing_raises_skill_error():
    with pytest.raises(SkillError, match="not found"):
        load_skill("nonexistent_skill_xyz")


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def test_render_with_valid_kwargs():
    skill = load_skill("fit_summary")
    result = skill.render(resume="My resume", job_description="My JD")
    assert "My resume" in result
    assert "My JD" in result


def test_render_missing_input_raises_skill_error():
    skill = load_skill("fit_summary")
    with pytest.raises(SkillError, match="missing required inputs"):
        skill.render(resume="only one input")


def test_render_preserves_template_content():
    skill = load_skill("format_resume")
    result = skill.render(resume="## EXPERIENCE\n- Did stuff")
    assert "## EXPERIENCE" in result
    assert "Did stuff" in result


# ---------------------------------------------------------------------------
# Escaped braces — Q{{n}} in questions skill
# ---------------------------------------------------------------------------

def test_questions_skill_escaped_braces():
    """Q{{n}} in the template should render as Q{n} after str.format."""
    skill = load_skill("questions")
    result = skill.render(
        count=5,
        stage="recruiter screen",
        job_description="JD text",
        resume="Resume text",
        role_intel="Strategy text",
        positioning_brief="Brief text",
        intel_section="",
        existing_questions="(none yet)",
    )
    # Q{{n}} in the source should produce Q{n} in the rendered output
    assert "Q{n}" in result


# ---------------------------------------------------------------------------
# All 16 skills load without error
# ---------------------------------------------------------------------------

ALL_SKILLS = [
    "role_intel",
    "resume_tailor",
    "profile_summary",
    "format_resume",
    "positioning_brief",
    "cover_letter",
    "email_inmail",
    "fit_summary",
    "interview_prep",
    "critique",
    "questions",
    "refine_resume",
    "refine_cover_letter",
    "refine_positioning_brief",
    "refine_email_inmail",
    "pdf_resume_cleanup",
]


@pytest.mark.parametrize("skill_name", ALL_SKILLS)
def test_all_skills_loadable(skill_name):
    skill = load_skill(skill_name)
    assert skill.name == skill_name
    assert skill.template, f"Skill '{skill_name}' has empty template"
    assert isinstance(skill.inputs, list)


# ---------------------------------------------------------------------------
# Output file mapping matches pipeline expectations
# ---------------------------------------------------------------------------

def test_output_file_mapping():
    expected = {
        "role_intel": "strategy.md",
        "resume_tailor": "resume.md",
        "format_resume": "resume.md",
        "positioning_brief": "positioning_brief.md",
        "cover_letter": "cover_letter.md",
        "email_inmail": "email_inmail.md",
        "fit_summary": "fit_summary.md",
    }
    for skill_name, expected_file in expected.items():
        skill = load_skill(skill_name)
        assert skill.output_file == expected_file, (
            f"Skill '{skill_name}': expected output_file={expected_file!r}, "
            f"got {skill.output_file!r}"
        )
