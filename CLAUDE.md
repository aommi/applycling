# applycling — Developer Guide

**applycling** is a CLI tool that turns a job URL into a complete application package: tailored resume, cover letter, positioning brief, email/InMail, and fit summary. Supports Anthropic (Claude), Google AI Studio (Gemini), and Ollama (local/cloud).

---

## Project structure

```
applycling/
├── applycling/
│   ├── cli.py           # All click commands + _Step context manager
│   ├── llm.py           # LLM provider routing (ollama / anthropic / google)
│   ├── prompts.py       # All LLM prompt templates
│   ├── scraper.py       # Job posting scraper (LinkedIn, JSON-LD, LLM fallback)
│   ├── storage.py       # File-based config/resume/profile/stories storage
│   ├── render.py        # Markdown → HTML → PDF (Playwright/Chromium)
│   ├── package.py       # Assembles output folder + run_log.json
│   ├── tracker/         # TrackerStore abstraction (Notion + SQLite)
│   │   ├── __init__.py  # get_store() — auto-detects Notion, falls back to SQLite
│   │   ├── notion_store.py
│   │   └── sqlite_store.py
│   ├── notion_connect.py  # Interactive Notion setup wizard
│   └── pdf_import.py    # PDF → Markdown resume import
├── data/
│   ├── config.json      # provider, model, review_mode, generate_docx, generate_run_log
│   ├── profile.json     # name, email, phone, location, linkedin, github, voice_tone, never_fabricate
│   ├── resume.md        # base resume (never modified by LLM)
│   ├── stories.md       # optional extra experiences for tailoring
│   └── notion.json      # Notion credentials (if connected)
└── output/
    └── {company}-{title}-{date}[-{model}]/   # one folder per run
        ├── resume.md / .html / .pdf
        ├── cover_letter.md / .html / .pdf
        ├── positioning_brief.md
        ├── strategy.md
        ├── email_inmail.md
        ├── fit_summary.md
        ├── company_context.md
        ├── job.json
        └── run_log.json
```

---

## Adding a new LLM pipeline step

All pipeline steps in `applycling add` use the `_Step` context manager defined in `cli.py`. This handles timing, logging, token counting, and status automatically.

**Pattern — copy this exactly for any new step:**

```python
_s = _Step("step_name", step_logs, output_file="output_file.md")
_s.prompt_text = prompts.YOUR_PROMPT.format(...)
try:
    with _s, console.status("[cyan]Doing the thing...[/cyan]", spinner="dots"):
        for chunk in llm.your_function(..., provider=provider):
            _s.collect(chunk)
except llm.LLMError as e:
    console.print(f"[red]{e}[/red]")   # use [red] + sys.exit(1) for critical steps
    sys.exit(1)                         # use [yellow] + continue for optional steps
result = _clean_llm_output(_s.output)
```

- `output_file` is the filename that will be written in the package folder (used in run_log).
- `prompt_text` must be set before entering the `with` block.
- `_Step.__exit__` auto-appends to `step_logs` with timing, status, and text — no manual append needed.
- Status is set to `"ok"`, `"skipped"` (empty output), or `"failed"` (exception) automatically.
- Token counts and cost estimates are computed from `step_logs` at the end of the run.

**Adding the LLM function:**

1. Add the prompt template to `prompts.py`.
2. Add the function to `llm.py` — import the prompt and yield from `_stream_chat(model, prompt, provider)`.
3. Use `_Step` in `cli.py` as shown above.

Nothing else needs wiring — token counts, run_log, and the terminal breakdown all pick it up automatically.

---

## Config keys (`data/config.json`)

| Key | Values | Default |
|-----|--------|---------|
| `provider` | `ollama`, `anthropic`, `google` | `ollama` |
| `model` | any model name for the provider | set during setup |
| `review_mode` | `interactive`, `async` | `interactive` |
| `generate_docx` | `true`, `false` | `false` |
| `generate_run_log` | `true`, `false` | `true` |

`storage.save_config()` merges into the existing config — it never overwrites unrelated keys.

---

## Tracker abstraction

`get_store()` in `tracker/__init__.py` auto-detects Notion (`data/notion.json` exists and is reachable) and falls back to SQLite transparently. All tracker calls go through the `TrackerStore` interface: `save_job`, `load_jobs`, `load_job`, `update_job`. Never call Notion or SQLite directly from `cli.py`.

---

## Output folder naming

`package.folder_name(company, title, date, model)` builds the folder name. Model is only appended when `--model` is explicitly passed (benchmarking). The `_slugify()` function handles special characters including `:` in model names.

---

## Resume formatting

The tailored resume goes through two LLM passes:
1. **resume_tailor** — content tailoring (keywords, bullets, relevance)
2. **format_resume** — structure reformatting to match the user's preferred template

The format template rules are in `FORMAT_RESUME_PROMPT` in `prompts.py`. The HTML/CSS in `render.py` uses `h3 em { float: right }` to right-align dates when written as `### Job Title *Date Range*`.

---

## Key conventions

- `_clean_llm_output()` strips code fences, preamble, leaked prompt markers, and trailing sign-offs from all LLM output. Always apply it.
- `_profile_header_markdown()` builds the static name/contact block from `profile.json`. Never let the LLM write this section.
- The profile summary section header must be `## PROFILE` (all caps) to match the format template.
- `storage.save_config()` merges — never call it with only partial keys unless merging is the intent.
- All API keys live in `.env` at repo root (gitignored). Loaded via `python-dotenv` in `llm.py`.
