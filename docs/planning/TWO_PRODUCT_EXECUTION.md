# Two-Product Strategy — Execution Plan

## Architecture

```
applycling/                         ← PUBLIC repo (open source)
│
├── skills/                         ← Fat: judgment, policy, LLM prompts
│   ├── applycling/SKILL.md         ← Pipeline orchestrator (NEW)
│   ├── cover_letter/SKILL.md
│   ├── resume_tailor/SKILL.md
│   ├── fit_summary/SKILL.md
│   ├── ... (all 17 content skills)
│   └── applycling/SKILL.md
│
├── tools/                          ← Sharp: deterministic, repeatable
│   ├── scrape_url                  ← curl + readability → clean job text
│   ├── clean_llm_output            ← strip code fences, preamble, sign-offs
│   ├── render_package              ← pandoc → PDFs
│   └── assemble_package            ← mkdir, name files, build folder tree
│
├── scripts/setup.sh                ← one-command install
├── README.md
├── LICENSE                         ← MIT
├── .gitignore
└── eval/                           ← eval gate: 20 URL test suite
    ├── urls.txt
    ├── run.sh
    └── criteria.md

applycling-workbench/               ← PRIVATE repo (SaaS)
│
├── applycling_workbench/
│   ├── ui/                         ← FastAPI, templates, auth
│   ├── tracker/                    ← Postgres, SQLite
│   ├── jobs_service.py             ← multi-job orchestration
│   └── analytics.py
├── docker-compose.yml
├── Dockerfile
├── migrations/
└── pyproject.toml                  ← depends on same tools, runs same skills
```

## Design Principle

| If the step needs... | Make it a... |
|---|---|
| Judgment, synthesis, adaptation, user-context interpretation | **Skill** (markdown) |
| Repeatability, filenames, schemas, PDFs, JSON, idempotency, external process behavior | **Tool** (deterministic script) |
| Coordination of judgment + deterministic work | **Orchestrator skill** (markdown) |

The orchestrator skill describes WHAT to do and WHEN. The tools do the mechanical work. The agent runtime calls tools when the skill says to.

## Phase 1: Write the orchestrator skill and tools (2-3 hours)

### 1a. Write `skills/applycling/SKILL.md`

The pipeline orchestrator. ~100 lines. Describes:
- Input: job URL, user profile path, resume path
- Sequence: scrape → role_intel → resume_tailor → cover_letter → fit_summary → positioning_brief → email_inmail → critique → clean → render → assemble
- Branching: "if user asked for resume only, skip cover letter, fit summary, and email"
- Retry: "if any LLM step fails (empty output, error), retry once. If it fails again, skip with a warning in the package notes"
- Output: a directory with named files (resume.pdf, cover_letter.pdf, package_notes.md, etc.)
- Profile handling: "read profile.json from ~/.applycling/. Validate it has name, experience, education. If missing, ask the user."
- Never-fabricate rule: "the candidate's actual experience comes from resume.md. Skills generate content from resume.md. Never invent experience."

### 1b. Write deterministic tools

`tools/scrape_url`:
```bash
#!/bin/bash
# Input: URL
# Output: job.md in current directory
# Uses curl + readability extraction
# Handles: Lever, Greenhouse, Workday, generic job pages
```

`tools/clean_llm_output`:
```bash
#!/bin/bash
# Input: raw LLM output on stdin
# Output: cleaned markdown on stdout
# Strips: code fences, preamble markers, trailing sign-offs
```

`tools/render_package`:
```bash
#!/bin/bash
# Input: directory of markdown files
# Output: PDFs alongside markdown files
# Uses: pandoc + applycling LaTeX template
```

`tools/assemble_package`:
```bash
#!/bin/bash
# Input: working directory with generated files
# Output: dated, named package directory under ~/applycling/jobs/
# e.g., ~/applycling/jobs/stripe-pm-2026-05-06/
```

### 1c. Write `scripts/setup.sh`

One command: `curl -sSL https://raw.githubusercontent.com/amirali/applycling/main/scripts/setup.sh | bash`

- Clones repo to `~/.applycling/`
- Symlinks skills into `~/.hermes/skills/applycling/`
- Installs pandoc, wkhtmltopdf, curl
- Creates `~/.applycling/profile.json` template
- Validates with a dry run

### 1d. Write README

Includes the pitch, quick start, architecture diagram, FAQ about Workbench.

## Phase 2: Eval gate

Two audiences, two purposes.

### 2a. Author gate (you, before publishing)

Run 20 real URLs through Hermes. If the orchestrator skill is flaky (skips steps, invents file names, fails retries), don't ship it. Fix the skill or fall back to a thin Python orchestrator. This is a one-time architecture validation — pass it once, move on.

### 2b. User gate (them, after setup)

`scripts/validate.sh` — a 30-second check that runs one URL and confirms:
- Job was scraped (job.md exists, non-empty)
- Package was assembled (all expected files present)
- PDFs rendered (non-zero, openable)
- No obvious hallucinations (grep for "at my previous role at [company they never worked at]")

User sees a green check or a red X with a specific error ("scraper failed — the job page might use JavaScript; try pasting the text manually"). This is not a comprehensive test — it's a smoke test so they know their setup works before they run 10 real applications through it.

### 2c. Success criteria (author gate)

`eval/criteria.md`:

| Criterion | Threshold |
|-----------|-----------|
| Package completeness | All files present in 18/20 runs |
| File naming | Consistent format (company-role-date) in 20/20 runs |
| PDF success | PDFs render without error in 19/20 runs |
| Retry behavior | Failed LLM step retries once, skips with warning in 5/5 simulated failures |
| Profile validation | Missing profile triggers user prompt, not silent failure |
| Never-fabricate | 0 hallucinated experiences in 20/20 spot checks |
| User intervention | ≤1 manual intervention per run on average |

### 2d. Decision

- **Pass**: ship the agent-native repo, keep Workbench as SaaS wrapper.
- **Fail on specific tools** (e.g., scrape_url unreliable): fix the tool, re-run.
- **Fail on orchestrator inconsistency** (e.g., agent skips steps, improvises file names): fall back to thin Python orchestrator that calls the same tools. Still ship the skills as-is. The orchestrator becomes `applycling/orchestrator.py` (~200 lines, deterministic), not an agent skill.

## Phase 3: Wire Workbench (1 hour)

After the eval gate passes:

1. Workbench's `jobs_service.py` can either:
   - Shell out to the public tools and call skills directly (same sequence as the agent)
   - Have its own thin orchestrator that reads the public skill + tools
2. Add `README.md` link: "Want the free agent-native version?"

## Phase 4: Ship (1 hour)

- Push `applycling` to public GitHub
- Announce on X/LinkedIn
- Add link from Workbench landing page

## Disk Layout After

```
/Users/amirali/Documents/dev/
├── applycling/                  ← PUBLIC (open source)
│   ├── skills/
│   ├── tools/
│   ├── eval/
│   ├── scripts/setup.sh
│   └── README.md
│
├── applycling-workbench/        ← PRIVATE (SaaS)
│   ├── applycling_workbench/
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── ...
│
└── product sense/               ← unrelated
```

The current SaaS repo at `/Users/amirali/Documents/dev/applycling/` gets renamed to `applycling-workbench/`. The public repo takes the `applycling` name.

## Risks

1. **Orchestrator skill flakiness.** If the agent improvises file names or skips steps, the eval gate catches it. Fallback: thin Python orchestrator.
2. **Scraper reliability.** Real job pages are messy. If curl+readability fails on >20% of URLs, invest in Playwright-based scraper.
3. **OSS maintenance burden.** Issues, PRs, contributions. This is also the upside.
