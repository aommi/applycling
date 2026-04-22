"""
Cursor IDE Adapter — generates .cursor/rules/memory.mdc with auto-attach globs
"""
from pathlib import Path

def generate(project_root: Path):
    """Generate Cursor IDE configuration."""

    cursor_dir = project_root / ".cursor"
    cursor_dir.mkdir(exist_ok=True)
    rules_dir = cursor_dir / "rules"
    rules_dir.mkdir(exist_ok=True)

    # Read the shared preprompt
    preprompt_path = project_root / ".agent" / "templates" / "preprompt.txt"
    with open(preprompt_path, "r") as f:
        preprompt_content = f.read()

    # Cursor rule with auto-attach globs
    memory_rule_content = f"""---
description: Memory system for cross-session context
globs: **/*
alwaysApply: true
---

# Memory System

This project uses a file-based memory system. Follow these rules:

## Session Startup

1. Read `memory/semantic.md` ONCE at session start to load project context
2. Read `memory/working.md` to understand current task state

## On Every Turn

{preprompt_content.strip()}

## Architecture Reference

- **Skills**: `applycling/skills/<name>/SKILL.md` — prompts with YAML frontmatter
- **Pipeline**: `applycling/pipeline.py` — library API for URL→package flow
- **LLM routing**: `applycling/llm.py` — ollama/anthropic/google/openai
- **Tracker**: `tracker/__init__.py` — Notion or SQLite via `get_store()`

## Key Files

- `memory/semantic.md` — distilled project knowledge (≤500 tokens)
- `memory/working.md` — live task state (≤300 tokens)
- `DECISIONS.md` — append-only decisions log
- `dev/[task]/` — active task context (plan.md, context.md, tasks.md)
- `ARCHITECTURE_VISION.md` — canonical architectural reference

## Conventions

- API keys in `.env` (gitignored)
- `_clean_llm_output()` required for all LLM output
- Profile header: `## PROFILE` (all caps)
- Skill templates use `str.format` — escape braces with `{{` and `}}`
"""

    with open(rules_dir / "memory.mdc", "w") as f:
        f.write(memory_rule_content)

    # Generate a .cursorignore to prevent memory files from appearing in code search
    cursorignore_content = """# Memory files — context only, not code
memory/semantic.md
memory/working.md
dev/*/context.md
"""

    with open(project_root / ".cursorignore", "w") as f:
        f.write(cursorignore_content)

    return "Cursor configuration generated:\n  - .cursor/rules/memory.mdc (auto-attach)\n  - .cursorignore"
