"""
OpenClaw Adapter — generates .openclaw-system.md (system prompt include)

OpenClaw has no native project-root file convention. Two install options:
  A) Point OpenClaw at this file via the `system_prompt_file` setting
  B) Paste the file contents directly into OpenClaw's system prompt settings
"""
from pathlib import Path


def generate(project_root: Path):
    """Generate OpenClaw configuration."""

    templates = project_root / ".agent" / "templates"
    preprompt = (templates / "preprompt.txt").read_text()
    arch = (templates / "architecture.md").read_text()

    content = (
        "# OpenClaw system prompt — applycling\n\n"
        "<!--\n"
        "  Install options:\n"
        "    A) system_prompt_file: .openclaw-system.md  (in OpenClaw config)\n"
        "    B) Paste this file's content into OpenClaw's system prompt settings\n"
        "-->\n\n"
        "You are an agent working in the **applycling** project — a CLI tool that turns a job URL\n"
        "into a complete application package (resume, cover letter, positioning brief, email, fit summary).\n\n"
        "This project uses a file-based memory system. Treat it as authoritative.\n\n"
        "## Startup (read in order)\n\n"
        "1. `memory/semantic.md` — distilled project knowledge (≤500 tokens); read ONCE per session\n"
        "2. `memory/working.md` — live task state; read before every response\n\n"
        "## On Every Turn\n\n"
        + preprompt.strip()
        + "\n\n---\n\n"
        + arch
        + "\n\n---\n\n"
        "## Memory Discipline\n\n"
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
