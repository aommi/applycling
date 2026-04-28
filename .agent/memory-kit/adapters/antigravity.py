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

    project = config["project"]
    arch_file = config.get("architecture", {}).get("file", "vision.md")

    # Build conventions section
    conventions = config.get("conventions", [])
    conventions_md = "\n".join(f"- {c}" for c in conventions) if conventions else ""

    # --- Rules ---
    agents_dir = project_root / ".agents"
    rules_dir = agents_dir / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)

    ag_templates = templates / "antigravity"

    # Rule 1: Memory System (Always On recommended)
    memory_rule = (
        (ag_templates / "memory-system.md").read_text()
        .format(project_name=project['name'])
    )

    # Rule 2: Project Context (Always On recommended)
    project_rule = (
        (ag_templates / "project-context.md").read_text()
        .format(
            project_name=project['name'],
            project_description=project['description'],
            arch_file=arch_file,
            conventions_md=conventions_md,
        )
    )

    (rules_dir / "memory-system.md").write_text(memory_rule)
    (rules_dir / "project-context.md").write_text(project_rule)

    # --- Workflows ---
    workflows_dir = agents_dir / "workflows"
    workflows_dir.mkdir(parents=True, exist_ok=True)

    memory_workflow = (ag_templates / "memory-update.md").read_text()
    task_switch_workflow = (ag_templates / "task-switch.md").read_text()

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
