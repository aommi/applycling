"""
Gemini CLI Adapter — generates GEMINI.md + sub-directory context files
"""
from pathlib import Path


def generate(project_root: Path, config: dict) -> str:
    """Generate Gemini CLI configuration."""

    mk_dir = project_root / ".agent" / "memory-kit"
    templates = mk_dir / "templates"
    preprompt = (templates / "preprompt.txt").read_text()
    memory_protocol = (templates / "memory_protocol.md").read_text()
    
    project = config["project"]
    arch_file = config.get("architecture", {}).get("file", "ARCHITECTURE_VISION.md")
    conventions = config.get("conventions", [])
    conventions_md = "\n".join(f"- {c}" for c in conventions) if conventions else ""

    gemini_md = (
        f"# Project Context — {project['name']}\n\n"
        f"**{project['name']}** is {project['description']}\n\n"
        f"---\n\n"
        + memory_protocol.strip()
        + "\n\n---\n\n"
        + "## Architecture\n\n"
        + f"Before implementing a feature, read `{arch_file}`. It is the canonical record of architectural principles, product direction, design-decision rationale, and known risks.\n"
        + "\n\n---\n\n"
        + "## Key conventions\n\n"
        + conventions_md
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
