"""
Claude Code Adapter — generates CLAUDE.md + .claude/settings.json hooks

CLAUDE.md structure:
  [project header — written once on first create, never touched again]

  <!-- amk:start -->
  [generic memory protocol — updated by amk on regen]
  <!-- amk:end -->

  [anything the user adds below stays untouched]
"""
import difflib
import json
from pathlib import Path

SENTINEL_START = "<!-- amk:start -->"
SENTINEL_END = "<!-- amk:end -->"

MANAGED_CONTENT_TEMPLATE = """\
## Memory System (Session Startup + Hooks)

**On session start:** Read `memory/semantic.md` ONCE to load project context.

**On every turn:** The preprompt hook (`hooks/preprompt.txt`) handles reading `memory/working.md`.

**Task files:** Only load `/dev/[task]/*` files when actively working on that task.

**MCP efficiency:** Before calling any MCP tool to retrieve information, first check if that information might exist in `memory/semantic.md` or `dev/[task]/context.md` — local files are cheaper than remote MCP queries.

**Keep context minimal:** Do not speculatively load files "just in case".

**Mid-session drift:** If reasoning becomes uncertain or inconsistent with prior context, re-read `memory/semantic.md` before continuing.

---

## Architecture vision

Before implementing a feature, read `{arch_file}`. It is the canonical record of architectural principles, product direction, design-decision rationale, and known risks."""


def _write_managed_section(claude_md_path: Path, header: str, content: str) -> str:
    """Insert or replace the amk-managed block in CLAUDE.md.

    On first create: writes header (outside sentinel) + managed block.
    On re-run with sentinels present: replaces only the managed block.
    On file exists but no sentinels: appends the managed block.

    Returns a human-readable status line.
    """
    block = f"{SENTINEL_START}\n{content}\n{SENTINEL_END}\n"

    if not claude_md_path.exists():
        claude_md_path.write_text(f"{header}\n\n{block}")
        return "  - CLAUDE.md (created)"

    existing = claude_md_path.read_text()
    start_idx = existing.find(SENTINEL_START)
    end_idx = existing.find(SENTINEL_END)

    if start_idx == -1 or end_idx == -1 or end_idx < start_idx:
        sep = "\n" if existing.endswith("\n") else "\n\n"
        claude_md_path.write_text(existing + sep + block)
        return "  - CLAUDE.md (amk section appended — existing content preserved)"

    old_block = existing[start_idx : end_idx + len(SENTINEL_END)]
    new_block = block.rstrip("\n")

    if old_block == new_block:
        return "  - CLAUDE.md (unchanged)"

    updated = existing[:start_idx] + block + existing[end_idx + len(SENTINEL_END) :].lstrip("\n")
    claude_md_path.write_text(updated)

    diff_lines = list(
        difflib.unified_diff(
            old_block.splitlines(keepends=True),
            new_block.splitlines(keepends=True),
            fromfile="CLAUDE.md (before)",
            tofile="CLAUDE.md (after)",
        )
    )
    return f"  - CLAUDE.md (amk section updated)\n{''.join(diff_lines)}"


def generate(project_root: Path, config: dict) -> str:
    """Generate Claude Code configuration."""
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
            {"hooks": [{"type": "command", "command": 'cat "$CLAUDE_PROJECT_DIR/hooks/preprompt.txt"'}]}
        ],
        "Stop": [
            {"hooks": [{"type": "command", "command": 'bash "$CLAUDE_PROJECT_DIR/hooks/stop.sh"'}]}
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

    arch_file = config.get("architecture", {}).get("file", "ARCHITECTURE_VISION.md")
    managed_content = MANAGED_CONTENT_TEMPLATE.format(arch_file=arch_file)

    # Project header — written once on first create, never regenerated
    header = f"# {project['name']} — Developer Guide\n\n**{project['name']}** is {project['description']}"

    claude_md_status = _write_managed_section(
        project_root / "CLAUDE.md", header, managed_content
    )

    return (
        "Claude Code configuration generated:\n"
        f"{claude_md_status}\n"
        "  - .claude/settings.json (hooks merged)\n"
        "  - hooks/preprompt.txt\n"
        "  - hooks/stop.sh"
    )
