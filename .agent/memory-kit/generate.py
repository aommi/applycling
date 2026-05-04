#!/usr/bin/env python3
"""
Agent Agnostic Memory Adapter Generator — Standalone

Generates entry-point files and hook configurations for different AI coding agents.
All adapters share the same underlying memory files (memory/semantic.md, memory/working.md).

Usage in any repo with a .agent/project.yaml:
    python .agent/memory-kit/generate.py <agent>

Where <agent> is one of:
    - claude-code  : Generates CLAUDE.md + .claude/settings.json hooks
    - codex        : Generates AGENTS.md (hooks not supported)
    - cursor       : Generates .cursor/rules/memory.mdc with auto-attach
    - gemini-cli   : Generates GEMINI.md + .gemini/context.md
    - windsurf     : Generates .windsurfrules (no hook support)
    - openclaw     : Generates .openclaw-system.md (system prompt include)
    - hermes       : Generates AGENTS.md — superset of codex, also readable by Codex
    - antigravity  : Generates .agents/rules/ + .agents/workflows/ (Rules + Workflows)
    - all          : Generates all ENABLED agents (respects project.yaml agents.*.enabled)
    - init         : Scaffold .agent/project.yaml and memory/ files for a new project

FLAGS (valid only with 'all'):
    --force        Regenerate already-enabled agents that were skipped by
                   re-run safety. Respects agents.*.enabled in project.yaml
                   (does NOT generate disabled agents).
    --check        Compare generated files against expected output. Exit non-zero
                   on drift. Mutually exclusive with --force.

NOTE: codex and hermes both write AGENTS.md. The hermes version is a superset
(adds agentskills.io note). If you use both agents, run `hermes` or `all`.

ADAPTER CONTRACT:
    Each adapter module must export:
      - generate(project_root, config) -> str    # writes agent files, returns status
      - check(project_root, config) -> list[str] # returns drift diffs (empty = clean)
      - referenced_memory_files() -> list[str]   # .md files the adapter's Memory
                                                  #   Discipline section references

RE-RUN SAFETY:
    Running `generate.py all` multiple times is safe. Already-generated agents
    are skipped unless their output files are missing or --force is used.
    Newly-enabled agents in project.yaml are automatically detected and generated.
    If you toggle agents (e.g. disable hermes after it wrote AGENTS.md), run
    `generate.py all --force` to ensure the remaining enabled agent regenerates
    the shared file in its own format.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# This file is inside .agent/memory-kit/; project root is two levels up
DEFAULT_PROJECT_ROOT = Path(__file__).parent.parent.parent

sys.path.insert(0, str(Path(__file__).parent))

from adapters.claude_code import generate as generate_claude_code
from adapters.codex import generate as generate_codex
from adapters.cursor import generate as generate_cursor
from adapters.gemini_cli import generate as generate_gemini_cli
from adapters.windsurf import generate as generate_windsurf
from adapters.openclaw import generate as generate_openclaw
from adapters.hermes import generate as generate_hermes
from adapters.antigravity import generate as generate_antigravity
from adapters.utils import ensure_gitignored

import yaml


AGENTS = {
    "claude-code": generate_claude_code,
    "codex": generate_codex,
    "cursor": generate_cursor,
    "gemini-cli": generate_gemini_cli,
    "windsurf": generate_windsurf,
    "openclaw": generate_openclaw,
    "hermes": generate_hermes,
    "antigravity": generate_antigravity,
}

# Explicit run order for 'all'. hermes must follow codex because both write AGENTS.md
# and the hermes version (superset) should win.
ALL_ORDER = [
    "claude-code",
    "codex",
    "cursor",
    "gemini-cli",
    "windsurf",
    "openclaw",
    "hermes",
    "antigravity",
]

# Primary output files per agent — used to detect if an agent was already generated.
AGENT_OUTPUTS = {
    "claude-code": ["CLAUDE.md", ".claude/settings.json", "hooks/preprompt.txt", "hooks/stop.sh"],
    "codex": ["AGENTS.md"],
    "cursor": [".cursor/rules/memory.mdc", ".cursorignore"],
    "gemini-cli": ["GEMINI.md", ".gemini/context.md"],
    "windsurf": [".windsurfrules"],
    "openclaw": [".openclaw-system.md"],
    "hermes": ["AGENTS.md"],
    "antigravity": [
        ".agents/rules/memory-system.md",
        ".agents/rules/project-context.md",
        ".agents/workflows/memory-update.md",
        ".agents/workflows/task-switch.md",
    ],
}


def _bootstrap_working_md(project_root: Path) -> None:
    """Create memory/working.md from memory/working.example.md if it exists.

    Never overwrites an existing working.md. If the example file is missing
    (e.g. a pre-existing project that hasn't adopted the template yet), falls
    back to a minimal skeleton.
    """
    working_path = project_root / "memory" / "working.md"
    if working_path.exists():
        return  # never overwrite

    example_path = project_root / "memory" / "working.example.md"
    if example_path.exists():
        working_path.write_text(example_path.read_text())
    else:
        working_path.parent.mkdir(parents=True, exist_ok=True)
        working_path.write_text("# Working Memory\n\n")


def cmd_init(project_root: Path) -> None:
    """Scaffold .agent/project.yaml and memory/ files interactively."""
    config_path = project_root / ".agent" / "project.yaml"
    if config_path.exists():
        print(f"project.yaml already exists at {config_path}")
        print("Edit it directly, or delete it and re-run init.")
        sys.exit(1)

    print("Initializing agent-memory-kit for this project.\n")

    name = input("Project name: ").strip()
    if not name:
        print("Project name is required.")
        sys.exit(1)

    description = input("Project description (one line): ").strip()
    if not description:
        print("Description is required.")
        sys.exit(1)

    arch_file = input("Architecture file [vision.md]: ").strip() or "vision.md"

    print("\nWhich agents do you want to enable? (Enter to accept default)")
    agent_defaults = [
        ("claude-code", True),
        ("codex",       True),
        ("hermes",      False),
        ("openclaw",    False),
        ("cursor",      False),
        ("windsurf",    False),
        ("gemini-cli",  False),
        ("antigravity", False),
    ]
    agents_section = {}
    for agent, default in agent_defaults:
        hint = "Y/n" if default else "y/N"
        answer = input(f"  {agent} [{hint}]: ").strip().lower()
        if answer == "":
            enabled = default
        else:
            enabled = answer in ("y", "yes")
        agents_section[agent.replace("-", "_")] = {"enabled": enabled}

    print("\nMemory capture — when should the Claude Code stop hook trigger? (Enter to accept default)")
    print("  'merge' catches local merges and GitHub PR merges made via merge commit.")
    print("  'commit' catches regular commits, including GitHub squash/rebase merge styles.")
    capture_defaults = [
        ("response", True, "Every response with tracked code changes (current behavior)"),
        ("commit", False, "When a new non-merge commit is detected since last run (noisier)"),
        ("merge", True, "When a merge commit is detected since last run"),
    ]
    capture_at = []
    for level, default, description in capture_defaults:
        hint = "Y/n" if default else "y/N"
        print(f"  {description}")
        answer = input(f"  Enable '{level}' [{hint}]: ").strip().lower()
        enabled = default if answer == "" else answer in ("y", "yes")
        if enabled:
            capture_at.append(level)

    if not capture_at:
        print("\n  Note: no capture levels selected. The stop hook will warn instead of capture.")
        print("  Edit memory.capture_at in .agent/project.yaml to enable levels later.")

    config = {
        "project": {"name": name, "description": description},
        "architecture": {"file": arch_file},
        "conventions": [],
        "agents": agents_section,
        "memory": {
            "semantic_max_lines": 500,
            "working_max_lines": 300,
            "capture_at": capture_at,
            "files": {
                "semantic": "memory/semantic.md",
                "working": "memory/working.md",
                "decisions": "DECISIONS.md",
            },
            "approval_mode": {
                "default": "auto",
                "review": [],
            },
            "task_directory": "dev/[task]/",
        },
    }

    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    print(f"\nCreated {config_path.relative_to(project_root)}")

    memory_dir = project_root / "memory"
    memory_dir.mkdir(exist_ok=True)
    created = []

    # semantic.md — canonical project memory (tracked)
    semantic_path = memory_dir / "semantic.md"
    if not semantic_path.exists():
        semantic_path.write_text("# Semantic Memory\n\n")
        created.append("memory/semantic.md")

    # working.example.md — tracked template for local working memory
    example_path = memory_dir / "working.example.md"
    if not example_path.exists():
        example_path.write_text(
            "# Working Memory\n\n"
            "## Current Focus\n\n"
            "(none)\n\n"
            "## In Progress\n\n"
            "(none)\n\n"
            "## Blocked\n\n"
            "(none)\n\n"
            "## Next Steps\n\n"
            "(none)\n"
        )
        created.append("memory/working.example.md")

    # working.md — local session state (gitignored), bootstrapped from example
    working_path = memory_dir / "working.md"
    if not working_path.exists():
        _bootstrap_working_md(project_root)
        created.append("memory/working.md")

    if created:
        print("Created: " + ", ".join(created))

    ensure_gitignored(project_root, "memory/working.md")
    ensure_gitignored(project_root, ".agent/.last_checked_commit")

    print("\nNext steps:")
    print("  python .agent/memory-kit/generate.py all")


def load_config(project_root: Path) -> dict:
    """Load project configuration from .agent/project.yaml."""
    config_path = project_root / ".agent" / "project.yaml"
    if not config_path.exists():
        raise FileNotFoundError(
            f"No project config found at {config_path}.\n"
            "Run `generate.py init` to create one."
        )
    with open(config_path) as f:
        return yaml.safe_load(f)


def get_enabled_agents(config: dict, force_all: bool = False) -> list[str]:
    """Return the list of agents to generate.

    If force_all is True, bypasses re-run safety but still respects
    ``enabled: false`` in project.yaml.  --force generates already-enabled
    agents that were skipped by re-run safety; it does NOT generate
    disabled agents.

    Without --force, reads the ``agents`` section from project.yaml and
    returns only those with ``enabled: true``.  Agents missing from the
    config default to **enabled** so that adding a new adapter does not
    silently disappear for existing projects.
    """
    agents_config = config.get("agents", {})
    if not agents_config:
        # No agents section at all → backward-compat: generate everything
        return list(ALL_ORDER)

    enabled = []
    for name in ALL_ORDER:
        cfg_key = name.replace("-", "_")
        agent_cfg = agents_config.get(cfg_key, {})
        if agent_cfg.get("enabled", True):
            enabled.append(name)
    return enabled


def state_path(project_root: Path) -> Path:
    return project_root / ".agent" / ".generated_state.json"


def load_state(project_root: Path) -> dict:
    """Load generation state (which agents have been generated)."""
    sp = state_path(project_root)
    if not sp.exists():
        return {"version": 1, "agents": {}}
    try:
        with open(sp) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "agents": {}}


def save_state(project_root: Path, state: dict) -> None:
    """Persist generation state."""
    sp = state_path(project_root)
    sp.write_text(json.dumps(state, indent=2) + "\n")


def agent_files_exist(agent: str, project_root: Path) -> bool:
    """Check whether all expected output files for an agent exist."""
    files = AGENT_OUTPUTS.get(agent, [])
    return all((project_root / f).exists() for f in files)


def should_generate(agent: str, project_root: Path, force: bool, state: dict) -> tuple[bool, str]:
    """Determine whether an agent should be generated and why.

    Returns (should_generate, reason_message).
    """
    if force:
        return True, "--force requested"

    previously_generated = agent in state.get("agents", {})

    if previously_generated:
        if agent_files_exist(agent, project_root):
            return False, "already generated (use --force to regenerate)"
        else:
            return True, "missing files detected"
    else:
        return True, "newly enabled"


def _clear_superseded_state(agent: str, state: dict) -> None:
    """Remove other agents from state that share output files with this agent.

    This prevents a stale "already generated" signal when an agent that shares
    an output file (e.g. codex/hermes both write AGENTS.md) is disabled and
    the remaining enabled agent needs to regenerate the file in its own format.
    """
    my_files = set(AGENT_OUTPUTS.get(agent, []))
    for other_agent in list(state.get("agents", {}).keys()):
        if other_agent == agent:
            continue
        other_files = set(AGENT_OUTPUTS.get(other_agent, []))
        if my_files & other_files:
            del state["agents"][other_agent]


def _parse_args() -> tuple[str, Path, bool, bool]:
    """Parse command-line arguments.

    Returns (agent_name, project_root, force_all, check_mode).
    Rejects unknown flags for single-agent mode.
    --check and --force are mutually exclusive.
    """
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nNo agent specified. Use one of:")
        for agent in AGENTS:
            print(f"  - {agent}")
        sys.exit(1)

    agent_name = sys.argv[1].lower()
    project_root = DEFAULT_PROJECT_ROOT
    force_all = False
    check_mode = False

    # Allow overriding project root via second arg
    arg_idx = 2
    if len(sys.argv) > arg_idx and not sys.argv[arg_idx].startswith("-"):
        project_root = Path(sys.argv[arg_idx]).resolve()
        arg_idx += 1

    # Only 'all' accepts --force and --check
    remaining = [a for a in sys.argv[arg_idx:] if a.startswith("-")]
    if remaining:
        if agent_name == "all":
            if "--force" in remaining:
                force_all = True
                remaining.remove("--force")
            if "--check" in remaining:
                check_mode = True
                remaining.remove("--check")
            if remaining:
                print(f"Unknown flag(s): {', '.join(remaining)}")
                sys.exit(1)
            if force_all and check_mode:
                print("Error: --force and --check are mutually exclusive.")
                sys.exit(1)
        else:
            print(f"Unknown flag(s): {', '.join(remaining)}")
            print("Note: --force and --check are only valid with 'all'.")
            sys.exit(1)

    return agent_name, project_root, force_all, check_mode


def _run_check(project_root: Path, config: dict, enabled_agents: list[str]) -> int:
    """Run check mode across enabled agents. Returns exit code (0 = clean)."""
    import importlib

    drift_count = 0
    print(f"Checking for drift: {', '.join(enabled_agents)}\n")

    # When both codex and hermes are enabled, hermes supersedes codex
    # (both write AGENTS.md). Skip codex's check to avoid false drift.
    if "codex" in enabled_agents and "hermes" in enabled_agents:
        enabled_agents = [a for a in enabled_agents if a != "codex"]

    for name in enabled_agents:
        # Load the adapter module and call its check() function
        adapter_name = name.replace("-", "_")
        try:
            mod = importlib.import_module(f"adapters.{adapter_name}")
        except ImportError:
            print(f"  WARN  {name:<13} — adapter not found, skipping check")
            continue

        if not hasattr(mod, "check"):
            print(f"  WARN  {name:<13} — no check function, skipping")
            continue

        diffs = mod.check(project_root, config)
        if not diffs:
            print(f"  OK    {name:<13} — no drift")
        else:
            for diff in diffs:
                drift_count += 1
                print(f"  DRIFT {name:<13}")
                print(diff)
                print()

    # ── Approval mode config validation ────────────────────────────────
    from adapters.utils import validate_approval_mode

    referenced_files = set()
    for name in enabled_agents:
        adapter_name = name.replace("-", "_")
        try:
            mod = importlib.import_module(f"adapters.{adapter_name}")
        except ImportError:
            continue
        if hasattr(mod, "referenced_memory_files"):
            referenced_files.update(mod.referenced_memory_files())

    if referenced_files:
        import sys as _sys
        approval_msgs = validate_approval_mode(config, referenced_files)
        for msg in approval_msgs:
            if msg.startswith("DRIFT"):
                drift_count += 1
                print(msg)
            elif msg.startswith("INFO"):
                print(msg, file=_sys.stderr)

    if drift_count:
        print(f"\n{drift_count} file(s) have drifted. Run `generate.py all` to regenerate.")
    else:
        print("\nAll generated files match expected output.")

    return 1 if drift_count else 0


def main():
    agent_name, project_root, force_all, check_mode = _parse_args()

    if agent_name == "init":
        cmd_init(project_root)
        return

    config = load_config(project_root)

    if agent_name == "all":
        enabled_agents = get_enabled_agents(config, force_all)
        if not enabled_agents:
            print(
                "No agents enabled in .agent/project.yaml.\n"
                "Set enabled: true for at least one agent in the agents section."
            )
            sys.exit(0)

        if check_mode:
            sys.exit(_run_check(project_root, config, enabled_agents))

        # Bootstrap working memory from template if missing (e.g. fresh clone)
        _bootstrap_working_md(project_root)

        state = load_state(project_root)
        mode = "enabled agents (--force)" if force_all else "enabled agents only"
        print(f"Checking configurations for {mode}: {', '.join(enabled_agents)}\n")

        generated_any = False
        for name in enabled_agents:
            should, reason = should_generate(name, project_root, force_all, state)
            if not should:
                print(f"  SKIP  {name:<13} — {reason}")
                continue

            print(f"  GEN   {name:<13} — {reason}")
            result = AGENTS[name](project_root, config)
            print(result)
            if name == "hermes":
                print("  (overwrote codex AGENTS.md — hermes version is superset)")
            print()

            # Record generation timestamp and clear any agents this one superseded
            state.setdefault("agents", {})[name] = {
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
            _clear_superseded_state(name, state)
            generated_any = True

        if generated_any:
            save_state(project_root, state)

        print("Done. Memory files (memory/, dev/, DECISIONS.md) are shared across all agents.")
        return

    if agent_name not in AGENTS:
        print(f"Unknown agent: {agent_name}")
        print(f"\nSupported agents: {', '.join(AGENTS.keys())}")
        sys.exit(1)

    generator = AGENTS[agent_name]
    result = generator(project_root, config)
    print(result)


if __name__ == "__main__":
    main()
