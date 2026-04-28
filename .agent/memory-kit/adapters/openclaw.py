"""
OpenClaw Adapter — generates .openclaw-system.md (system prompt include)

OpenClaw has no native project-root file convention. Two install options:
  A) Point OpenClaw at this file via the `system_prompt_file` setting
  B) Paste the file contents directly into OpenClaw's system prompt settings
"""
from pathlib import Path


def generate(project_root: Path, config: dict) -> str:
    """Generate OpenClaw configuration."""

    mk_dir = project_root / ".agent" / "memory-kit"
    templates = mk_dir / "templates"
    preprompt = (templates / "preprompt.txt").read_text()

    project = config["project"]
    arch_file = config.get("architecture", {}).get("file", "vision.md")
    conventions = config.get("conventions", [])
    conventions_md = "\n".join(f"- {c}" for c in conventions) if conventions else ""

    content = (
        f"# OpenClaw system prompt — {project['name']}\n\n"
        "<!--\n"
        "  Install options:\n"
        "    A) system_prompt_file: .openclaw-system.md  (in OpenClaw config)\n"
        "    B) Paste this file's content into OpenClaw's system prompt settings\n"
        "-->\n\n"
        f"You are an agent working in the **{project['name']}** project — {project['description']}\n\n"
        "This project uses a file-based memory system. Treat it as authoritative.\n\n"
        "## Startup (read in order)\n\n"
        "1. `memory/semantic.md` — distilled project knowledge (≤500 lines); read ONCE per session\n"
        "2. `memory/working.md` — live task state; read before every response\n\n"
        "## On Every Turn\n\n"
        + preprompt.strip()
        + "\n\n---\n\n"
        + "## Architecture\n\n"
        + f"Before implementing a feature, read `{arch_file}`. It is the canonical record of architectural principles, product direction, design-decision rationale, and known risks.\n"
        + "\n\n---\n\n"
        + "## Key conventions\n\n"
        + conventions_md
        + "\n\n---\n\n"
        + "## Memory Discipline\n\n"
        "- `memory/semantic.md` — propose updates; wait for approval before writing\n"
        "- `memory/working.md` — update freely after each response; no approval needed\n"
        "- `DECISIONS.md` — append-only; propose entries for approval\n"
        "- `dev/[task]/context.md` — log confirmed assumptions immediately; no approval needed\n"
    )

    (project_root / ".openclaw-system.md").write_text(content)

    return (
        "OpenClaw configuration generated:\n"
        "  - .openclaw-system.md\n\n"
        "Install options:\n"
        "  A) Set system_prompt_file: .openclaw-system.md in OpenClaw config\n"
        "  B) Paste the file contents into OpenClaw's system prompt settings"
    )
