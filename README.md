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
GOOGLE_API_KEY=AIza...
```

---

## First-time setup

```bash
applycling setup
```

This walks you through:

1. **Pick an Ollama model** from your installed models.
2. **Import your base resume** — from PDF or paste.
3. **Personal details** — name, email, phone, location, LinkedIn, GitHub. Used verbatim in every resume, never rewritten by AI.
4. **Voice and tone** — how you want your resume and cover letter to sound (e.g. "Direct, active voice, outcome-first").
5. **Never fabricate** — hard boundaries on what the LLM must never invent.
6. **Playwright browsers** — installed automatically for PDF rendering.

To use a cloud provider instead of Ollama, edit `data/config.json` after setup:

```json
{
  "provider": "anthropic",
  "model": "claude-haiku-4-5-20251001"
}
```

Valid providers: `ollama`, `anthropic`, `google`.

---

## Commands

### `applycling add [--async]`

Add a job and generate the full application package.

```bash
applycling add                  # interactive mode (default)
applycling add --async          # skip input gates, generate everything
```

**Interactive mode** asks you to confirm the positioning angle and gap handling before writing the resume. **Async mode** generates the full package without stopping — review the output later.

The flow:
1. Provide a job URL (or enter details manually)
2. Role Intel runs and shows findings
3. You confirm angle + gap handling (interactive) or auto-proceed (async)
4. Resume, cover letter, email/InMail, positioning brief generated
5. Package assembled and tracked

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
│   └── notion.json      # Notion integration credentials (if connected)
├── output/
│   └── {company}-{title}-{date}/
│       ├── resume.md / .html / .pdf / .docx
│       ├── cover_letter.md / .html / .pdf / .docx
│       ├── positioning_brief.md
│       ├── strategy.md (role intel output)
│       ├── email_inmail.md
│       ├── fit_summary.md
│       ├── company_context.md
│       └── job.json (manifest)
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

### `data/config.json`

```json
{
  "model": "claude-haiku-4-5-20251001",
  "provider": "anthropic",
  "review_mode": "interactive",
  "generate_docx": false
}
```

| Key | Values | Default |
|-----|--------|---------|
| `provider` | `ollama`, `anthropic`, `google` | `ollama` |
| `model` | Any model name for the provider | (set during setup) |
| `review_mode` | `interactive`, `async` | `interactive` |
| `generate_docx` | `true`, `false` | `false` |

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
