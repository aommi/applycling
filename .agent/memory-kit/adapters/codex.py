"""
OpenAI Codex Adapter — generates AGENTS.md (hooks not supported)

Note: Hermes also reads AGENTS.md. The hermes adapter produces a superset.
If you use both Codex and Hermes, run the hermes adapter (or `generate.py all`).
"""
from pathlib import Path


def generate(project_root: Path, config: dict) -> str:
    """Generate OpenAI Codex configuration."""

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

    content = (
        f"# Project Context — {project['name']}\n\n"
        f"**{project['name']}** is {project['description']}\n\n"
        f"---\n\n"
        + memory_protocol.strip()
        + "\n\n---\n\n"
        + f"## Architecture\n\n{arch_content}"
        + "\n"
    )

    (project_root / "AGENTS.md").write_text(content)

    return (
        "Codex configuration generated:\n"
        "  - AGENTS.md\n\n"
        "Note: Codex does not support hooks. Memory loading relies on the agent reading AGENTS.md at session start.\n"
        "Note: If you also use Hermes, run `generate.py hermes` instead — the hermes AGENTS.md is a superset."
    )
