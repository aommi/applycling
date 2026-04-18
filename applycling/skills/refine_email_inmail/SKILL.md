---
name: refine_email_inmail
description: Refine an application email and LinkedIn InMail based on specific feedback
inputs:
  - feedback
  - email_inmail
  - role_intel
output_file: email_inmail.md
---
You are refining an application email and LinkedIn InMail based on specific feedback. Do NOT rewrite from scratch.

Apply ONLY the changes the feedback asks for. Keep everything else exactly as written.

**Rules:**
- Maintain both sections: ## Application email and ## LinkedIn InMail.
- No networking fluff. No "would love to pick your brain." Direct and specific.
- Output both sections. No preamble, no commentary.

=== FEEDBACK ===
{feedback}

=== EXISTING EMAIL + INMAIL ===
{email_inmail}

=== ROLE INTEL (for context) ===
{role_intel}
