---
name: refine_cover_letter
description: Refine an already-written cover letter based on specific feedback without rewriting
inputs:
  - feedback
  - cover_letter
  - role_intel
output_file: cover_letter.md
---
You are refining an already-written cover letter based on specific feedback. Do NOT rewrite from scratch.

Apply ONLY the changes the feedback asks for. Every sentence not mentioned in the feedback must stay exactly as written.

**Rules:**
- Do not add a "Dear Hiring Manager" or sign-off — those are handled by the template.
- No em-dashes. No double hyphens. No filler openers ("I am writing to express...").
- Match the tone already established in the existing letter.
- Output ONLY the cover letter body. No preamble, no commentary.

=== FEEDBACK ===
{feedback}

=== EXISTING COVER LETTER ===
{cover_letter}

=== ROLE INTEL (for context) ===
{role_intel}
