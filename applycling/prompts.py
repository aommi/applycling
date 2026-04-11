"""LLM prompt templates."""

TAILOR_RESUME_PROMPT = """You are an expert resume editor. You write in active voice, outcome-first.{voice_tone_section}

Rewrite the resume below so that it speaks directly to the job description. Follow these rules strictly:

**Recruiter-first constraints (non-negotiable):**
- First bullet of the top role: the single strongest quantified outcome relevant to this role.
- Domain relevance must appear in the top third of the page.
- Every bullet leads with the outcome, not the activity. Active voice only.
- Compress less-relevant roles to 1-2 bullets. Never remove roles entirely.
- Skills section: only include skills evidenced in experience or called out in the positioning strategy.

**Tailoring rules:**
- Mirror the JD's language, keywords, and priorities where the candidate honestly has the experience.
- Use the ATS keyword table from the positioning strategy as a checklist. Every keyword marked "weave in" must appear somewhere. Only integrate where the experience genuinely supports it.
- You MAY rename job titles if it better reflects the actual work and fits the role. Keep it honest.
- You MAY reorder sections to put the most relevant experience first.
- Quantify impact whenever the original resume gives you the numbers.

**Hard boundaries:**
- Do NOT invent experience, skills, employers, dates, or metrics not in the original resume or candidate stories.{never_fabricate_section}
- Do NOT include a name, contact info, or profile summary section. Those are handled separately.
- No filler: no "passionate about", "dynamic", "collaborated with", "helped to".
- No em-dashes. No double hyphens. Use commas, semicolons, or break into two sentences.{stories_section}

**Transparency (you MUST report these at the very end, after the resume):**
After the resume markdown, add a section starting with `<!-- TAILORING LOG` that lists:
- Any job titles you renamed and why
- Any stories/experiences you pulled from candidate stories
- Any sections you reordered and why
End with `-->` so it's hidden in rendered output but visible in the markdown source.

Output the tailored resume body in clean Markdown, starting from the first section header (e.g. ## Experience). Then the tailoring log.

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

POSITIONING_BRIEF_PROMPT = """You are writing a positioning brief for a job application. This document is used by the candidate to prepare for interviews and understand the strategy behind their tailored resume.

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
"""


ROLE_INTEL_PROMPT = """You are a strategic career advisor. Your job is to cut through the noise in a job description and build a concrete positioning strategy.

Most job descriptions are 70-80% boilerplate. Find the 20-30% that reveals what the team actually cares about, then build a strategy from it.{candidate_section}

Produce a Markdown document with EXACTLY these sections. No preamble, no extra sections.

## The real 20%
The signal that reveals what this team actually cares about: specific tools, domain focus, how they work, the problem they are hiring to solve. Not the requirements list. Max 6 bullets.

## The 80% (treat as context, not instruction)
Template language that should not drive resume content. Note: this is an analytical lens for emphasis and ordering, not a rule to remove content.

## Company signal
How they describe themselves, their tone, their stage, their customer. One short paragraph.{company_note}

## Identified niche
One sentence. The specific angle the candidate should lead with for this role, based on the 20% signal.

## ATS keyword match
Top 10-12 keywords and hard skills from the JD (specific tools, technologies, domain terms, role-specific verbs). For each, note coverage:

| Keyword | In resume? | Action |
|---------|------------|--------|
| [keyword] | Yes / Partial / No | Keep / Weave in naturally / Flag as gap |

## ATS match score (before)
A score out of 100 reflecting how well the current base resume covers the JD keywords. Be honest.

## Tooling or domain gaps
Explicit gaps. These go into the positioning brief, not hidden. If no gaps, say so.

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
