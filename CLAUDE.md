# applycling — Developer Guide

**applycling** is a CLI tool that turns a job URL into a complete application package: tailored resume, cover letter, positioning brief, email/InMail, and fit summary. Supports Anthropic (Claude), Google AI Studio (Gemini), and Ollama (local/cloud).

## Architecture vision

Before implementing a feature, read `ARCHITECTURE_VISION.md`. It is the
canonical record of architectural principles (thin harness + fat skills),
product direction, design-decision rationale, and known risks. Tickets
expire; this document does not. Use it to understand *why* the codebase
looks the way it does before changing it.

CLAUDE.md documents *how* the codebase works today. ARCHITECTURE_VISION.md
documents *why* it is shaped this way and where it is going.

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

## Skills architecture (post-T7)

All 16 LLM prompt templates live in `applycling/skills/<name>/SKILL.md`. The old `applycling/prompts.py` has been deleted entirely — there are no prompt strings in Python source files.

### Skill file format

Each `SKILL.md` file contains a YAML frontmatter block followed by the prompt template body:

```markdown
---
name: skill_name          # must match the directory name exactly
description: One-line purpose shown in logs and docs
inputs:
  - placeholder_one       # every {placeholder} used in the body must be listed
  - placeholder_two
output_file: result.md    # optional — omit if the step writes no file
model_hint: claude-3-5-haiku-20241022   # optional — per-skill model preference (T8)
temperature: 0.3          # optional — per-skill temperature override (T8)
---
Prompt body here.  Uses {placeholder_one} and {placeholder_two} via str.format.

Use {{literal_braces}} when you need a { or } character in the output.
```

Frontmatter is parsed with `pyyaml`. The template engine is plain `str.format` — zero additional dependencies.

### Loader: `applycling/skills/loader.py`

`load_skill(name) -> Skill` reads `SKILLS_DIR/<name>/SKILL.md`, parses the frontmatter, and returns a `Skill` dataclass with:

- `.name`, `.description`, `.inputs`, `.output_file`, `.model_hint`, `.temperature`
- `.render(**kwargs) -> str` — validates all declared inputs are present, then calls `template.format(**kwargs)`. Raises `SkillError` on missing inputs or undefined keys.

Import path: `from applycling.skills import load_skill, Skill, SkillError`

The loader validates that the `name` field in frontmatter matches the directory name — a mismatch raises `SkillError` immediately at load time.

### All 16 skills

| Skill | Purpose | `output_file` |
|-------|---------|---------------|
| `role_intel` | Analyse job description; build ATS keyword table and positioning strategy | `strategy.md` |
| `resume_tailor` | Tailor base resume to the job using role intel | `resume.md` |
| `profile_summary` | Write 2-3 sentence tailored profile summary | _(none — injected into resume)_ |
| `format_resume` | Reformat tailored resume into canonical markdown structure | `resume.md` |
| `positioning_brief` | Write interview-prep positioning brief from role intel + resume | `positioning_brief.md` |
| `cover_letter` | Write tailored cover letter matching candidate voice | `cover_letter.md` |
| `email_inmail` | Write short application email + LinkedIn InMail | `email_inmail.md` |
| `fit_summary` | Write honest 2-3 sentence fit summary | `fit_summary.md` |
| `refine_resume` | Refine tailored resume from feedback without restarting | `resume.md` |
| `refine_cover_letter` | Refine cover letter from feedback without rewriting | `cover_letter.md` |
| `refine_positioning_brief` | Update positioning brief to reflect resume changes | `positioning_brief.md` |
| `refine_email_inmail` | Refine email/InMail from feedback without rewriting | `email_inmail.md` |
| `interview_prep` | Generate scannable prep doc with likely questions per stage | `interview_prep.md` |
| `critique` | Senior-recruiter critique across 6 dimensions | `critique.md` |
| `questions` | Generate targeted practice questions with STAR frameworks | _(none — printed to terminal)_ |
| `pdf_resume_cleanup` | Convert messy PDF-extracted text to clean Markdown | _(none — used in import flow)_ |

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
- **Escaped braces in skill files:** `{{` and `}}` in a `SKILL.md` body render as literal `{` and `}` after `str.format`. Use this whenever the prompt itself must output a brace (e.g., `Q{{n}}` → `Q{n}` in the rendered prompt). Do not use `\{` — that is not valid `str.format` syntax.
- **Conditional logic stays in Python:** Skill templates have no `if/else` constructs. The caller pre-computes conditional strings (e.g., `voice_tone_section = "Write in a formal tone." if tone else ""`) and passes them as inputs. The template just interpolates `{voice_tone_section}` unconditionally.
- **No Jinja2:** The template engine is `str.format` and nothing else. Never add a Jinja2 dependency — `str.format` handles all current and planned cases. If logic is complex, move it into the Python caller, not the skill file.
- **Keep `ARCHITECTURE_VISION.md` canonical.** Update it in the same commit
  whenever you: add or remove a skill, change the pipeline contract
  (`_Step`, `PipelineStep`, `load_skill`), introduce a new provider, ship a
  T-numbered phase from "Future work", or discover a risk worth remembering.
  If you are unsure whether a change qualifies, it does — update the doc.

---

## Future work (T8+) — product roadmap

The detailed *why* behind these phases lives in `ARCHITECTURE_VISION.md`.
This section is the sprint-ready ticket list.

The skills architecture introduced in T7 is the foundation for the following planned features. Do not implement these ahead of schedule, but do not design changes that would conflict with them.

- **T8 — Per-skill model overrides and resolver layer:** The `model_hint` and `temperature` frontmatter fields are parsed and stored on `Skill` but not yet acted on. T8 will wire these into `_stream_chat` so expensive skills (e.g., `resume_tailor`) can target a stronger model while cheap skills (e.g., `fit_summary`) use a faster one. T8 will also add a resolver layer that inspects context (job seniority, available stories, etc.) and activates optional extra skills automatically.
- **T9 — Learning loop (`LEARNED.md`):** After each successful run, patterns extracted from feedback will be appended to a `LEARNED.md` file stored alongside each skill directory. Future renders will inject the relevant learned patterns as an additional `{learned_section}` input. This closes the loop between human review and prompt quality over time.
- **T10 — User-override skills (`~/.applycling/skills/`):** `load_skill` will check `~/.applycling/skills/<name>/SKILL.md` before falling back to the built-in skills directory. This lets power users override any prompt without touching the package source, and enables community-shared skill packs that drop into the user directory.
