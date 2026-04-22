"""
OpenAI Codex Adapter — generates AGENTS.md (hooks not supported)

Note: Hermes also reads AGENTS.md. The hermes adapter produces a superset of this
file (adds agentskills.io note). If you use both Codex and Hermes, run the hermes
adapter (or `generate.py all`) — Codex reads the hermes version fine.
"""
from pathlib import Path


def generate(project_root: Path):
    """Generate OpenAI Codex configuration."""

    templates = project_root / ".agent" / "templates"
    preprompt = (templates / "preprompt.txt").read_text()
    arch = (templates / "architecture.md").read_text()

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
        + arch
        + "\n"
    )

    (project_root / "AGENTS.md").write_text(content)

    return (
        "Codex configuration generated:\n"
        "  - AGENTS.md\n\n"
        "Note: Codex does not support hooks. Memory loading relies on the agent reading AGENTS.md at session start.\n"
        "Note: If you also use Hermes, run `generate.py hermes` instead — the hermes AGENTS.md is a superset."
    )
