---
name: Pipeline Step Map
description: All steps in cli.py add command with line numbers, I/O, checkpoint status, and backend type
type: project
---

Mapped from cli.py `add` command (lines 530–977). Step names match _Step("name", ...) calls.

## Steps in Execution Order

| # | Step Name | Lines | Backend | Inputs | Output File | Checkpoint? | Error Mode |
|---|-----------|-------|---------|--------|-------------|-------------|------------|
| 1 | job_scraping | 564–591 | scrape (Playwright + JSON-LD + LLM fallback) | url | job.json (via package.assemble) | no | yellow + fallback to manual |
| 2 | company_fetch | 614–622 | scrape (Playwright, no LLM) | company_url | company_context.md (via assemble) | no | yellow + skip |
| 3 | role_intel | 624–671 | LLM | job_description, company_page_text, base_resume | strategy.md | YES — angle + gap review | red (critical) |
| 4 | resume_tailor | 673–709 | LLM | base_resume, job_description, strategy, stories, linkedin_profile | resume.md | no | red (critical) |
| 5 | profile_summary | 713–724 | LLM | base_resume, job_description | (injected into resume.md) | no | yellow + skip |
| 6 | format_resume | 727–735 | LLM | tailored_body | resume.md | no | yellow + fallback to unformatted |
| 7 | positioning_brief | 747–758 | LLM | strategy, tailored, job_description | positioning_brief.md | no | red (critical) |
| 8 | cover_letter | 760–777 | LLM | strategy, tailored, job_description | cover_letter.md | no | yellow + skip |
| 9 | email_inmail | 779–803 | LLM | strategy, profile, title, company | email_inmail.md | no | yellow + skip |
| 10 | fit_summary | 806–817 | LLM | base_resume, job_description | fit_summary.md | no | red (critical) |
| 11 | package_assemble | 879–901 | pure transform (render.py + package.py) | all above | full folder (md/html/pdf) | no | red (critical) |

ATS score is NOT a step — it's a regex extraction from strategy output at line 948, used only for display hint.

## Checkpoints Detail

### Checkpoint 1: Angle (lines 654–660, inside role_intel review block)
- Trigger: `review_mode == "interactive"` 
- Gate: extracts `## Identified niche` section from strategy, asks user if angle feels right
- Override: if user types anything other than "looks good/yes/y/good/", appends `## Candidate override` to strategy
- Async behavior: skipped entirely (`console.print("[dim]Async mode — auto-proceeding.[/dim]")`)

### Checkpoint 2: Gap (lines 662–666, inside role_intel review block)
- Trigger: gaps found in strategy AND `review_mode == "interactive"`
- Gate: shows `## Tooling or domain gaps`, asks bridge/deprioritise/other
- Override: appends `## Gap handling\nCandidate chose: {gap_action}` to strategy
- Async behavior: skipped entirely

### Checkpoint 3: Strategy edit (lines 668–669)
- Trigger: user chooses "edit" at "Proceed to resume tailoring?"
- Gate: full strategy text is editable in multiline paste
- Async behavior: skipped entirely

## Pre-pipeline Interactive Gates (NOT checkpoints in pipeline sense)

- Line 559: URL prompt (if not --url and not async)
- Line 581–586: title/company/company_url confirmation after scrape (interactive only)
- Line 607–609: "Include a profile summary section?" (interactive default y; async defaults to True)
- Lines 596–601: manual JD entry fallback (if no URL)

## Data Flow Summary

```
URL → [scrape] → {title, company, job_description, company_url}
company_url → [company_fetch] → company_page_text
{job_description, company_page_text, base_resume} → [role_intel] → strategy
strategy + [CHECKPOINT: angle, gap] → modified strategy
{base_resume, job_description, strategy, stories, linkedin_profile} → [resume_tailor] → tailored_body
{base_resume, job_description} → [profile_summary] → profile_summary (optional)
tailored_body → [format_resume] → formatted_body
{profile_header + profile_summary + formatted_body} → tailored (assembled resume)
{strategy, tailored, job_description} → [positioning_brief] → pos_brief
{strategy, tailored, job_description} → [cover_letter] → cover_letter_text
{strategy, profile, title, company} → [email_inmail] → email_inmail_text
{base_resume, job_description} → [fit_summary] → fit_summary
{all above} → [package_assemble] → output folder (md/html/pdf)
```
