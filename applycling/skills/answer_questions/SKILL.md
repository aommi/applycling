---
name: answer_questions
description: Draft answers to application form questions grounded in job context and applicant profile
inputs:
  - resume
  - stories
  - role_intel
  - company_context
  - positioning_brief
  - applicant_profile
  - questions
output_file: answers.md
---
You are helping a candidate complete a job application form. Draft a concise, honest answer for each question below. These are form fields, not essays — aim for 2–4 sentences per answer unless the question clearly calls for more.

**Rules:**
- Ground every answer in the candidate's resume, stories, and applicant profile. Do not invent experience.
- Tone should match the positioning brief — if it reads direct and outcome-focused, so should the answers.
- Use first person. No filler phrases like "I am passionate about" or "I am excited to."
- If a question asks for specific numbers or dates (e.g. notice period, start date, compensation), pull from the applicant profile if available.
- Format: output each answer under its question as a markdown heading:
  `### Question: <question text>`
  then the answer on the next line.
- If context is insufficient to answer a question, write: `[TODO: needs your input]` rather than guessing.

=== RESUME ===
{resume}

=== STORIES / EXPERIENCE HIGHLIGHTS ===
{stories}

=== ROLE INTEL ===
{role_intel}

=== COMPANY CONTEXT ===
{company_context}

=== POSITIONING BRIEF ===
{positioning_brief}
{applicant_profile}

=== QUESTIONS TO ANSWER ===
{questions}
