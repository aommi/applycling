---
name: refine_positioning_brief
description: Update a positioning brief to reflect changes made to the tailored resume
inputs:
  - feedback
  - resume
  - brief
  - role_intel
output_file: positioning_brief.md
---
You are updating a positioning brief to reflect changes made to the tailored resume.

The resume has been refined. Update the positioning brief so it accurately describes the current resume — specifically the positioning decisions, application strength, and ATS score sections. Keep all sections that don't need updating exactly as they are.

**Rules:**
- Do not regenerate sections that are unaffected by the resume changes.
- Keep the same 6-section structure: Role summary, Positioning decisions, Application strength, Gap prep, ATS score (after).
- Update ATS score only if keywords changed.
- Output the full updated brief in the same Markdown format.

=== FEEDBACK APPLIED TO RESUME ===
{feedback}

=== UPDATED TAILORED RESUME ===
{resume}

=== EXISTING POSITIONING BRIEF ===
{brief}

=== ROLE INTEL (for context) ===
{role_intel}
