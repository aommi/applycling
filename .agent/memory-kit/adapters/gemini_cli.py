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

    gemini_md = (
        f"# Project Context — {project['name']}\n\n"
        f"**{project['name']}** is {project['description']}\n\n"
        f"---\n\n"
        + memory_protocol.strip()
        + "\n\n---\n\n"
        + "## Architecture\n\n"
        + arch_content
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
