"""
Windsurf Adapter — generates .windsurfrules at project root
"""
from pathlib import Path


def generate(project_root: Path):
    """Generate Windsurf configuration."""

    preprompt_path = project_root / ".agent" / "templates" / "preprompt.txt"
    with open(preprompt_path, "r") as f:
        preprompt_content = f.read()

    windsurfrules_content = f"""# Windsurf rules — applycling memory system

This project uses a file-based memory system to maintain context across sessions.
No hook support — memory loading is instruction-driven.

## Session Startup

1. Read `memory/semantic.md` ONCE to load project context
2. Read `memory/working.md` to understand current task state

## On Every Turn

{preprompt_content.strip()}

## Architecture Reference

- **Skills**: `applycling/skills/<name>/SKILL.md` — prompts with YAML frontmatter, loaded via `load_skill(name)`
- **Pipeline**: `applycling/pipeline.py` — `PipelineContext`, `PipelineStep`, `PipelineRun`; linear flow: role_intel → resume_tailor → profile_summary → format_resume → positioning_brief → cover_letter → email_inmail → fit_summary
- **LLM routing**: `applycling/llm.py` — supports ollama, anthropic, google, openai; keys in `.env`
- **Tracker**: `tracker/__init__.py` — `get_store()` auto-detects Notion or SQLite; use `TrackerStore` interface only

## Key Files

| File | Purpose |
|------|---------|
| `memory/semantic.md` | Distilled project knowledge (≤500 tokens) |
| `memory/working.md` | Live task state (≤300 tokens) |
| `DECISIONS.md` | Append-only decisions log |
| `dev/[task]/` | Active task context (plan.md, context.md, tasks.md) |
| `ARCHITECTURE_VISION.md` | Canonical architectural reference — read before implementing |

## Key Conventions

- `_clean_llm_output()` strips code fences from all LLM output — always apply it
- Profile header: `## PROFILE` (all caps)
- `storage.save_config()` merges — don't call with partial keys
- Skill templates use `str.format` — escape braces with `{{{{` and `}}}}`
- Conditional logic stays in Python, not skill templates
- All API keys in `.env` (gitignored), loaded via `python-dotenv`
"""

    with open(project_root / ".windsurfrules", "w") as f:
        f.write(windsurfrules_content)

    return "Windsurf configuration generated:\n  - .windsurfrules\n\nNote: Windsurf has no hook support. Memory loading relies on .windsurfrules being read at session start."
