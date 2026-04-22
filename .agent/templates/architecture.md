## Architecture

Before implementing a feature, read `ARCHITECTURE_VISION.md`. It is the canonical record of architectural principles, product direction, and design-decision rationale.

### Skills

All LLM prompt templates live in `applycling/skills/<name>/SKILL.md`:

```markdown
---
name: skill_name
description: One-line purpose
inputs:
  - input_key
output_file: result.md
model_hint: claude-3-5-haiku-20241022  # optional
temperature: 0.3  # optional
---
Prompt body using {input_key} via str.format.
```

Loader: `from applycling.skills import load_skill` → `load_skill(name).render(**kwargs)`

### Pipeline

`applycling/pipeline.py` — library API with `PipelineContext`, `PipelineStep`, `PipelineRun`.
Linear flow: `role_intel → resume_tailor → profile_summary → format_resume → positioning_brief → cover_letter → email_inmail → fit_summary`

### LLM Routing

`applycling/llm.py` — supports ollama, anthropic, google, openai.
API keys in `.env` (gitignored), loaded via `python-dotenv`.

### Tracker

`get_store()` in `tracker/__init__.py` — auto-detects Notion or falls back to SQLite.
Use the `TrackerStore` interface only — never call either store directly from `cli.py`.

---

## Key Files

| File | Purpose |
|------|---------|
| `memory/semantic.md` | Distilled project knowledge (≤500 tokens) |
| `memory/working.md` | Live task state (≤300 tokens) |
| `DECISIONS.md` | Append-only decisions log |
| `dev/[task]/` | Active task context (plan.md, context.md, tasks.md) |
| `ARCHITECTURE_VISION.md` | Canonical architectural reference |

---

## Key Conventions

- `_clean_llm_output()` strips code fences from all LLM output — always apply it
- Profile header: `## PROFILE` (all caps)
- `storage.save_config()` merges — don't call with partial keys
- Skill templates use `str.format` — escape braces with `{{` and `}}`
- Conditional logic stays in Python, not skill templates
- All API keys in `.env` (gitignored)
