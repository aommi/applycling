#!/usr/bin/env python3
"""
Agent Agnostic Memory Adapter Generator

Generates entry-point files and hook configurations for different AI coding agents.
All adapters share the same underlying memory files (memory/semantic.md, memory/working.md).

Usage:
    python .agent/generate.py <agent>

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
    --force        When used with 'all', generate ALL agents regardless of config
                   or previous generation state.

NOTE: codex and hermes both write AGENTS.md. The hermes version is a superset
(adds agentskills.io note). If you use both agents, run `hermes` or `all`.

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

# Add adapters to path
sys.path.insert(0, str(Path(__file__).parent))

from adapters.claude_code import generate as generate_claude_code
from adapters.codex import generate as generate_codex
from adapters.cursor import generate as generate_cursor
from adapters.gemini_cli import generate as generate_gemini_cli
from adapters.windsurf import generate as generate_windsurf
from adapters.openclaw import generate as generate_openclaw
from adapters.hermes import generate as generate_hermes
from adapters.antigravity import generate as generate_antigravity

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
        return

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

    config = {
        "project": {"name": name, "description": description},
        "architecture": {"file": arch_file},
        "conventions": [],
        "agents": agents_section,
        "memory": {
            "semantic_max_lines": 500,
            "working_max_lines": 300,
            "files": {
                "semantic": "memory/semantic.md",
                "working": "memory/working.md",
                "decisions": "DECISIONS.md",
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

    # Ensure memory/working.md is gitignored
    gitignore_path = project_root / ".gitignore"
    entry = "memory/working.md"
    if gitignore_path.exists():
        content = gitignore_path.read_text()
        if entry not in content.splitlines():
            if not content.endswith("\n"):
                content += "\n"
            gitignore_path.write_text(content + entry + "\n")
    else:
        gitignore_path.write_text(entry + "\n")

    print("\nNext steps:")
    print("  python .agent/generate.py all")


def load_config(project_root: Path) -> dict:
    """Load project configuration from .agent/project.yaml."""
    config_path = project_root / ".agent" / "project.yaml"
    if not config_path.exists():
        raise FileNotFoundError(
            f"No project config found at {config_path}.\n"
            "Run `python .agent/generate.py init` to create one."
        )
    with open(config_path) as f:
        return yaml.safe_load(f)


def get_enabled_agents(config: dict, force_all: bool = False) -> list[str]:
    """Return the list of agents to generate.

    If force_all is True, returns every agent in ALL_ORDER.
    Otherwise reads the ``agents`` section from project.yaml and returns
    only those with ``enabled: true``.  Agents missing from the config
    default to **enabled** so that adding a new adapter does not silently
    disappear for existing projects.
    """
    if force_all:
        return list(ALL_ORDER)

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
    project_root = Path(__file__).parent.parent
    force_all = False
    check_mode = False

    # Optional positional project_root override (memory-kit style)
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
                "Enable some agents or run with --force to generate all."
            )
            sys.exit(0)

        if check_mode:
            # Delegate check to memory-kit's generate.py (avoids sys.path conflicts)
            import subprocess
            mk_gen = str(project_root / ".agent" / "memory-kit" / "generate.py")
            result = subprocess.run(
                [sys.executable, mk_gen, "all", "--check", project_root],
                capture_output=False,
            )
            sys.exit(result.returncode)

        # Bootstrap working memory from template if missing (e.g. fresh clone)
        _bootstrap_working_md(project_root)

        state = load_state(project_root)
        mode = "ALL agents (--force)" if force_all else "enabled agents only"
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
