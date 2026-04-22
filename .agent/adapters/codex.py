"""
OpenAI Codex Adapter — generates AGENTS.md (hooks not supported)
"""
from pathlib import Path

def generate(project_root: Path):
    """Generate OpenAI Codex configuration."""

    # Read the shared preprompt to incorporate into AGENTS.md
    preprompt_path = project_root / ".agent" / "templates" / "preprompt.txt"
    with open(preprompt_path, "r") as f:
        preprompt_content = f.read()

    agents_md_content = f"""# Project Context — applycling

**applycling** is a CLI tool that turns a job URL into a complete application package: tailored resume, cover letter, positioning brief, email/InMail, and fit summary.

---

## Memory System

This project uses a file-based memory system to maintain context across sessions.

### On Session Start

Read `memory/semantic.md` ONCE to load project context before answering.

### On Every Turn

{preprompt_content.strip()}

---

## Architecture

Before implementing a feature, read `ARCHITECTURE_VISION.md`. It is the canonical record of architectural principles.

### Skills Architecture

All LLM prompt templates live in `applycling/skills/<name>/SKILL.md` with YAML frontmatter:

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
Prompt body using {{input_key}}.
```

Loader: `from applycling.skills import load_skill` → `load_skill(name).render(**kwargs)`

### Tracker

`get_store()` in `tracker/__init__.py` auto-detects Notion or SQLite. Use the `TrackerStore` interface — never call stores directly.

---

## Key Conventions

- All API keys in `.env` (gitignored)
- `_clean_llm_output()` strips code fences from LLM output
- Profile header: `## PROFILE` (all caps)
- `storage.save_config()` merges — don't call with partial keys
- Skill templates use `str.format` — escape braces with `{{` and `}}`
- Conditional logic stays in Python, not skills
"""

    with open(project_root / "AGENTS.md", "w") as f:
        f.write(agents_md_content)

    return "Codex configuration generated:\n  - AGENTS.md\n\nNote: Codex does not support hooks. Memory loading relies on the agent reading AGENTS.md at session start."
