"""
Gemini CLI Adapter — generates GEMINI.md + sub-directory context files
"""
from pathlib import Path


def generate(project_root: Path):
    """Generate Gemini CLI configuration."""

    templates = project_root / ".agent" / "templates"
    preprompt = (templates / "preprompt.txt").read_text()
    arch = (templates / "architecture.md").read_text()

    gemini_md = (
        "# Project Context — applycling\n\n"
        "**applycling** is a CLI tool that turns a job URL into a complete application package:"
        " tailored resume, cover letter, positioning brief, email/InMail, and fit summary.\n\n"
        "---\n\n"
        "## Memory System\n\n"
        "This project uses a file-based memory system to maintain context across sessions.\n\n"
        "### Session Startup\n\n"
        "Read `memory/semantic.md` ONCE to load project context.\n\n"
        "### On Every Turn\n\n"
        + preprompt.strip()
        + "\n\n---\n\n"
        + arch
        + "\n"
    )

    (project_root / "GEMINI.md").write_text(gemini_md)

    gemini_dir = project_root / ".gemini"
    gemini_dir.mkdir(exist_ok=True)

    context = (
        "# Gemini CLI Context\n\n"
        "This project uses a shared memory system in the `memory/` directory:\n\n"
        "- `memory/semantic.md` — project knowledge (read at session start)\n"
        "- `memory/working.md` — current task state (read every turn)\n"
        "- `dev/[task]/` — active task context\n\n"
        "See `GEMINI.md` for full integration details.\n"
    )

    (gemini_dir / "context.md").write_text(context)

    return "Gemini CLI configuration generated:\n  - GEMINI.md\n  - .gemini/context.md"
