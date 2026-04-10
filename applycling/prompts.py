"""LLM prompt templates."""

TAILOR_RESUME_PROMPT = """You are an expert resume editor helping a job seeker tailor their resume to a specific job description.

Rewrite the resume below so that it speaks directly to the job description. Concretely:
- Mirror the job description's language, keywords, and priorities where the candidate honestly has the experience.
- Reorder and rewrite bullet points to lead with the most relevant accomplishments first.
- Quantify impact whenever the original resume gives you the numbers to do so.
- Do NOT invent experience, skills, employers, dates, or metrics that are not in the original resume.
- Preserve the candidate's overall structure (sections, employers, dates).
- Do NOT include a name, contact info, or profile summary section — those are handled separately.{context_section}

Output ONLY the tailored resume body in clean Markdown, starting from the first section header (e.g. ## Experience). No preamble, no explanation, no closing remarks.

=== BASE RESUME ===
{resume}

=== JOB DESCRIPTION ===
{job_description}
"""

PROFILE_SUMMARY_PROMPT = """You are writing a short profile summary for a resume tailored to a specific job.

Write 2-3 tight sentences (no bullet points) that:
- Position the candidate for this specific role using the job description's language.
- Highlight their most relevant experience and strengths.
- Sound natural and confident, not like a generic template.

Output ONLY the summary text. No heading, no preamble, no closing remarks.

=== RESUME ===
{resume}

=== JOB DESCRIPTION ===
{job_description}
"""


FIT_SUMMARY_PROMPT = """You are a sharp, honest friend reviewing a job application for someone you want to see succeed.

Given the resume and job description below, write a 2-3 sentence fit summary covering:
1. Where the candidate is a strong match.
2. What they should emphasize in their application or interview.
3. Any notable gaps they should be ready to address.

Be direct and specific. No hedging, no filler, no bullet lists — just 2-3 tight sentences.

=== RESUME ===
{resume}

=== JOB DESCRIPTION ===
{job_description}
"""


ROLE_ANALYST_PROMPT = """You are a strategic career advisor. Your job is to help a candidate cut through the noise in a job description and figure out exactly how to position themselves.

Most job descriptions are 70-80% boilerplate. Your task is to find the 20-30% that actually differentiates this role and build a concrete positioning strategy from it.{company_section}

Produce a Markdown document with EXACTLY these three sections — no extra sections, no preamble:

## What makes this role unique
Bullet points identifying: team or product area, core objective or mission, specific experience signals that stand out from the template, anything non-obvious in the JD that a careful reader would notice.

## Positioning strategy
2-4 sentences on how to frame the candidate for THIS specific role — which angle to lead with, what to emphasise, any gaps to reframe or pre-empt.

## Key signals for the resume
Bullet points: specific language, keywords, and framings this company/team responds to; experiences or metrics to surface; anything to de-emphasise.

=== JOB DESCRIPTION ===
{job_description}
"""

COMPANY_CONTEXT_PROMPT = """You are extracting key information about a company from their website or LinkedIn page.

Extract the following and return a short Markdown document:

## Company overview
One or two sentences: what the company does and who it serves.

## Domain and industry
What space are they in?

## Product focus
Main product(s) or service(s) — be specific, not generic.

## Stage and scale
Size, funding stage, or growth phase if inferable.

## Cultural or technical signals
Any notable signals about how they work, what they value, or their tech approach.

Be factual and concise. If something is not inferable from the page, omit it.

=== PAGE TEXT ===
{page_text}
"""

PDF_RESUME_CLEANUP_PROMPT = """You are an expert at converting messy PDF-extracted resume text into clean Markdown.

The text below was extracted from a PDF resume using a text extraction library. It may have:
- Lost line breaks (multiple bullet points joined into one line)
- Lost section headers (sections run into each other)
- Lost spacing between dates, titles, and companies
- Page numbers, headers, or footers that should be removed
- Garbled bullet characters

Reconstruct it into a clean, well-structured Markdown resume. Concretely:
- Use # for the candidate's name (top of resume)
- Use ## for major sections (Experience, Education, Skills, etc.)
- Use ### for individual roles or degrees, with company and dates
- Use - for bullet points under each role
- Preserve every fact: do not invent, summarize, or drop any content
- Do not add any preamble, explanation, or commentary

Output ONLY the cleaned Markdown.

=== EXTRACTED TEXT ===
{extracted_text}
"""
