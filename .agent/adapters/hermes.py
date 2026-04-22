"""
Hermes Agent Adapter — generates AGENTS.md (superset of the Codex adapter)

Hermes (Nous Research) reads AGENTS.md as workspace-level context and supports
the agentskills.io skill frontmatter standard natively via its /skills browser.

NOTE: Both this adapter and the Codex adapter write AGENTS.md. This version is
a superset — it adds the agentskills.io note and optional Hermes memory mirroring.
Codex reads the result fine. If you run both agents, use this adapter (or run
`generate.py all`, which runs codex then hermes so hermes wins).
"""
from pathlib import Path


def generate(project_root: Path):
    """Generate Hermes Agent configuration."""

    templates = project_root / ".agent" / "templates"
    preprompt = (templates / "preprompt.txt").read_text()
    arch = (templates / "architecture.md").read_text()

    # Hermes-specific note inserted after the Skills section
    hermes_skills_note = (
        "\nThese skill files follow the agentskills.io frontmatter shape —"
        " Hermes's `/skills` browser can enumerate them natively.\n"
    )

    # Insert the note after the "Loader:" line in the architecture block
    arch_with_note = arch.replace(
        "Loader: `from applycling.skills import load_skill` → `load_skill(name).render(**kwargs)`",
        "Loader: `from applycling.skills import load_skill` → `load_skill(name).render(**kwargs)`"
        + hermes_skills_note,
    )

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
        "# Project Context — applycling\n\n"
        "**applycling** is a CLI tool that turns a job URL into a complete application package:"
        " tailored resume, cover letter, positioning brief, email/InMail, and fit summary."
        " Supports Anthropic (Claude), Google AI Studio (Gemini), Ollama, and OpenAI.\n\n"
        "---\n\n"
        "## Memory System\n\n"
        "This project uses a file-based memory system to maintain context across sessions.\n\n"
        "### On Session Start\n\n"
        "Read `memory/semantic.md` ONCE to load project context before answering.\n\n"
        "### On Every Turn\n\n"
        + preprompt.strip()
        + "\n\n---\n\n"
        + arch_with_note
        + "\n\n"
        + hermes_footer
    )

    (project_root / "AGENTS.md").write_text(content)

    return (
        "Hermes configuration generated:\n"
        "  - AGENTS.md (superset — also readable by Codex)\n\n"
        "Note: Hermes reads AGENTS.md natively. Skills in applycling/skills/ follow\n"
        "the agentskills.io frontmatter shape and are browsable via Hermes's /skills."
    )
