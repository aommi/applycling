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

FLAGS:
    --force        When used with 'all', generate ALL agents regardless of config
                   or previous generation state.

NOTE: codex and hermes both write AGENTS.md. The hermes version is a superset
(adds agentskills.io note). If you use both agents, run `hermes` or `all`.

RE-RUN SAFETY:
    Running `generate.py all` multiple times is safe. Already-generated agents
    are skipped unless their output files are missing or --force is used.
    Newly-enabled agents in project.yaml are automatically detected and generated.
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

AGENT_NAME_MAP = {
    "claude-code": "claude_code",
    "codex": "codex",
    "cursor": "cursor",
    "gemini-cli": "gemini_cli",
    "windsurf": "windsurf",
    "openclaw": "openclaw",
    "hermes": "hermes",
    "antigravity": "antigravity",
}

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


def load_config(project_root: Path) -> dict:
    """Load project configuration from .agent/project.yaml."""
    config_path = project_root / ".agent" / "project.yaml"
    if not config_path.exists():
        raise FileNotFoundError(
            f"No project config found at {config_path}.\n"
            "Run `amk init` or create .agent/project.yaml manually."
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
        cfg_key = AGENT_NAME_MAP.get(name, name)
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


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nNo agent specified. Use one of:")
        for agent in AGENTS:
            print(f"  - {agent}")
        sys.exit(1)

    agent_name = sys.argv[1].lower()
    project_root = DEFAULT_PROJECT_ROOT
    force_all = "--force" in sys.argv

    # Allow overriding project root via second arg
    if len(sys.argv) >= 3 and not sys.argv[2].startswith("-"):
        project_root = Path(sys.argv[2]).resolve()

    config = load_config(project_root)

    if agent_name == "all":
        enabled_agents = get_enabled_agents(config, force_all)
        if not enabled_agents:
            print(
                "No agents enabled in .agent/project.yaml.\n"
                "Enable some agents or run with --force to generate all."
            )
            sys.exit(0)

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

            # Record generation timestamp
            state.setdefault("agents", {})[name] = {
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
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
