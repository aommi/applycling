---
name: profile_summary
description: Write a short tailored profile summary for a resume
inputs:
  - resume
  - job_description
---
You are writing a short profile summary for a resume tailored to a specific job.

Write 2-3 tight sentences (no bullet points) that:
- Position the candidate for this specific role using the job description's language.
- Highlight their most relevant experience and strengths.
- Sound natural and confident, not like a generic template.
- Reflect the candidate's ACTUAL experience level from the resume — do not echo back the JD's minimum requirements. If the candidate has 10+ years, say that. Never undersell by mirroring "5+ years" just because the JD asks for it.

Output ONLY the summary text. No heading, no preamble, no closing remarks.

=== RESUME ===
{resume}

=== JOB DESCRIPTION ===
{job_description}
