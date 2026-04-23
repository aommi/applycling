"""
Claude Code Adapter — generates CLAUDE.md + .claude/settings.json hooks

Reads project config to produce a project-specific entry-point file.
"""
import json
from pathlib import Path


def generate(project_root: Path, config: dict) -> str:
    """Generate Claude Code configuration.
    
    Args:
        project_root: Path to the target project
        config: Project configuration dict from project.yaml
    """
    project = config["project"]
    mk_dir = project_root / ".agent" / "memory-kit"
    templates = mk_dir / "templates"

    # Write hooks/preprompt.txt
    hooks_dir = project_root / "hooks"
    hooks_dir.mkdir(exist_ok=True)
    (hooks_dir / "preprompt.txt").write_text((templates / "preprompt.txt").read_text())

    # Write hooks/stop.sh and make executable
    stop_path = hooks_dir / "stop.sh"
    stop_path.write_text((templates / "stop.sh").read_text())
    stop_path.chmod(0o755)

    # Generate .claude/settings.json
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

    # Build conventions section
    conventions = config.get("conventions", [])
    conventions_md = "\n".join(f"- {c}" for c in conventions) if conventions else ""
    
    # Build skills section if enabled
    skills = config.get("skills", {})
    skills_md = ""
    if skills.get("enabled"):
        skills_md = f"""\

---

## Skills architecture

All LLM prompt templates live in `{skills.get("directory", "skills/")}<name>/SKILL.md`. There are no prompt strings in Python source files.

Frontmatter is parsed with `pyyaml`. Template engine is plain `str.format` — no Jinja2, no exceptions.
"""

    arch_file = config.get("architecture", {}).get("file", "ARCHITECTURE_VISION.md")

    claude_md = f"""\
# {project["name"]} — Developer Guide

**{project["name"]}** is {project["description"]}

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

Before implementing a feature, read `{arch_file}`. It is the canonical record of architectural principles, product direction, design-decision rationale, and known risks.

To add a new pipeline step, see `{arch_file}` — section "Adding a New Pipeline Step".{skills_md}
---

## Key conventions

{conventions_md}
"""

    (project_root / "CLAUDE.md").write_text(claude_md)

    return (
        "Claude Code configuration generated:\n"
        "  - CLAUDE.md\n"
        "  - .claude/settings.json (hooks merged)\n"
        "  - hooks/preprompt.txt\n"
        "  - hooks/stop.sh"
    )
