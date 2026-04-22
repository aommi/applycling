"""
Windsurf Adapter — generates .windsurfrules at project root
"""
from pathlib import Path


def generate(project_root: Path):
    """Generate Windsurf configuration."""

    templates = project_root / ".agent" / "templates"
    preprompt = (templates / "preprompt.txt").read_text()
    arch = (templates / "architecture.md").read_text()

    content = (
        "# Windsurf rules — applycling memory system\n\n"
        "This project uses a file-based memory system to maintain context across sessions.\n"
        "No hook support — memory loading is instruction-driven.\n\n"
        "## Session Startup\n\n"
        "1. Read `memory/semantic.md` ONCE to load project context\n"
        "2. Read `memory/working.md` to understand current task state\n\n"
        "## On Every Turn\n\n"
        + preprompt.strip()
        + "\n\n---\n\n"
        + arch
        + "\n"
    )

    (project_root / ".windsurfrules").write_text(content)

    return (
        "Windsurf configuration generated:\n"
        "  - .windsurfrules\n\n"
        "Note: Windsurf has no hook support. Memory loading relies on .windsurfrules being read at session start."
    )
