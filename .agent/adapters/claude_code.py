"""
Claude Code Adapter — generates CLAUDE.md + .claude/settings.json hooks
"""
import json
from pathlib import Path


def generate(project_root: Path):
    """Generate Claude Code configuration."""

    templates = project_root / ".agent" / "templates"

    # Write hooks/preprompt.txt
    hooks_dir = project_root / "hooks"
    hooks_dir.mkdir(exist_ok=True)
    (hooks_dir / "preprompt.txt").write_text((templates / "preprompt.txt").read_text())

    # Write hooks/stop.sh and make executable
    stop_path = hooks_dir / "stop.sh"
    stop_path.write_text((templates / "stop.sh").read_text())
    stop_path.chmod(0o755)

    # Generate .claude/settings.json
    # Merge per-event: preserve any hook events we don't own (e.g. PreToolUse),
    # but replace our own events (UserPromptSubmit, Stop) with the current config.
    claude_dir = project_root / ".claude"
    claude_dir.mkdir(exist_ok=True)
    settings_path = claude_dir / "settings.json"

    our_hooks = {
        "UserPromptSubmit": [
            {"hooks": [{"type": "command", "command": "cat hooks/preprompt.txt"}]}
        ],
        "Stop": [
            {"hooks": [{"type": "command", "command": "bash hooks/stop.sh"}]}
        ],
    }

    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text())
        except (json.JSONDecodeError, OSError):
            existing = {}
    else:
        existing = {}

    existing.setdefault("hooks", {}).update(our_hooks)

    settings_path.write_text(json.dumps(existing, indent=2) + "\n")

    # Generate CLAUDE.md
    # This is the project constitution — kept as a plain string (not f-string)
    # so {{ / }} in the skill example render correctly without extra escaping.
    claude_md = """\
# applycling — Developer Guide

**applycling** is a CLI tool that turns a job URL into a complete application package: tailored resume, cover letter, positioning brief, email/InMail, and fit summary. Supports Anthropic (Claude), Google AI Studio (Gemini), and Ollama (local/cloud).

---

## Memory System (Session Startup + Hooks)

**On session start:** Read `memory/semantic.md` ONCE to load project context.

**On every turn:** The preprompt hook (`hooks/preprompt.txt`) handles reading `memory/working.md`.

**Task files:** Only load `/dev/[task]/*` files when actively working on that task.

**MCP efficiency:** Before calling any MCP tool to retrieve information, first check if that information might exist in `memory/semantic.md` or `dev/[task]/context.md` — local files are cheaper than remote MCP queries.

**Keep context minimal:** Do not speculatively load files "just in case".

**Mid-session drift:** If reasoning becomes uncertain or inconsistent with prior context, re-read `memory/semantic.md` before continuing.

---

## Architecture vision

Before implementing a feature, read `ARCHITECTURE_VISION.md`. It is the canonical record of architectural principles (thin harness + fat skills), product direction, design-decision rationale, and known risks. Tickets expire; this document does not. Use it to understand *why* the codebase looks the way it does before changing it.

To add a new pipeline step, see `ARCHITECTURE_VISION.md` — section "Adding a New Pipeline Step".

---

## Skills architecture

All LLM prompt templates live in `applycling/skills/<name>/SKILL.md`. There are no prompt strings in Python source files.

### Skill file format

```markdown
---
name: skill_name          # must match the directory name exactly
description: One-line purpose
inputs:
  - placeholder_one       # every {placeholder} used in the body must be listed
  - placeholder_two
output_file: result.md    # optional — omit if the step writes no file
model_hint: claude-3-5-haiku-20241022   # optional (T8)
temperature: 0.3          # optional (T8)
---
Prompt body. Uses {placeholder_one} and {placeholder_two} via str.format.

Use {{literal_braces}} when the output must contain a literal { or }.
```

Frontmatter is parsed with `pyyaml`. Template engine is plain `str.format` — no Jinja2, no exceptions.

### Loader

`load_skill(name)` → `Skill` with `.render(**kwargs)`. Import: `from applycling.skills import load_skill, Skill, SkillError`. Raises `SkillError` if the `name` field in frontmatter doesn't match the directory name.

---

## Tracker abstraction

`get_store()` in `tracker/__init__.py` auto-detects Notion or falls back to SQLite. All tracker calls go through the `TrackerStore` interface. Never call Notion or SQLite directly from `cli.py`.

---

## Key conventions

- `_clean_llm_output()` strips code fences, preamble, leaked prompt markers, and trailing sign-offs from all LLM output. Always apply it.
- `_profile_header_markdown()` builds the static name/contact block from `profile.json`. Never let the LLM write this section.
- The profile summary section header must be `## PROFILE` (all caps) to match the format template.
- `storage.save_config()` merges — never call it with only partial keys unless merging is the intent.
- All API keys live in `.env` at repo root (gitignored). Loaded via `python-dotenv` in `llm.py`.
- **Escaped braces in skill files:** `{{` and `}}` render as literal `{`/`}` after `str.format`. Do not use `\\{` — invalid syntax.
- **Conditional logic stays in Python:** Skill templates have no `if/else`. The caller pre-computes conditional strings and passes them as inputs.
- **No Jinja2:** The template engine is `str.format`. If logic is complex, move it to the Python caller.
- **Keep `ARCHITECTURE_VISION.md` canonical.** Update it in the same commit whenever you: add or remove a skill, change the pipeline contract (`_Step`, `PipelineStep`, `load_skill`), introduce a new provider, ship a T-numbered phase, or discover a risk worth remembering. When in doubt, update it.
"""

    (project_root / "CLAUDE.md").write_text(claude_md)

    return (
        "Claude Code configuration generated:\n"
        "  - CLAUDE.md\n"
        "  - .claude/settings.json (hooks merged)\n"
        "  - hooks/preprompt.txt\n"
        "  - hooks/stop.sh"
    )
