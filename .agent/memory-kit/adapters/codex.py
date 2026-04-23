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
    arch_file = config.get("architecture", {}).get("file", "ARCHITECTURE_VISION.md")
    arch_ref_note = config.get("architecture", {}).get("reference_note", "")
    arch_extra = f"\n{arch_ref_note}" if arch_ref_note else ""
    conventions = config.get("conventions", [])
    conventions_md = "\n".join(f"- {c}" for c in conventions) if conventions else ""

    content = (
        f"# Project Context — {project['name']}\n\n"
        f"**{project['name']}** is {project['description']}\n\n"
        f"---\n\n"
        + memory_protocol.strip()
        + "\n\n---\n\n"
        + f"## Architecture\n\n"
        + f"Before implementing a feature, read `{arch_file}`. It is the canonical record of architectural principles, product direction, design-decision rationale, and known risks.{arch_extra}"
        + "\n\n---\n\n"
        + "## Key conventions\n\n"
        + conventions_md
        + "\n"
    )

    (project_root / "AGENTS.md").write_text(content)

    return (
        "Codex configuration generated:\n"
        "  - AGENTS.md\n\n"
        "Note: Codex does not support hooks. Memory loading relies on the agent reading AGENTS.md at session start.\n"
        "Note: If you also use Hermes, run `generate.py hermes` instead — the hermes AGENTS.md is a superset."
    )
