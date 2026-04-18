---
name: cover_letter
description: Write a tailored cover letter matching the candidate's voice and positioning strategy
inputs:
  - role_intel
  - tailored_resume
  - job_description
  - voice_tone_section
output_file: cover_letter.md
---
You are writing a cover letter for a job application. Write like the candidate, not a template.{voice_tone_section}

You have the role intel (with company signal) and the tailored resume. Use both.

**Structure (5 short paragraphs, each with one job):**
1. Hook: something specific about the company not found in the JD. Shows research. One or two sentences.
2. Differentiator: the one thing that makes this candidate non-obvious for this role. Not their strongest skill, but their unique angle.
3. Evidence: 2-3 outcomes mapped directly to the 20% signal from role intel. Specific, quantified. Scan the entire resume — pick the strongest matches regardless of which role they came from. Do NOT default to the most recent role.
4. How they work: prototyping speed, cross-functional approach, starts with the customer problem. One short paragraph.
5. Close: one sentence. No fluff. No "I look forward to the opportunity."

**Rules:**
- 4-5 short paragraphs total. If a paragraph has two jobs, split or cut.
- No em-dashes. No double hyphens.
- Match the company's tone from the role intel company signal section.
- Must read like the candidate wrote it, not a template.
- No filler opener. No "I am writing to express my interest in."
- No "passionate about", "excited to", "thrilled by."

Output ONLY the cover letter text. No heading, no "Dear Hiring Manager" (that's added by the template). No sign-off.

=== ROLE INTEL ===
{role_intel}

=== TAILORED RESUME ===
{tailored_resume}

=== JOB DESCRIPTION ===
{job_description}
