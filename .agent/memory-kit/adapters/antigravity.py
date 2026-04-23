"""
Antigravity Adapter — generates .agents/rules/ and .agents/workflows/

Google Antigravity supports workspace-specific Rules and Workflows as markdown
files in .agents/rules/ and .agents/workflows/. Rules can be Always On, Manual,
Model Decision, or Glob-activated. Workflows are invoked via /workflow-name.

This adapter generates:
  - .agents/rules/memory-system.md      (memory protocol — set to Always On in UI)
  - .agents/rules/project-context.md    (architecture + conventions — set to Always On)
  - .agents/workflows/memory-update.md  (post-work memory maintenance workflow)

Note: Antigravity rules and workflows are markdown files. Activation mode
(Always On / Manual / Glob) is set via the Antigravity UI after the files are
detected. The user must open the Customizations panel and set each rule to
"Always On" for full passive coverage.
"""
from pathlib import Path


def generate(project_root: Path, config: dict) -> str:
    """Generate Antigravity configuration."""

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
            fallback = project_root / ".agent" / "templates" / "architecture.md"
            if fallback.exists():
                arch_content = fallback.read_text()

    # Build conventions section
    conventions = config.get("conventions", [])
    conventions_md = "\n".join(f"- {c}" for c in conventions) if conventions else ""

    # --- Rules ---
    agents_dir = project_root / ".agents"
    rules_dir = agents_dir / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)

    # Rule 1: Memory System (Always On recommended)
    memory_rule = f"""\
# Memory System — {project['name']}

You are working on a project with a file-based persistent memory system.
Follow these rules on every turn.

## Session Start
Read `memory/semantic.md` ONCE to load distilled project context.

## Every Turn
Read `memory/working.md` to know the current task state before responding.

## Task Files
Only load `/dev/[task]/*` files when actively working on that specific task.
Do not speculatively load files "just in case".

## MCP Efficiency
Before calling any MCP tool to retrieve project information, first check if
that information might exist in `memory/semantic.md` or `dev/[task]/context.md`.
Local files are cheaper than remote MCP queries.

## Context Drift
If your reasoning becomes uncertain or inconsistent with prior context,
re-read `memory/semantic.md` before continuing.

## Task Switching
If the user's message describes work outside the current `working.md` focus,
ask: "This looks like a different task — should I archive the current state first?"

## Approval Gate
- `memory/semantic.md` and `DECISIONS.md` require explicit user approval before writing.
- `memory/working.md` may be updated freely, including rewriting from scratch if stale.
- Never write speculatively to `semantic.md` or `DECISIONS.md`.
"""

    # Rule 2: Project Context (Always On recommended)
    project_rule = f"""\
# Project Context — {project['name']}

**{project['name']}** is {project['description']}

---

## Architecture Vision

{arch_content}

---

## Key Conventions

{conventions_md}
"""

    (rules_dir / "memory-system.md").write_text(memory_rule)
    (rules_dir / "project-context.md").write_text(project_rule)

    # --- Workflows ---
    workflows_dir = agents_dir / "workflows"
    workflows_dir.mkdir(parents=True, exist_ok=True)

    memory_workflow = """\
# Memory Update

Run this workflow after completing significant work to update project memory.

## Steps

1. Inspect the git diff:
   - `git diff --name-only`
   - `git diff` for specifics when needed

2. If the reason behind a change is not obvious from the diff, ask the user
   for intent before proposing any memory update. Do not guess intent from code alone.

3. Evaluate whether changes introduce any of:
   - New architectural decisions
   - New patterns or conventions
   - Important implementation details worth remembering
   - Bugs or gotchas discovered during work
   - Resolved assumptions (from `dev/[task]/context.md` Assumptions section)

4. If ANY qualifies as architecturally or operationally significant:
   - Draft the proposed update — show the user exactly what would be written and to which file
   - Wait for explicit approval ("looks good", "yes", "approve") before writing
   - On approval: write to `semantic.md` and/or `DECISIONS.md` and/or `context.md`
   - On correction: apply the user's edit, then write

5. Always, regardless of significance:
   - Update `memory/working.md` to reflect current state — this does NOT require approval
   - If `working.md` is stale, inconsistent, or over 300 lines: rewrite from scratch

6. If changes are trivial (renames, formatting, one-line bugfixes without broader lessons):
   - Update `working.md` only
   - State explicitly: "No semantic.md update needed — changes were trivial."
"""

    task_switch_workflow = """\
# Task Switch

Use this workflow when the user wants to change tasks mid-session.

## Steps

1. Confirm with the user: "Should I archive the current state first?"
2. If yes:
   - Snapshot current `memory/working.md` contents into `dev/[current-task]/context.md`
   - Create or load `dev/[new-task]/` folder
   - Read `dev/[new-task]/plan.md`, `context.md`, and `tasks.md`
   - Rewrite `memory/working.md` for the new focus
3. If no:
   - Simply create or load `dev/[new-task]/` and update `working.md`
"""

    (workflows_dir / "memory-update.md").write_text(memory_workflow)
    (workflows_dir / "task-switch.md").write_text(task_switch_workflow)

    return (
        "Antigravity configuration generated:\n"
        "  - .agents/rules/memory-system.md\n"
        "  - .agents/rules/project-context.md\n"
        "  - .agents/workflows/memory-update.md\n"
        "  - .agents/workflows/task-switch.md\n\n"
        "IMPORTANT: Open Antigravity's Customizations panel and set both rules\n"
        "to 'Always On' for passive memory coverage. Workflows are invoked manually\n"
        "via /memory-update and /task-switch."
    )
