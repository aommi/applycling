"""
Windsurf Adapter — generates .windsurfrules at project root
"""
from pathlib import Path


def generate(project_root: Path, config: dict) -> str:
    """Generate Windsurf configuration."""

    mk_dir = project_root / ".agent" / "memory-kit"
    templates = mk_dir / "templates"
    preprompt = (templates / "preprompt.txt").read_text()
    memory_protocol = (templates / "memory_protocol.md").read_text()
    
    project = config["project"]
    arch_file = config.get("architecture", {}).get("file", "ARCHITECTURE_VISION.md")
    conventions = config.get("conventions", [])
    conventions_md = "\n".join(f"- {c}" for c in conventions) if conventions else ""

    content = (
        f"# Windsurf rules — {project['name']} memory system\n\n"
        "This project uses a file-based memory system to maintain context across sessions.\n"
        "No hook support — memory loading is instruction-driven.\n\n"
        "## Session Startup\n\n"
        "1. Read `memory/semantic.md` ONCE to load project context\n"
        "2. Read `memory/working.md` to understand current task state\n\n"
        "## On Every Turn\n\n"
        + preprompt.strip()
        + "\n\n---\n\n"
        + "## Architecture\n\n"
        + f"Before implementing a feature, read `{arch_file}`. It is the canonical record of architectural principles, product direction, design-decision rationale, and known risks.\n"
        + "\n\n---\n\n"
        + "## Key conventions\n\n"
        + conventions_md
        + "\n"
    )

    (project_root / ".windsurfrules").write_text(content)

    return (
        "Windsurf configuration generated:\n"
        "  - .windsurfrules\n\n"
        "Note: Windsurf has no hook support. Memory loading relies on .windsurfrules being read at session start."
    )
