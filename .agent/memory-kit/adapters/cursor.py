"""
Cursor IDE Adapter — generates .cursor/rules/memory.mdc with auto-attach
"""
from pathlib import Path


def generate(project_root: Path, config: dict) -> str:
    """Generate Cursor IDE configuration."""

    mk_dir = project_root / ".agent" / "memory-kit"
    templates = mk_dir / "templates"
    preprompt = (templates / "preprompt.txt").read_text()
    
    project = config["project"]
    
    # Load architecture content
    arch_file = config.get("architecture", {}).get("file")
    arch_content = ""
    if arch_file:
        arch_path = project_root / arch_file
        if arch_path.exists():
            arch_content = arch_path.read_text()
        else:
            # Fallback to template for backward compatibility / test fixtures
            fallback = project_root / ".agent" / "templates" / "architecture.md"
            if fallback.exists():
                arch_content = fallback.read_text()
    
    conventions = config.get("conventions", [])
    conventions_text = "\n".join(f"- {c}" for c in conventions) if conventions else ""

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
        + arch_content
        + "\n\n"
        "## Conventions\n\n"
        + conventions_text
    )

    cursor_dir = project_root / ".cursor"
    cursor_dir.mkdir(exist_ok=True)
    rules_dir = cursor_dir / "rules"
    rules_dir.mkdir(exist_ok=True)
    (rules_dir / "memory.mdc").write_text(memory_rule)

    # .cursorignore: exclude only generated output dirs, not memory files.
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
