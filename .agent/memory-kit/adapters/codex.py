"""
OpenAI Codex Adapter — generates AGENTS.md (hooks not supported)

AGENTS.md structure:
  [project header — written once on first create, never touched again]

  <!-- amk:start -->
  [managed memory protocol + architecture ref + conventions]
  <!-- amk:end -->

  [custom content outside sentinels is preserved across regenerations]

Note: Hermes also reads AGENTS.md. The hermes adapter produces a superset
(with skills note + memory mirroring footer). If you use both Codex and Hermes,
run the hermes adapter (or `generate.py all`, which runs codex then hermes so
hermes wins).
"""
import difflib
from pathlib import Path


SENTINEL_START = "<!-- amk:start -->"
SENTINEL_END = "<!-- amk:end -->"


_MANAGED_TEMPLATE = """\
## Memory System

This project uses a file-based memory system to maintain context across sessions.

### On Session Start

Read `memory/semantic.md` ONCE to load project context before answering.

### On Every Turn

The preprompt hook handles reading `memory/working.md`.

### Task Files

Only load `/dev/[task]/*` files when actively working on that task.

### MCP Efficiency

Before calling any MCP tool to retrieve information, first check if that information might exist in `memory/semantic.md` or `dev/[task]/context.md` — local files are cheaper than remote MCP queries.

### Keep Context Minimal

Do not speculatively load files "just in case".

### Mid-Session Drift

If reasoning becomes uncertain or inconsistent with prior context, re-read `memory/semantic.md` before continuing.

### Memory Discipline

- `memory/semantic.md` — current build state; propose updates; wait for approval before writing
- `memory/working.md` — live task state; update freely after each response; no approval needed
- `DECISIONS.md` — append-only log of architectural decisions; propose entries for approval
- `{arch_file}` — principles, load-bearing assumptions, planned capabilities; update only on merge when a capability ships or an assumption is invalidated; **never put current state here** (that's `semantic.md`), **never put planning details here** (tickets, checklists, phases)
- `dev/[task]/context.md` — log confirmed assumptions immediately; no approval needed

**DECISIONS.md vs. Assumptions distinction:**
- `DECISIONS.md` = immutable log — "we chose X on date Y because Z" — never edited, only superseded by appending
- `{arch_file}` Assumptions = live load-bearing premises — mutable; when invalidated, append a supersession to `DECISIONS.md` first, then update the assumption

**On PR merge:** check `{arch_file}` — move shipped capabilities to `memory/semantic.md` and remove them from the Vision section; append a supersession to `DECISIONS.md` then update or remove any invalidated Assumption.

---

## Architecture

Before implementing a feature, read `{arch_file}`. It is the canonical record of architectural principles, load-bearing assumptions, and planned capabilities — not current build state (that lives in `memory/semantic.md`).

---

## Key conventions

{conventions_md}
"""


def _write_managed_section(agents_md_path: Path, header: str, content: str) -> str:
    """Insert or replace the amk-managed block in AGENTS.md.

    On first create: writes header (outside sentinel) + managed block.
    On re-run with sentinels present: replaces only the managed block.
    On file exists but no sentinels: appends the managed block after existing content.

    Returns a human-readable status line.
    """
    block = f"{SENTINEL_START}\n{content.rstrip()}\n{SENTINEL_END}\n"

    if not agents_md_path.exists():
        agents_md_path.write_text(f"{header}\n\n{block}")
        return "  - AGENTS.md (created)"

    existing = agents_md_path.read_text()
    start_idx = existing.find(SENTINEL_START)
    end_idx = existing.find(SENTINEL_END)

    if start_idx == -1 or end_idx == -1 or end_idx < start_idx:
        # No sentinels — append managed block at end, preserving everything
        sep = "\n" if existing.endswith("\n") else "\n\n"
        agents_md_path.write_text(existing + sep + block)
        return "  - AGENTS.md (amk section appended — existing content preserved)"

    old_block = existing[start_idx : end_idx + len(SENTINEL_END)]
    new_block = block.rstrip("\n")

    if old_block == new_block:
        return "  - AGENTS.md (unchanged)"

    # Replace only the managed block; preserve header + custom content
    after = existing[end_idx + len(SENTINEL_END):]
    if after.startswith("\n"):
        after = after[1:]
    updated = existing[:start_idx] + block + after
    agents_md_path.write_text(updated)

    diff_lines = list(
        difflib.unified_diff(
            old_block.splitlines(keepends=True),
            new_block.splitlines(keepends=True),
            fromfile="AGENTS.md (before)",
            tofile="AGENTS.md (after)",
        )
    )
    return f"  - AGENTS.md (amk section updated)\n{''.join(diff_lines)}"


def generate(project_root: Path, config: dict) -> str:
    """Generate OpenAI Codex configuration (AGENTS.md with sentinel preservation).

    The managed block (memory protocol + architecture ref + conventions) is
    wrapped in <!-- amk:start/end --> sentinels. Custom content outside those
    blocks is preserved across regenerations.
    """
    project = config["project"]
    arch_file = config.get("architecture", {}).get("file", "vision.md")
    conventions = config.get("conventions", [])
    conventions_md = (
        "\n".join(f"- {c}" for c in conventions) if conventions else ""
    )

    managed_content = _MANAGED_TEMPLATE.format(
        arch_file=arch_file,
        conventions_md=conventions_md,
    )

    header = (
        f"# Project Context — {project['name']}\n\n"
        f"**{project['name']}** is {project['description']}"
    )

    agents_md_status = _write_managed_section(
        project_root / "AGENTS.md", header, managed_content
    )

    return (
        "Codex configuration generated:\n"
        f"{agents_md_status}\n\n"
        "Note: Codex does not support hooks. Memory loading relies on the agent reading AGENTS.md at session start.\n"
        "Note: If you also use Hermes, run `generate.py hermes` instead — the hermes AGENTS.md is a superset.\n"
        "  Custom content outside <!-- amk:start/end --> is preserved."
    )
