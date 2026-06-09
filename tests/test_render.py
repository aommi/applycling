"""Tests for the structured (OS-grade) resume renderer in applycling.render.

These cover the pure parse/HTML-build functions and the structured-vs-legacy
fallback gate. They deliberately avoid html_to_pdf (needs Chromium) and the
legacy markdown_to_html fallback body (needs python-markdown) so the suite runs
without optional rendering dependencies.
"""

from __future__ import annotations

from applycling import render


# A resume in the shape the pipeline assembles: profile header + ## PROFILE
# summary + standard sections, plus a tailoring-log comment to strip.
SAMPLE = """# Amirali Ommi

amirali.ommi@gmail.com · (604) 339-4347 · Vancouver, BC
linkedin.com/in/amiraliommi · github.com/aommi

## PROFILE

Senior Product Manager turning manual workflows into scalable systems.

## EXPERIENCE

### Product Manager, Digital Merchandising — MEC (Mountain Equipment Company)
*Vancouver · May 2024 – Feb 2026*

- Drove **~20% lift in add-to-cart** by automating curated merchandising.
- Cut product-launch backlog ~90% while scaling to ~10,000 live styles.

### Product Manager, CRM & Marketing Analytics — Nomatec Software Company
*Tehran · Oct 2012 – Jun 2016*

- Built a 0->1 cloud CRM with marketing analytics.

## SELECTED PROJECTS

### ApplyCling (Current)
Messaging-first AI agent for job seekers.
[github.com/aommi/applycling](https://github.com/aommi/applycling) · applycling.com

## SKILLS

**Product:** Product Strategy · Roadmapping · Discovery

## EDUCATION

### M.Sc., Systems Engineering — Concordia University
*Montreal · 2016–2019*
Thesis on staffing design teams.

<!-- TAILORING LOG
- Renamed nothing.
-->
"""


def test_parse_extracts_header_and_summary():
    model = render._parse_resume(SAMPLE)
    assert model["name"] == "Amirali Ommi"
    assert any("amirali.ommi@gmail.com" in c for c in model["contact"])
    # ## PROFILE body becomes the summary.
    assert "scalable systems" in model["summary"]


def test_parse_roles_with_dates_and_bullets():
    model = render._parse_resume(SAMPLE)
    exp = next(s for s in model["sections"] if s["kind"] == "experience")
    assert len(exp["roles"]) == 2
    first = exp["roles"][0]
    assert first["role"] == "Product Manager, Digital Merchandising"
    assert first["company"] == "MEC (Mountain Equipment Company)"
    assert first["location"] == "Vancouver"
    assert first["dates"] == "May 2024 – Feb 2026"
    assert len(first["bullets"]) == 2


def test_parse_skills_and_education_and_projects():
    model = render._parse_resume(SAMPLE)
    kinds = [s["kind"] for s in model["sections"]]
    assert kinds == ["experience", "projects", "skills", "education"]

    skills = next(s for s in model["sections"] if s["kind"] == "skills")
    assert skills["skills"][0]["label"] == "Product"

    projects = next(s for s in model["sections"] if s["kind"] == "projects")
    assert projects["projects"][0]["name"] == "ApplyCling (Current)"
    assert "github.com/aommi/applycling" in projects["projects"][0]["links"]

    edu = next(s for s in model["sections"] if s["kind"] == "education")
    assert edu["items"][0]["degree"] == "M.Sc., Systems Engineering"
    assert edu["items"][0]["school"] == "Concordia University"


def test_project_bullets_render_as_list_not_flattened():
    # A project bullet must become a real <li>, not get joined into the
    # description paragraph (regression from the Shopify PDF).
    src = """# Jane Doe

jane@example.com

## EXPERIENCE

### Engineer — Acme
*City · 2018 – 2024*

- Shipped features.

## SELECTED PROJECTS

### ApplyCling (Current)
Messaging-first AI agent.
- Built with an agentic stack including MCP and Claude Code.
[github.com/aommi/applycling](https://github.com/aommi/applycling)
"""
    model = render._parse_resume(src)
    proj = next(s for s in model["sections"] if s["kind"] == "projects")["projects"][0]
    assert proj["description"] == "Messaging-first AI agent."
    assert proj["bullets"] == ["Built with an agentic stack including MCP and Claude Code."]
    html = render._structured_resume_html(src)
    assert "<li>Built with an agentic stack including MCP and Claude Code.</li>" in html
    # the bullet text must not be flattened into the description
    assert "- Built" not in html


def test_wrapped_bullet_continuation_is_kept():
    # A bullet split across two source lines must keep its continuation text.
    src = """# Jane Doe

jane@example.com

## EXPERIENCE

### Engineer — Acme
*City · 2018 – 2024*

- Led a large cross-functional initiative
  that shipped a new billing platform end to end.
"""
    model = render._parse_resume(src)
    role = next(s for s in model["sections"] if s["kind"] == "experience")["roles"][0]
    assert role["bullets"] == [
        "Led a large cross-functional initiative that shipped a new billing platform end to end."
    ]


def test_structured_html_has_semantic_markup():
    html = render._structured_resume_html(SAMPLE, title="Test")
    assert html is not None
    assert html.startswith("<!DOCTYPE html>")
    # right-aligned dates, company accent, skills grid, education block
    assert 'class="role-dates"' in html
    assert "May 2024 – Feb 2026" in html
    assert 'class="company"' in html
    assert '<span class="role-title">Product Manager, Digital Merchandising</span><span class="company">MEC' in html
    assert 'class="skills"' in html
    assert 'class="education-title"' in html
    # bold markdown becomes <strong>, not literal **
    assert "<strong>~20% lift in add-to-cart</strong>" in html
    assert "**" not in html
    # markdown link becomes an anchor
    assert '<a href="https://github.com/aommi/applycling">' in html


def test_tailoring_log_is_stripped():
    html = render._structured_resume_html(SAMPLE, title="Test")
    assert "TAILORING LOG" not in html
    assert "Renamed nothing" not in html


def test_section_order_is_preserved():
    # Education before experience in the source should render in that order.
    src = """# Jane Doe

jane@example.com

## EDUCATION

### B.Sc., CS — Some University
*City · 2014–2018*

## EXPERIENCE

### Engineer — Acme
*City · 2018 – 2024*

- Did things.
"""
    model = render._parse_resume(src)
    assert [s["kind"] for s in model["sections"]] == ["education", "experience"]
    html = render._structured_resume_html(src)
    assert html.index("EDUCATION") < html.index("EXPERIENCE")


def test_unrecognized_section_renders_generically():
    src = """# Jane Doe

jane@example.com

## EXPERIENCE

### Engineer — Acme
*City · 2018 – 2024*

- Shipped features.

## CERTIFICATIONS

- AWS Solutions Architect
- PMP
"""
    html = render._structured_resume_html(src)
    assert html is not None
    assert "CERTIFICATIONS" in html
    assert "AWS Solutions Architect" in html


def test_education_as_bold_lines_is_not_dropped():
    # Regression: education written as **bold** lines (not ### headings) must
    # still render, not silently vanish.
    src = """# Jane Doe

jane@example.com

## EXPERIENCE

### Engineer — Acme
*City · 2018 – 2024*

- Shipped features.

## EDUCATION
**M.Sc., Systems Engineering — Concordia University** · Montreal · 2016–2019
**B.Eng., Management Systems Engineering — Amirkabir University of Technology** · Tehran · 2008–2012
"""
    html = render._structured_resume_html(src)
    assert html is not None
    assert "Concordia University" in html
    assert "Amirkabir University of Technology" in html


def test_non_resume_input_falls_back_to_none():
    # A cover letter has no experience roles -> structured renderer declines.
    cover = """# Dear Hiring Manager

I am excited to apply for the Product Manager role at your company.

I bring a decade of experience building products.

Sincerely,
Amirali
"""
    assert render._structured_resume_html(cover) is None


def test_resume_html_uses_structured_path_for_resume():
    html = render._resume_html(SAMPLE, title="Test")
    assert 'class="role-dates"' in html  # structured markup, not legacy
