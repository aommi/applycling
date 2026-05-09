# applycling

> Your clingy job-search companion. We won't leave you alone until you land your next role.

A CLI that tailors your resume, writes cover letters, and builds complete application packages for each job you apply to. Supports **local Ollama models**, **Anthropic (Claude)**, **OpenAI (GPT-4o)**, and **Google AI Studio (Gemini)**.

It never fabricates. Every bullet, claim, and date comes from what you actually gave it — your resume, your stories, your voice. The LLM tailors and positions; it does not invent.

Getting started is fast — `applycling setup` walks you through everything interactively, so you go from zero to your first full application package without touching a config file.

---

## What it does

Run `applycling add` with a job URL and get a complete package:

1. **Scrapes the job posting** (structured data first, LLM fallback) and optionally the company page.
2. **Runs Role Intel** — extracts the unique 20% signal from the JD, identifies the niche, scores ATS keyword coverage, flags gaps.
3. **Tailors your resume** — recruiter-first, outcome-first, ATS-optimized. Uses your voice/tone and draws from your stories file when relevant.
4. **Writes a cover letter** — 5-paragraph structure matched to the company's tone.
5. **Drafts an application email and LinkedIn InMail** — direct, no fluff.
6. **Generates a positioning brief** — positioning decisions, application strength, gap prep with bridge answers, ATS before/after score.
7. **Assembles a package** — resume (md/html/pdf), cover letter (md/html/pdf), positioning brief, email/InMail, strategy, all in one folder.
8. **Tracks everything** — in Notion (optional) or local SQLite.

Once you have a package, the toolkit keeps going:

- **`refine`** — iterate on any artifact with feedback, without re-running the full pipeline. Previous versions are archived automatically.
- **`critique`** — senior recruiter review across 6 dimensions: first impression, positioning, evidence gaps, ATS risks, cover letter signal, red flags.
- **`prep`** — stage-specific interview prep (recruiter / hiring manager / technical / executive) with talk tracks built from your actual resume.
- **`questions`** — targeted practice questions with STAR answer frameworks, additive across rounds so nothing gets overwritten.

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

Setup is designed to be as smooth as possible — every prompt has a sensible default, existing values are pre-filled so re-runs only ask for what changed, and nothing is left as an exercise for the config file. This walks you through:

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
- **Text files:** `.pdf` (text-based), `.md`, `.txt` — always supported.
- **Images:** `.png`, `.jpg`, `.webp`, etc. — supported when a vision model is configured. Screenshots of Slack messages, LinkedIn DMs, recruiter emails all work.
- **Notion notes:** if connected, `prep` reads the job's Notion page body automatically.
- A warning is shown for any file that can't be read — nothing fails silently.

**Image extraction** — to enable, add to `data/config.json`:
```json
{
  "intel_vision_model": "llava",
  "intel_vision_provider": "ollama"
}
```

`intel_vision_provider` defaults to your configured provider if omitted. Any vision-capable model works: `llava`, `llama3.2-vision`, `moondream` (Ollama); or your cloud model (`claude-sonnet-4-6`, `gpt-4o`, `gemini-2.0-flash`) which all support vision natively. Without this config, images are skipped with a hint.

Image extractions are cached in `intel/.cache/{filename}.extracted.md` so they're not re-extracted on every run. You can review and edit the cached text — it's used as-is until the original image is modified. The `.cache/` folder is managed automatically and kept separate from your own intel files.

**Step notes** — after each interview round, drop your notes into `intel/`. The next `prep` run automatically uses them as context:

```
intel/
├── step1_recruiter_notes.md     ← what they asked, what went well
├── step2_hm_notes.md            ← hiring manager focus areas
├── glassdoor_research.md
├── slack_recruiter.png          ← extracted via vision model
└── .cache/                      ← auto-managed extraction cache (don't edit)
```

Saves `interview_prep.md` to the package folder.

---

### `applycling questions <job_id> [--stage STAGE] [-n COUNT] [--model MODEL] [--provider PROVIDER]`

Generate targeted interview questions with STAR-structured answer frameworks. Additive — each run appends a new dated section to `questions.md`. Run it multiple times (before different rounds, or after adding new intel) without losing previous output.

```bash
applycling questions job_015                          # 5 questions × all 4 stages
applycling questions job_015 --stage recruiter        # recruiter stage only
applycling questions job_015 --stage technical -n 8   # 8 technical questions
applycling questions job_015 --stage hiring-manager --model claude-opus-4-6 --provider anthropic
```

For each question:
- **Why likely** — why this specific interviewer will ask this, tied to the JD or candidate gaps
- **STAR framework** — a suggested answer using a named role and real outcome from the resume
- **Watch out for** — the trap or pitfall to avoid when answering

Each run passes existing questions as context so the LLM generates new, non-duplicate questions. A `⚠ Gap:` note is added when the candidate has a real gap, with a suggested bridge answer.

Saves (or appends) to `questions.md` in the package folder. Reads the same intel context as `prep`: `intel/` folder files, vision-extracted images (if configured), and Notion page notes.

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

Update a job's status. Valid statuses: `new`, `generating`, `reviewing`, `reviewed`, `applied`, `interviewing`, `offered`, `accepted`, `rejected`, `failed`, `archived`. See `applycling/statuses.py` for the canonical state machine.

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
│       ├── questions.md         (applycling questions — additive, append-only)
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
| `intel_vision_model` | any vision-capable model name | not set (images skipped) |
| `intel_vision_provider` | `ollama`, `anthropic`, `openai`, `google` | same as `provider` |
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

---

## Telegram bot (send job URLs from your phone)

applycling can listen for job URLs sent to a Telegram bot and generate application packages automatically. The intake uses Hermes Agent's Telegram gateway.

### Architecture

```
Your phone → Telegram bot → Hermes (deepseek, routing) → applycling pipeline (Claude, generation) → PDFs back to Telegram
```

Two separate LLMs, two separate configs — no single point of failure. See `DECISIONS.md` §2026-04-27 for rationale.

### Setup

```bash
# 1. Configure Telegram credentials (one-time)
python3 -m applycling.cli telegram setup

# 2. Provision the Hermes profile + gateway (idempotent)
./scripts/setup_hermes_telegram.sh
```

The script creates an isolated Hermes profile with:
- Its own Telegram bot token
- Toolsets locked to terminal only (no browser or file tools)
- API keys merged from your main Hermes config
- A launchd background service that survives reboots
- A profile wrapper command: `applycling-hermes`

### Usage

Send a job URL to your applycling bot on Telegram. Progress messages and generated PDFs (resume, cover letter) arrive in the same chat.

```bash
# Check gateway status
applycling-hermes gateway status

# View logs
tail -f ~/.hermes/profiles/applycling/logs/gateway.log
```

---

## Local Workbench (web UI)

Start a local web dashboard to manage your job search pipeline visually.

```bash
# Start the workbench
applycling ui serve

# Index existing output packages
applycling ui index-output
```

Open http://127.0.0.1:8080 in your browser. The workbench shows:

- **Job board** — all jobs grouped by status, data-driven from the canonical 11-state machine (`new`, `generating`, `reviewing`, `reviewed`, `applied`, `interviewing`, `offered`, `accepted`, `rejected`, `failed`, `archived`)
- **Job detail** — inspect generated artifacts (resume PDF/MD, cover letter PDF/MD, positioning brief, fit summary)
- **Status actions** — one-click status transitions (data-driven from `statuses.py`). Regenerate runs the full pipeline from `new`, `reviewing`, or `failed`.
- **URL submission** — paste a job URL and trigger the full pipeline from the UI
- **Index existing** — import previously generated packages from `output/` into the workbench

### Postgres Backend (optional)

SQLite is the default zero-config backend. Postgres is available as an opt-in alternative:

```bash
# 1. Install with Postgres support
pip install ".[postgres]"

# 2. Start Postgres via Docker
docker compose up -d postgres

# 3. Run migrations
alembic upgrade head

# 4. Seed the local user
DATABASE_URL=postgresql://applycling:applycling@localhost:5432/applycling \
  python -m applycling.db_seed

# 5. Use Postgres
APPLYCLING_DB_BACKEND=postgres \
  DATABASE_URL=postgresql://applycling:applycling@localhost:5432/applycling \
  applycling ui serve
```

To switch back to SQLite: unset `APPLYCLING_DB_BACKEND` or set it to `sqlite`.

### Known limitations

- Local only (binds to 127.0.0.1) — no network exposure
- No authentication — single-user local tool
- Pipeline runs synchronously (blocks the request until generation completes)
- SQLite by default; Postgres available via `APPLYCLING_DB_BACKEND=postgres DATABASE_URL=...`

## Using applycling via MCP

applycling can act as an MCP (Model Context Protocol) server, making its
pipeline available as tools in Claude Desktop, Cursor, and other MCP clients.
Your AI assistant becomes the interface — describe the job, and it generates
the full application package through applycling's tools.

### How it works

```
Your AI client (Claude Desktop, Cursor, etc.)
       │  stdio (JSON-RPC) — reads applycling tools
       ▼
applycling MCP server (runs locally)
       │  calls pipeline directly
       ▼
applycling pipeline → your configured LLM → package artifacts on disk
```

The MCP server runs on your machine. It reads your Application Profile (the
same one used by the CLI and local workbench) and your configured LLM API key.
Your AI client calls tools like `add_job` and `get_package` — applycling does
the heavy lifting behind the scenes.

### Prerequisites

Complete the standard install first (see [Install](#install) above):

- Python 3.10+ with a venv
- One configured LLM provider (Anthropic, OpenAI, Google, or Ollama)
- API key in `.env` (for cloud providers)
- `applycling setup` completed — profile with name, email, and resume

### Setup

1. Install with MCP support:
   ```bash
   pip install -e ".[mcp]"
   ```

2. Complete the standard setup (if not already done):
   ```bash
   applycling setup
   ```

3. Get your client config:
   ```bash
   applycling mcp config
   ```

4. Paste the JSON output into your MCP client config:
   - **Claude Desktop:** `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Cursor:** `.cursor/mcp.json`

5. Restart your client. applycling tools are now available.

### Available Tools

Once connected, your AI client has access to these tools:

| Tool | What it does |
|------|-------------|
| `add_job(url)` | Generate a complete application package for a job URL (2–5 min) |
| `list_jobs(limit, status)` | List your tracked job applications |
| `get_package(job_id)` | Read text content of generated markdown artifacts |
| `update_job_status(job_id, status)` | Move a job through the application pipeline |
| `interview_prep(job_id, stage)` | Generate interview prep materials |
| `refine_package(job_id, feedback)` | Iterate on artifacts with specific feedback |
| `answer_questions(job_id, questions)` | Draft answers to application form questions |
| `critique_package(job_id)` | Senior recruiter review of your package |
| `generate_questions(job_id, stage, count)` | Generate targeted interview questions with STAR frameworks |

### Where Artifacts Live

Generated packages are local folders on your machine under `output/`:

```
output/<job_id>-<company>-<title>-<date>/
├── resume.md / .html / .pdf
├── cover_letter.md / .html / .pdf
├── positioning_brief.md
├── email_inmail.md
├── fit_summary.md
├── interview_prep.md
└── ...
```

`get_package` returns the text content of markdown artifacts directly in
your chat. PDFs and other binary files remain as local files — your AI
client can tell you the path, but it cannot send the file itself. Open
them from the `output/` folder.

### Example Prompts

Once connected, try these in your AI client:

- "Generate an application for https://example.com/jobs/123"
- "Show my recent tracked job applications"
- "Open the package for job_001 and summarize the generated artifacts"
- "Mark job_001 as applied"
- "Generate interview prep for job_001"
- "Refine job_001's resume and cover letter to emphasize backend systems work"
- "Answer the application form questions for job_001"
- "Critique my application package for job_001"
- "Generate interview questions for job_001 (recruiter screen)"

### Client Timeout Note

The `add_job` tool runs the full pipeline synchronously (2–5 minutes).
Progress notifications appear during the run, but if your MCP client has a
request timeout below 5 minutes, the call may be cut off before completion.
If the client times out, run `applycling add <url>` via CLI for the
generation step, then inspect the package with MCP read tools.
