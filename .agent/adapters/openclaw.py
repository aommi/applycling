"""
OpenClaw Adapter — generates .openclaw-system.md (system prompt include)

OpenClaw has no native project-root file convention. Two install options:
  A) Point OpenClaw at this file via the `system_prompt_file` setting
  B) Paste the file contents directly into OpenClaw's system prompt settings
"""
from pathlib import Path


def generate(project_root: Path):
    """Generate OpenClaw configuration."""

    preprompt_path = project_root / ".agent" / "templates" / "preprompt.txt"
    with open(preprompt_path, "r") as f:
        preprompt_content = f.read()

    system_prompt_content = f"""# OpenClaw system prompt — applycling

<!--
  Install options:
    A) system_prompt_file: .openclaw-system.md  (in OpenClaw config)
    B) Paste this file's content into OpenClaw's system prompt settings
-->

You are an agent working in the **applycling** project — a CLI tool that turns a job URL
into a complete application package (resume, cover letter, positioning brief, email, fit summary).

This project uses a file-based memory system. Treat it as authoritative.

## Startup (read in order)

1. `memory/semantic.md` — distilled project knowledge (≤500 tokens); read ONCE per session
2. `memory/working.md` — live task state; read before every response

## On Every Turn

{preprompt_content.strip()}

## Architecture

### Skills
All LLM prompt templates live in `applycling/skills/<name>/SKILL.md` with YAML frontmatter:

```
---
name: skill_name
description: One-line purpose
inputs:
  - input_key
output_file: result.md
---
Prompt body using {{input_key}} via str.format.
```

Loader: `from applycling.skills import load_skill` → `load_skill(name).render(**kwargs)`

### Pipeline
`applycling/pipeline.py` — linear flow:
`role_intel → resume_tailor → profile_summary → format_resume → positioning_brief → cover_letter → email_inmail → fit_summary`

Before implementing a feature, read `ARCHITECTURE_VISION.md`.

### LLM routing
`applycling/llm.py` — supports ollama, anthropic, google, openai. API keys in `.env`.

### Tracker
`get_store()` in `tracker/__init__.py` — auto-detects Notion or SQLite. Always use the
`TrackerStore` interface; never call either store directly from `cli.py`.

## Key Conventions

- `_clean_llm_output()` strips code fences from all LLM output — always apply it
- Profile header: `## PROFILE` (all caps)
- `storage.save_config()` merges — don't call with partial keys
- Skill templates use `str.format` — escape braces with `{{{{` and `}}}}`
- Conditional logic stays in Python, not skill templates
- All API keys in `.env` (gitignored)

## Memory Discipline

- `memory/semantic.md` — propose updates; wait for approval before writing
- `memory/working.md` — update freely after each response; no approval needed
- `DECISIONS.md` — append-only; propose entries for approval
- `dev/[task]/context.md` — log confirmed assumptions immediately; no approval needed
"""

    with open(project_root / ".openclaw-system.md", "w") as f:
        f.write(system_prompt_content)

    return (
        "OpenClaw configuration generated:\n"
        "  - .openclaw-system.md\n\n"
        "Install options:\n"
        "  A) Set system_prompt_file: .openclaw-system.md in OpenClaw config\n"
        "  B) Paste the file contents into OpenClaw's system prompt settings"
    )
