"""
Cursor IDE Adapter — generates .cursor/rules/memory.mdc with auto-attach
"""
from pathlib import Path


def generate(project_root: Path):
    """Generate Cursor IDE configuration."""

    templates = project_root / ".agent" / "templates"
    preprompt = (templates / "preprompt.txt").read_text()

    # alwaysApply: true means the rule fires every turn — globs is redundant, omit it.
    # Note: {input_key} in the code block below is literal text (not a format field)
    # because we're using string concatenation, not f-strings.
    memory_rule = (
        "---\n"
        "description: Memory system for cross-session context\n"
        "alwaysApply: true\n"
        "---\n\n"
        "# Memory System\n\n"
        "This project uses a file-based memory system. Follow these rules:\n\n"
        "## Session Startup\n\n"
        "1. Read `memory/semantic.md` ONCE at session start to load project context\n"
        "2. Read `memory/working.md` to understand current task state\n\n"
        "## On Every Turn\n\n"
        + preprompt.strip()
        + "\n\n"
        "## Architecture Reference\n\n"
        "- **Skills**: `applycling/skills/<name>/SKILL.md` — prompts with YAML frontmatter;"
        " loader: `load_skill(name).render(**kwargs)`\n"
        "- **Pipeline**: `applycling/pipeline.py` — `PipelineContext`, `PipelineStep`, `PipelineRun`;"
        " linear flow: role_intel → resume_tailor → profile_summary → format_resume →"
        " positioning_brief → cover_letter → email_inmail → fit_summary\n"
        "- **LLM routing**: `applycling/llm.py` — ollama/anthropic/google/openai\n"
        "- **Tracker**: `tracker/__init__.py` — Notion or SQLite via `get_store()`\n\n"
        "## Key Files\n\n"
        "- `memory/semantic.md` — distilled project knowledge (≤500 tokens)\n"
        "- `memory/working.md` — live task state (≤300 tokens)\n"
        "- `DECISIONS.md` — append-only decisions log\n"
        "- `dev/[task]/` — active task context (plan.md, context.md, tasks.md)\n"
        "- `ARCHITECTURE_VISION.md` — canonical architectural reference\n\n"
        "## Conventions\n\n"
        "- API keys in `.env` (gitignored)\n"
        "- `_clean_llm_output()` required for all LLM output\n"
        "- Profile header: `## PROFILE` (all caps)\n"
        "- Skill templates use `str.format` — escape braces with `{{` and `}}`\n"
    )

    cursor_dir = project_root / ".cursor"
    cursor_dir.mkdir(exist_ok=True)
    rules_dir = cursor_dir / "rules"
    rules_dir.mkdir(exist_ok=True)
    (rules_dir / "memory.mdc").write_text(memory_rule)

    # .cursorignore: exclude only generated output dirs, not memory files.
    # Memory files should remain visible to Cursor's AI indexing so the agent
    # can search and reference them directly.
    cursorignore = (
        "# Generated output — not source\n"
        "output/\n"
        ".cursor/history/\n"
    )
    (project_root / ".cursorignore").write_text(cursorignore)

    return (
        "Cursor configuration generated:\n"
        "  - .cursor/rules/memory.mdc (alwaysApply)\n"
        "  - .cursorignore"
    )
