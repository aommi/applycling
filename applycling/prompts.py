"""LLM prompt templates."""

TAILOR_RESUME_PROMPT = """You are an expert resume editor helping a job seeker tailor their resume to a specific job description.

Rewrite the resume below so that it speaks directly to the job description. Concretely:
- Mirror the job description's language, keywords, and priorities where the candidate honestly has the experience.
- Reorder and rewrite bullet points to lead with the most relevant accomplishments first.
- Quantify impact whenever the original resume gives you the numbers to do so.
- Do NOT invent experience, skills, employers, dates, or metrics that are not in the original resume.
- Preserve the candidate's overall structure (sections, employers, dates).

Output ONLY the tailored resume in clean Markdown. No preamble, no explanation, no closing remarks.

=== BASE RESUME ===
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
