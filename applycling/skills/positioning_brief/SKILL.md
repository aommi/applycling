---
name: positioning_brief
description: Write a positioning brief document for interview prep from role intel and tailored resume
inputs:
  - role_intel
  - tailored_resume
  - job_description
output_file: positioning_brief.md
---
You are writing a positioning brief for a job application. This document is used by the candidate to prepare for interviews and understand the strategy behind their tailored resume.

You have the role intel, the tailored resume, and the tailoring log. Use all of them.

Produce a Markdown document with EXACTLY these sections:

## Role summary
Keep it brief: what's unique about this role and the identified niche (1-2 sentences).

## Positioning decisions
- The niche and angle chosen, and why.
- Top 3-4 tailoring decisions: what was moved, reframed, compressed, or led, and why.
- Any job titles renamed and why (from the tailoring log).
- Any stories/experiences pulled from candidate stories and why.
- What was deliberately deprioritised and why.

## Application strength
3 strongest specific reasons this company should call. Not generic. Tied to this role and company.

## Gap prep
1-2 honest gaps identified. For each, a suggested bridge answer: what to say in the interview when it comes up. Be concrete.

## ATS score (after)
Recalculate keyword coverage based on the finalised resume. Score out of 100. Show before and after.

Keep it short. This is a reference doc to scan before an interview, not a report.

=== ROLE INTEL ===
{role_intel}

=== TAILORED RESUME ===
{tailored_resume}

=== JOB DESCRIPTION ===
{job_description}
