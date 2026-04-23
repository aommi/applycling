"""
Hermes Agent Adapter — generates AGENTS.md (superset of the Codex adapter)

Hermes (Nous Research) reads AGENTS.md as workspace-level context and supports
the agentskills.io skill frontmatter standard natively via its /skills browser.

NOTE: Both this adapter and the Codex adapter write AGENTS.md. This version is
a superset. Codex reads the result fine. If you run both agents, use this adapter
(or run `generate.py all`, which runs codex then hermes so hermes wins).
"""
from pathlib import Path


def generate(project_root: Path, config: dict) -> str:
    """Generate Hermes Agent configuration."""

    mk_dir = project_root / ".agent" / "memory-kit"
    templates = mk_dir / "templates"
    preprompt = (templates / "preprompt.txt").read_text()
    memory_protocol = (templates / "memory_protocol.md").read_text()
    
    project = config["project"]
    skills = config.get("skills", {})
    
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
    
    # Hermes-specific skills note
    skills_note = ""
    if skills.get("enabled") and skills.get("standard"):
        skills_note = (
            f"\nThese skill files follow the {skills['standard']} standard —"
            " Hermes's `/skills` browser can enumerate them natively.\n"
        )
        # Insert after the first paragraph in arch content if possible
        if "Loader:" in arch_content and skills_note:
            arch_content = arch_content.replace(
                "Loader:",
                f"Loader: {skills_note.strip()}\n\nLoader:",
                1
            )
            skills_note = ""  # Already inserted

    hermes_footer = (
        "---\n\n"
        "## Optional: Hermes Memory Mirroring\n\n"
        "Hermes has its own `MEMORY.md` / `USER.md` persistence layer. These are complementary,\n"
        "not replacements, for this project's `memory/` files. If you want high-signal lessons\n"
        "visible inside Hermes's built-in persistence, you can symlink:\n\n"
        "```bash\n"
        "ln -s memory/semantic.md MEMORY.md\n"
        "```\n\n"
        "The project's `memory/semantic.md` remains the single source of truth.\n"
    )

    content = (
        f"# Project Context — {project['name']}\n\n"
        f"**{project['name']}** is {project['description']}\n\n"
        f"---\n\n"
        + memory_protocol.strip()
        + "\n\n---\n\n"
        + "## Architecture\n\n"
        + arch_content
        + (skills_note if skills_note else "")
        + "\n\n"
        + hermes_footer
    )

    (project_root / "AGENTS.md").write_text(content)

    return (
        "Hermes configuration generated:\n"
        "  - AGENTS.md (superset — also readable by Codex)\n\n"
        "Note: Hermes reads AGENTS.md natively."
    )
