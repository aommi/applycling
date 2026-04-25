---
name: email_inmail
description: Write a short application email and LinkedIn InMail for a job application
inputs:
  - role_intel
  - candidate_name
  - candidate_contact
  - job_title
  - company
  - voice_tone_section
  - applicant_profile_section
output_file: email_inmail.md
---
Write a short application email and a LinkedIn InMail for a job application.{voice_tone_section}

**Application email:**
- Subject line: [Role title] Application, [Candidate name]
- Body: 3 lines max. Reference resume and cover letter attached. Do not summarize the cover letter.
- Sign off with candidate name and contact info.

**LinkedIn InMail:**
- For direct outreach to a hiring manager or recruiter after applying.
- 3-4 sentences max. Why you match this specific role. Reference that you already applied.
- Be direct. No coffee chat ask. No "would love to pick your brain." No networking fluff.
- End with one concrete next step.

Output as two sections with headers:

## Application email
[subject and body]

## LinkedIn InMail
[message]

=== ROLE INTEL ===
{role_intel}

=== CANDIDATE NAME ===
{candidate_name}

=== CANDIDATE CONTACT ===
{candidate_contact}

=== JOB TITLE ===
{job_title}

=== COMPANY ===
{company}
{applicant_profile_section}