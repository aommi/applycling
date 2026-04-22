"""
Gemini CLI Adapter — generates GEMINI.md + sub-directory context files
"""
from pathlib import Path

def generate(project_root: Path):
    """Generate Gemini CLI configuration."""

    # Read the shared preprompt
    preprompt_path = project_root / ".agent" / "templates" / "preprompt.txt"
    with open(preprompt_path, "r") as f:
        preprompt_content = f.read()

    gemini_md_content = f"""# Project Context — applycling

**applycling** is a CLI tool that turns a job URL into a complete application package: tailored resume, cover letter, positioning brief, email/InMail, and fit summary.

---

## Memory System

This project uses a file-based memory system to maintain context across sessions.

### Session Startup

Read `memory/semantic.md` ONCE to load project context.

### On Every Turn

{preprompt_content.strip()}

---

## Architecture

### Skills

All LLM prompt templates live in `applycling/skills/<name>/SKILL.md`:

```markdown
---
name: skill_name
description: One-line purpose
inputs:
  - input_key
output_file: result.md
model_hint: claude-3-5-haiku-20241022
temperature: 0.3
---
Prompt body using {{input_key}} via str.format.
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

---

## Key Files

| File | Purpose |
|------|---------|
| `memory/semantic.md` | Distilled project knowledge (≤500 tokens) |
| `memory/working.md` | Live task state (≤300 tokens) |
| `DECISIONS.md` | Append-only decisions log |
| `dev/[task]/` | Active task context |
| `ARCHITECTURE_VISION.md` | Canonical architectural reference |

---

## Conventions

- `_clean_llm_output()` strips code fences from LLM output
- Profile header: `## PROFILE` (all caps)
- `storage.save_config()` merges — don't call with partial keys
- Skill templates use `str.format` — escape braces with `{{` and `}}`
- Conditional logic stays in Python, not skills
"""

    with open(project_root / "GEMINI.md", "w") as f:
        f.write(gemini_md_content)

    # Create .gemini/ directory for context files (Gemini CLI convention)
    gemini_dir = project_root / ".gemini"
    gemini_dir.mkdir(exist_ok=True)

    # Context file pointing to memory system
    context_content = """# Gemini CLI Context

This project uses a shared memory system in the `memory/` directory:

- `memory/semantic.md` — project knowledge (read at session start)
- `memory/working.md` — current task state (read every turn)
- `dev/[task]/` — active task context

See `GEMINI.md` for full integration details.
"""

    with open(gemini_dir / "context.md", "w") as f:
        f.write(context_content)

    return "Gemini CLI configuration generated:\n  - GEMINI.md\n  - .gemini/context.md"
