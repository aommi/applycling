# Apply Companion — Agentic Build Instructions

You are building **Apply Companion**, a CLI tool that helps job seekers tailor their resume to job descriptions using a local Ollama LLM. Build the entire project from scratch, file by file, running and testing as you go.

---

## What You're Building

A Python CLI tool with these commands:

```
apply-companion setup        # First-time setup: saves base resume, picks Ollama model
apply-companion add          # Add a job: paste JD, get tailored resume + fit summary
apply-companion list         # List all tracked jobs with status
apply-companion status <id>  # Update job status (applied / interview / offer / rejected)
apply-companion view <id>    # View tailored resume for a specific job
```

---

## Tech Stack

- **Python 3.10+**
- **click** — CLI framework
- **ollama** Python SDK — to call local Ollama models
- **rich** — pretty terminal output (tables, panels, spinners)
- **JSON files** — simple local storage (no database)

---

## Project Structure to Build

```
apply-companion/
├── CLAUDE.md                  # This file
├── README.md                  # Setup + usage instructions
├── pyproject.toml             # Package config with dependencies
├── apply_companion/
│   ├── __init__.py
│   ├── cli.py                 # All click commands
│   ├── llm.py                 # Ollama integration
│   ├── storage.py             # Read/write jobs.json and resume
│   └── prompts.py             # All LLM prompt templates
├── data/
│   └── .gitkeep               # jobs.json and resume stored here at runtime
└── output/
    └── .gitkeep               # Tailored resumes saved here
```

---

## Step-by-Step Build Order

### Step 1 — Project scaffolding
Create `pyproject.toml` with dependencies: `click`, `ollama`, `rich`. Make it installable via `pip install -e .` with entrypoint `apply-companion = apply_companion.cli:main`.

### Step 2 — Storage layer (`storage.py`)
- `save_resume(text)` — saves base resume to `data/resume.md`
- `load_resume()` — loads it, raises friendly error if not set up
- `save_job(job_dict)` — appends to `data/jobs.json`, auto-generates an ID like `job_001`
- `load_jobs()` — returns list of all jobs
- `load_job(id)` — returns single job by ID
- `update_job_status(id, status)` — updates status field

### Step 3 — Prompts (`prompts.py`)
Two prompts:

**TAILOR_RESUME_PROMPT**: Takes `{resume}` and `{job_description}`. Instructs model to rewrite resume bullets to match the JD's language, keywords, and priorities. Output only the tailored resume in markdown, nothing else.

**FIT_SUMMARY_PROMPT**: Takes `{resume}` and `{job_description}`. Returns 2-3 sentences: what's a strong match, what to emphasize, any gaps to address. Keep it direct and honest, like a smart friend reviewing your application.

### Step 4 — LLM layer (`llm.py`)
- `get_available_models()` — calls `ollama.list()`, returns model names
- `tailor_resume(resume, job_description, model)` — calls Ollama with TAILOR_RESUME_PROMPT
- `get_fit_summary(resume, job_description, model)` — calls Ollama with FIT_SUMMARY_PROMPT
- Use streaming if possible so the user sees output as it generates
- Handle `ollama.ResponseError` with a friendly message telling user to run `ollama serve`

### Step 5 — CLI commands (`cli.py`)

#### `apply-companion setup`
1. Ask user to paste their base resume (multi-line input, end with `---`)
2. List available Ollama models with `rich` selection prompt
3. Save resume to `data/resume.md`
4. Save chosen model name to `data/config.json`
5. Print success message with next steps

#### `apply-companion add`
1. Ask: job title, company name
2. Ask: paste job description (multi-line, end with `---`)
3. Show a `rich` spinner: "Tailoring your resume..."
4. Call `tailor_resume()` and `get_fit_summary()`
5. Save tailored resume to `output/{company}-{title}-{date}.md`
6. Save job entry to `jobs.json` with fields: id, title, company, date_added, status (default: "tailored"), output_file
7. Print fit summary in a `rich` Panel
8. Print where the tailored resume was saved

#### `apply-companion list`
- Show a `rich` Table with columns: ID, Company, Title, Date, Status
- Color-code status: tailored=blue, applied=yellow, interview=green, offer=bold green, rejected=dim

#### `apply-companion status <id>`
- Prompt to pick new status from: tailored / applied / interview / offer / rejected
- Update and confirm

#### `apply-companion view <id>`
- Load and print the tailored resume markdown to terminal using `rich.Markdown`

---

## Key Details

- Store config (chosen model) in `data/config.json`
- All data files go in `data/`, all resume outputs in `output/` — create these dirs if they don't exist
- If Ollama isn't running, catch the connection error and print: "Ollama doesn't seem to be running. Start it with: `ollama serve`"
- If no model is configured, prompt user to run `apply-companion setup` first
- Multi-line input pattern: print instructions, read lines until user types `---` on its own line

---

## README to Write

Include:
1. Prerequisites: Python 3.10+, Ollama installed and running
2. Recommended models: `llama3.2`, `mistral`, `phi3` (fast and good at text tasks)
3. Install steps: `pip install -e .`
4. First run: `apply-companion setup`
5. Daily use: `apply-companion add`

---

## Build Instructions for You (Claude Code)

1. Build in order: pyproject.toml → storage.py → prompts.py → llm.py → cli.py → README.md
2. After creating each file, verify it's syntactically correct
3. After all files are created, run `pip install -e .` and verify the `apply-companion` command is available
4. Run `apply-companion --help` to confirm all commands are registered
5. If Ollama is available locally, do a quick smoke test with `apply-companion setup`
6. Fix any import errors or bugs before finishing

Do not ask for confirmation between steps — build the whole thing end to end.
