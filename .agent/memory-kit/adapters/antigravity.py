"""
Antigravity Adapter — generates .agents/rules/ and .agents/workflows/

Google Antigravity supports workspace-specific Rules and Workflows as markdown
files in .agents/rules/ and .agents/workflows/. Rules can be Always On, Manual,
Model Decision, or Glob-activated. Workflows are invoked via /workflow-name.

This adapter generates:
  - .agents/rules/memory-system.md      (memory protocol — set to Always On in UI)
  - .agents/rules/project-context.md    (architecture + conventions — set to Always On)
  - .agents/workflows/memory-update.md  (post-work memory maintenance workflow)
  - .agents/workflows/task-switch.md    (task switching)

Note: Antigravity rules and workflows are markdown files. Activation mode
(Always On / Manual / Glob) is set via the Antigravity UI after the files are
detected. The user must open the Customizations panel and set each rule to
"Always On" for full passive coverage.
"""
from pathlib import Path

from .utils import (
    GENERATED_BANNER_MD,
    check_fully_generated,
)


def _banner_md(content: str) -> str:
    """Prepend the generated banner to a markdown template."""
    return GENERATED_BANNER_MD + "\n\n" + content


def generate(project_root: Path, config: dict) -> str:
    """Generate Antigravity configuration."""
    mk_dir = project_root / ".agent" / "memory-kit"
    templates = mk_dir / "templates"

    project = config["project"]
    arch_file = config.get("architecture", {}).get("file", "vision.md")

    conventions = config.get("conventions", [])
    conventions_md = "\n".join(f"- {c}" for c in conventions) if conventions else ""

    agents_dir = project_root / ".agents"
    rules_dir = agents_dir / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)

    ag_templates = templates / "antigravity"

    # Rule 1: Memory System (Always On recommended)
    memory_rule = _banner_md(
        (ag_templates / "memory-system.md").read_text().format(
            project_name=project["name"]
        )
    )

    # Rule 2: Project Context (Always On recommended)
    project_rule = _banner_md(
        (ag_templates / "project-context.md").read_text().format(
            project_name=project["name"],
            project_description=project["description"],
            arch_file=arch_file,
            conventions_md=conventions_md,
        )
    )

    (rules_dir / "memory-system.md").write_text(memory_rule)
    (rules_dir / "project-context.md").write_text(project_rule)

    # --- Workflows ---
    workflows_dir = agents_dir / "workflows"
    workflows_dir.mkdir(parents=True, exist_ok=True)

    memory_workflow = _banner_md((ag_templates / "memory-update.md").read_text())
    task_switch_workflow = _banner_md((ag_templates / "task-switch.md").read_text())

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


# ── Check mode ────────────────────────────────────────────────────────────────


def check(project_root: Path, config: dict) -> list[str]:
    """Return drift diffs for all generated files (empty if no drift)."""
    mk_dir = project_root / ".agent" / "memory-kit"
    templates = mk_dir / "templates"
    project = config["project"]
    arch_file = config.get("architecture", {}).get("file", "vision.md")
    conventions = config.get("conventions", [])
    conventions_md = "\n".join(f"- {c}" for c in conventions) if conventions else ""
    ag_templates = templates / "antigravity"

    diffs = []

    # Rules
    expected_memory_rule = _banner_md(
        (ag_templates / "memory-system.md").read_text().format(
            project_name=project["name"]
        )
    )
    r = check_fully_generated(
        project_root / ".agents" / "rules" / "memory-system.md",
        expected_memory_rule,
        ".agents/rules/memory-system.md",
    )
    if r:
        diffs.append(r)

    expected_project_rule = _banner_md(
        (ag_templates / "project-context.md").read_text().format(
            project_name=project["name"],
            project_description=project["description"],
            arch_file=arch_file,
            conventions_md=conventions_md,
        )
    )
    r = check_fully_generated(
        project_root / ".agents" / "rules" / "project-context.md",
        expected_project_rule,
        ".agents/rules/project-context.md",
    )
    if r:
        diffs.append(r)

    # Workflows
    expected_memory_wf = _banner_md((ag_templates / "memory-update.md").read_text())
    r = check_fully_generated(
        project_root / ".agents" / "workflows" / "memory-update.md",
        expected_memory_wf,
        ".agents/workflows/memory-update.md",
    )
    if r:
        diffs.append(r)

    expected_task_switch = _banner_md((ag_templates / "task-switch.md").read_text())
    r = check_fully_generated(
        project_root / ".agents" / "workflows" / "task-switch.md",
        expected_task_switch,
        ".agents/workflows/task-switch.md",
    )
    if r:
        diffs.append(r)

    return diffs
