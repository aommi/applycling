"""Tests for the role-archetype tailoring pass.

The pass is a prompt-level capability: role_intel emits a "Role archetype &
vocabulary" section in its positioning strategy, and resume_tailor consumes it.
These tests assert the skills still render with their declared inputs (no broken
str.format braces) and that the new instructions are present.
"""

from __future__ import annotations

from applycling.skills.loader import load_skill


def test_role_intel_renders_with_archetype_section():
    skill = load_skill("role_intel")
    out = skill.render(
        job_description="Build merchant tools. Talk to merchants. Write code.",
        company_note="",
        candidate_section="",
    )
    assert "## Role archetype & vocabulary" in out
    assert "Primary user archetype" in out
    assert "Vocabulary map" in out
    assert "Builder signal" in out
    assert "Discovery signal" in out
    # The job description still interpolates.
    assert "Talk to merchants" in out


def test_resume_tailor_renders_with_archetype_rules():
    skill = load_skill("resume_tailor")
    out = skill.render(
        resume="## EXPERIENCE\n### PM — Acme\n- Did things.",
        job_description="Senior PM, commerce platform.",
        stories_section="",
        voice_tone_section="",
        never_fabricate_section="",
    )
    assert "Role archetype translation" in out
    assert "Builder signal" in out
    assert "Discovery signal" in out
    # Existing contract intact.
    assert "Reframe, don't rewrite" in out
    assert "## EXPERIENCE" in out
