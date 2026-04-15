# applycling

> Your clingy job-search companion. We won't leave you alone until you land your next role.

A CLI that tailors your resume, writes cover letters, and builds complete application packages for each job you apply to. Supports **local Ollama models**, **Anthropic (Claude)**, and **Google AI Studio (Gemini)**.

---

## What it does

For each job URL you provide, applycling:

1. **Scrapes the job posting** (structured data first, LLM fallback) and optionally the company page.
2. **Runs Role Intel** — extracts the unique 20% signal from the JD, identifies the niche, scores ATS keyword coverage, flags gaps.
3. **Tailors your resume** — recruiter-first, outcome-first, ATS-optimized. Uses your voice/tone and draws from your stories file when relevant.
4. **Writes a cover letter** — 5-paragraph structure matched to the company's tone.
5. **Drafts an application email and LinkedIn InMail** — direct, no fluff.
6. **Generates a positioning brief** — your interview prep: positioning decisions, application strength, gap prep with bridge answers, ATS before/after score.
7. **Assembles a package** — resume (md/html/pdf), cover letter (md/html/pdf), positioning brief, email/InMail, strategy, all in one folder.
8. **Tracks everything** — in Notion (recommended) or local SQLite.

---

## Prerequisites

- **Python 3.10+**
- **One of these LLM providers:**
  - **[Ollama](https://ollama.com)** (local, free) — install and pull a model: `ollama pull llama3.2`
  - **Anthropic API key** — for Claude models
  - **OpenAI API key** — for GPT-4o and o-series models
  - **Google AI Studio API key** — for Gemini models

---

## Install

```bash
cd /path/to/applycling
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

For API providers, create a `.env` file in the project root:

```bash
# .env (gitignored — never committed)
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=AIza...
```

---

## First-time setup

```bash
applycling setup
```

This walks you through:

1. **Pick an Ollama model** from your installed models.
2. **Import your base resume** — from PDF or paste (keeps existing resume if already set up).
3. **Personal details** — name, email, phone, location, LinkedIn, GitHub. Used verbatim in every resume, never rewritten by AI.
4. **Voice and tone** — how you want your resume and cover letter to sound (e.g. "Direct, active voice, outcome-first").
5. **Never fabricate** — hard boundaries on what the LLM must never invent.
6. **Output settings** — whether to generate `run_log.json` (timing, tokens, cost per run) and `.docx` files.
7. **Stories** — optional extra experiences the tailorer can draw from. Preview or edit if already set.
8. **Playwright browsers** — installed automatically for PDF rendering.

Re-running `applycling setup` at any time will pre-fill all existing values so you only need to update what changed.

To use a cloud provider instead of Ollama, edit `data/config.json` after setup:

```json
{
  "provider": "anthropic",
  "model": "claude-haiku-4-5-20251001"
}
```

Valid providers: `ollama`, `anthropic`, `openai`, `google`.

---

## Commands

### `applycling add [--async] [--url URL] [--model MODEL] [--provider PROVIDER]`

Add a job and generate the full application package.

```bash
applycling add                                         # interactive mode (default)
applycling add --async                                 # skip input gates, generate everything
applycling add --url "https://..." --async             # fully non-interactive, no prompts
applycling add --url "https://..." --model gemma4:27b  # override model for this run
applycling add --url "https://..." \
  --model claude-sonnet-4-6 \
  --provider anthropic                                 # override both model and provider
```

**Interactive mode** asks you to confirm the positioning angle and gap handling before writing the resume. **Async mode** generates the full package without stopping — review the output later.

`--model` and `--provider` override `config.json` for a single run without changing your default. Useful for benchmarking models or using a stronger model for important applications.

The flow:
1. Provide a job URL (or enter details manually)
2. Role Intel runs and shows findings
3. You confirm angle + gap handling (interactive) or auto-proceed (async)
4. Resume, cover letter, email/InMail, positioning brief generated
5. Package assembled and tracked

### `applycling refine <job_id> [--only ARTIFACTS] [--cascade] [-f FEEDBACK] [--model MODEL] [--provider PROVIDER]`

Iterate on an existing application package with feedback, without re-running the full pipeline.

```bash
applycling refine job_015                                      # prompts for feedback, refines all artifacts
applycling refine job_015 -f "tighten the EA bullets"          # refine all artifacts with this feedback
applycling refine job_015 --only resume -f "lead with data platform work"   # resume only, no cascade
applycling refine job_015 --only resume --cascade -f "..."     # resume + downstream (brief, cover letter, email)
applycling refine job_015 --only cover-letter -f "paragraph 3 is too generic"
applycling refine job_015 --model claude-sonnet-4-6 --provider anthropic -f "..."
```

`--only` accepts comma-separated artifact names: `resume`, `cover-letter` (aliases: `cl`), `brief` (alias: `positioning-brief`), `email` (alias: `inmail`).

Each refine run archives the previous artifacts to a `v1/`, `v2/`, ... subfolder before writing new ones, so nothing is ever lost.

**Cascade behaviour:**
- No `--only`: all artifacts that exist are regenerated (cascade not needed).
- `--only` without `--cascade`: only the specified artifacts are regenerated.
- `--only` with `--cascade`: specified artifacts + their downstream dependencies (resume → brief, cover letter, email; cover letter → email).

### `applycling prep <job_id> [--stage STAGE] [--model MODEL] [--provider PROVIDER]`

Generate stage-specific interview prep for a job. Run this when you get the interview call — not part of `applycling add`.

```bash
applycling prep job_015                        # all 4 stages
applycling prep job_015 --stage recruiter      # recruiter screen only
applycling prep job_015 --stage hiring-manager
applycling prep job_015 --stage technical
applycling prep job_015 --stage executive
```

For each stage, generates:
- **Likely questions** — 5-7 questions tied to this specific JD and the candidate's gaps
- **Talk tracks** — a suggested answer for each question using a real example from the resume
- **"Why me" narrative** — tailored to what that specific interviewer cares about

**Prep works without any intel** — resume, JD, and role intel are enough to generate questions and talk tracks. Intel files just make it richer.

Before running, `prep` prints a full context summary so you know exactly what was loaded:

```
Context loaded for prep:
  resume.md                    ✓
  job description              ✓
  role intel / strategy        ✓
  positioning brief            ✓
  intel/glassdoor_notes.md     ✓
  intel/recruiter_call.pdf     ✓
  Notion page notes            ✓
```

**Intel feeding** — drop files into the `intel/` subfolder inside the job's package folder before running `prep`:
- Supported: `.pdf` (text-based), `.md`, `.txt`
- Not supported: image files (`.png`, `.jpg`, etc.) — export as PDF or paste content into a `.md` file instead. A warning is shown for any file that can't be read.
- If using Notion: add research notes directly to the job's Notion page — `prep` reads the page body automatically.

Saves `interview_prep.md` to the package folder.

---

### `applycling critique <job_id> [--model MODEL] [--provider PROVIDER]`

Senior recruiter review of a complete application package.

```bash
applycling critique job_015               # uses strongest model for your provider
applycling critique job_015 --model gpt-4o --provider openai
```

Reads `resume.md`, `cover_letter.md`, `positioning_brief.md`, and `strategy.md` from the package folder and evaluates them across 6 dimensions:

1. **First impression** — what a recruiter sees in the first 6-second scan
2. **Positioning** — does the narrative match what the role actually needs?
3. **Evidence gaps** — claims without metrics or outcomes
4. **ATS risks** — missing keywords, formatting issues
5. **Cover letter** — does it add signal, or just repeat the resume?
6. **Red flags** — anything that would make a recruiter hesitate

Each finding includes the specific fix. Ends with a **Priority fixes** section: the top 3 changes ordered by impact.

Saves `critique.md` to the package folder. Read-only — never modifies existing artifacts.

**Model default:** automatically upgrades to the strongest model for your provider. Built-in defaults: `claude-opus-4-6` (Anthropic), `gpt-4o` (OpenAI), `gemini-2.5-pro` (Google). For Ollama, uses your configured model.

Override per-provider in `config.json` — only the providers you specify are overridden; others keep the built-in default:
```json
{
  "critique_models": {
    "anthropic": "claude-opus-5",
    "google": "gemini-3-ultra"
  }
}
```

Override for a single run with `--model`.

After a strong `applycling add` run (ATS score ≥ 80), the CLI will suggest running `critique` automatically.

### `applycling list`

Show all tracked jobs in a table with status.

### `applycling view <job_id>`

Print a tailored resume in the terminal.

### `applycling status <job_id>`

Update a job's status: `tailored` / `applied` / `interview` / `offer` / `rejected`.

### `applycling setup`

First-time setup or re-configure profile, model, voice/tone.

### `applycling notion connect`

Connect to Notion for job tracking. Creates a Job Tracker database with a Review Queue view.

---

## Project files

```
applycling/
├── data/
│   ├── resume.md        # your base resume (from setup)
│   ├── config.json      # model, provider, review_mode, generate_docx
│   ├── profile.json     # name, contact, voice_tone, never_fabricate
│   ├── stories.md       # optional: extra experiences the tailorer can draw from
│   ├── linkedin_profile.md  # optional: LinkedIn profile PDF export text
│   └── notion.json      # Notion integration credentials (if connected)
├── output/
│   └── {job_id}-{company}-{title}-{date}/
│       ├── resume.md / .html / .pdf / .docx
│       ├── cover_letter.md / .html / .pdf / .docx
│       ├── positioning_brief.md
│       ├── strategy.md          (role intel)
│       ├── job_description.md
│       ├── email_inmail.md
│       ├── fit_summary.md
│       ├── company_context.md
│       ├── critique.md          (applycling critique — on demand)
│       ├── interview_prep.md    (applycling prep — on demand)
│       ├── intel/               (drop research files here before running prep)
│       ├── v1/ v2/ ...          (previous versions archived by applycling refine)
│       ├── job.json             (manifest)
│       └── run_log.json
└── .env                 # API keys (gitignored)
```

### `data/stories.md`

Optional file. Write experiences, side projects, part-time work, or achievements here that aren't always on your resume but could be relevant for certain roles. The tailorer reads this and decides whether to include anything based on the job.

Example:
```markdown
## Consulting (part-time during master's)
Advised two SaaS startups on product strategy, ran discovery workshops,
built prototypes. 6-month engagement each.

## MS Access inventory system (2012)
Built first commercial product: an inventory system for an appliance store.
Sold to multiple shops via word of mouth.
```

### `data/linkedin_profile.md`

Optional file. Import your LinkedIn profile as additional context for resume tailoring. The tailorer draws from it when it contains fuller role descriptions, older experiences, or skills not captured in your base resume.

To import: run `applycling setup` and follow the LinkedIn import prompt (export your profile as PDF from LinkedIn → Settings → Data Privacy → Get a copy of your data, then select **PDF** from your profile page).

Set `use_linkedin_profile: false` in `data/config.json` to disable without deleting the file.

### `data/config.json`

```json
{
  "model": "claude-haiku-4-5-20251001",
  "provider": "anthropic",
  "review_mode": "interactive",
  "generate_docx": false,
  "generate_run_log": true,
  "use_linkedin_profile": true
}
```

| Key | Values | Default |
|-----|--------|---------|
| `provider` | `ollama`, `anthropic`, `openai`, `google` | `ollama` |
| `model` | Any model name for the provider | (set during setup) |
| `review_mode` | `interactive`, `async` | `interactive` |
| `generate_docx` | `true`, `false` | `false` |
| `generate_run_log` | `true`, `false` | `true` |
| `use_linkedin_profile` | `true`, `false` | `true` |
| `output_dir` | Any local path (supports `~`) | `./output` |
| `ats_hint_threshold` | Integer 0–100 | `80` |
| `critique_models` | `{"anthropic": "...", "openai": "...", "google": "..."}` | see below |
| `critique_models_reviewed_at` | ISO date string | set on first `add` run — update manually to dismiss the staleness nudge |

---

## Token usage

After each `applycling add`, a token breakdown is shown with cost estimates for cloud APIs:

```
Token usage (tiktoken cl100k):
  Job scraping (HTML)      0 tokens (structured data)
  Role Intel             3,200 in +    820 out
  Resume Tailor          2,100 in +    950 out
  Profile Summary        1,400 in +    120 out
  Positioning Brief      4,200 in +    680 out
  Cover Letter           3,800 in +    450 out
  Email + InMail         1,200 in +    280 out
  Fit Summary            1,400 in +    150 out
  ────────────────────────────────────────
  Total                 17,300 in +  3,450 out = 20,750

  API cost estimate:
  Gemini 2.0 Flash       $0.0031
  GPT-4o mini            $0.0047
  Claude Haiku 3.5       $0.0276
  GPT-4o                 $0.0778
  Claude Sonnet 3.7      $0.1035
  Gemini 2.5 Pro         $0.0950
  o4-mini                $0.0342
  Claude Opus 4          $0.5183
  o3                     $0.3110
```

When structured data is available (LinkedIn, sites with JSON-LD), the job scraping step uses zero tokens.

---

## Troubleshooting

- **`Ollama doesn't seem to be running`** — start it with `ollama serve`.
- **`No Ollama models installed`** — pull one: `ollama pull llama3.2`.
- **`ANTHROPIC_API_KEY is not set`** — add it to `.env` in the project root.
- **`No base resume found`** — run `applycling setup` first.
- **`command not found: applycling`** — activate the venv: `source .venv/bin/activate`.
- **`playwright install` fails** — run `.venv/bin/playwright install chromium` manually.
- **JD paste hangs** — type `---` on a new line and press Enter to submit.
- **Notion unreachable warning** — check that the integration has access to the page (··· → Connections → add integration).
