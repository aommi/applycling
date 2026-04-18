# applycling — Developer Guide

**applycling** is a CLI tool that turns a job URL into a complete application package: tailored resume, cover letter, positioning brief, email/InMail, and fit summary. Supports Anthropic (Claude), Google AI Studio (Gemini), and Ollama (local/cloud).

---

## Project structure

```
applycling/
├── applycling/
│   ├── cli.py           # All click commands + _Step context manager
│   ├── llm.py           # LLM provider routing (ollama / anthropic / google)
│   ├── skills/          # Skill files — one subdirectory per skill
│   │   ├── __init__.py  # re-exports Skill, SkillError, load_skill
│   │   ├── loader.py    # load_skill(name) → Skill(template, metadata)
│   │   ├── role_intel/SKILL.md
│   │   ├── resume_tailor/SKILL.md
│   │   ├── profile_summary/SKILL.md
│   │   ├── format_resume/SKILL.md
│   │   ├── positioning_brief/SKILL.md
│   │   ├── cover_letter/SKILL.md
│   │   ├── email_inmail/SKILL.md
│   │   ├── fit_summary/SKILL.md
│   │   ├── interview_prep/SKILL.md
│   │   ├── critique/SKILL.md
│   │   ├── questions/SKILL.md
│   │   ├── refine_resume/SKILL.md
│   │   ├── refine_cover_letter/SKILL.md
│   │   ├── refine_positioning_brief/SKILL.md
│   │   ├── refine_email_inmail/SKILL.md
│   │   └── pdf_resume_cleanup/SKILL.md
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

**Step 1 — Create `applycling/skills/<name>/SKILL.md`** with YAML frontmatter and the prompt body:

```markdown
---
name: my_step
description: One-line description of what this skill does
inputs:
  - input_key_one
  - input_key_two
output_file: my_step.md   # omit if the step produces no output file
---
You are an expert at...

=== INPUT ONE ===
{input_key_one}

=== INPUT TWO ===
{input_key_two}
```

Frontmatter fields: `name` (must match directory name), `description`, `inputs` (list of `{placeholder}` names in the body), `output_file` (optional), `model_hint` (optional), `temperature` (optional).

**Step 2 — Add the function to `llm.py`:**

```python
from .skills import load_skill

def my_step(input_key_one: str, input_key_two: str, model: str, provider: str = "ollama") -> Iterator[str]:
    prompt = load_skill("my_step").render(
        input_key_one=input_key_one,
        input_key_two=input_key_two,
    )
    yield from _stream_chat(model, prompt, provider)
```

**Step 3 — Use `_Step` in `cli.py` or `PipelineStep` in `pipeline.py`:**

```python
_s = _Step("my_step", step_logs, output_file="my_step.md")
_s.prompt_text = load_skill("my_step").render(
    input_key_one=..., input_key_two=...
)
try:
    with _s, console.status("[cyan]Doing the thing...[/cyan]", spinner="dots"):
        for chunk in llm.my_step(..., provider=provider):
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

Nothing else needs wiring — token counts, run_log, and the terminal breakdown all pick it up automatically.

---

## Config keys (`data/config.json`)

| Key | Values | Default |
|-----|--------|---------|
| `provider` | `ollama`, `anthropic`, `openai`, `google` | `ollama` |
| `model` | any model name for the provider | set during setup |
| `review_mode` | `interactive`, `async` | `interactive` |
| `generate_docx` | `true`, `false` | `false` |
| `generate_run_log` | `true`, `false` | `true` |
| `use_linkedin_profile` | `true`, `false` | `true` |
| `output_dir` | any local path, supports `~` | `./output` |

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

The format template rules are in `applycling/skills/format_resume/SKILL.md`. The HTML/CSS in `render.py` uses `h3 em { float: right }` to right-align dates when written as `### Job Title *Date Range*`.

---

## Key conventions

- `_clean_llm_output()` strips code fences, preamble, leaked prompt markers, and trailing sign-offs from all LLM output. Always apply it.
- `_profile_header_markdown()` builds the static name/contact block from `profile.json`. Never let the LLM write this section.
- The profile summary section header must be `## PROFILE` (all caps) to match the format template.
- `storage.save_config()` merges — never call it with only partial keys unless merging is the intent.
- All API keys live in `.env` at repo root (gitignored). Loaded via `python-dotenv` in `llm.py`.
