---
name: refine_resume
description: Refine an already-tailored resume based on specific feedback without starting over
inputs:
  - feedback
  - resume
  - job_description
output_file: resume.md
---
You are refining an already-tailored resume based on specific feedback. Do NOT start from scratch.

Apply ONLY the changes implied by the feedback. Every bullet, role, and section that is not mentioned in the feedback must stay exactly as written. Preserve all keywords, quantified results, and framing choices that are not explicitly targeted.

**Rules:**
- Make only the changes the feedback asks for.
- Do not "improve" unrelated sections while you're in there.
- Do not include a name, contact info, or profile summary — those are added separately.
- No em-dashes. No double hyphens. No filler ("passionate about", "dynamic", etc.).
- Maintain reverse chronological order within sections.
- Output ONLY the resume body markdown. No preamble, no commentary, no tailoring log.

=== FEEDBACK ===
{feedback}

=== EXISTING TAILORED RESUME ===
{resume}

=== JOB DESCRIPTION (for context — do not re-tailor from scratch) ===
{job_description}
