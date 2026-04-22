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
    - all          : Generates all of the above (hermes runs after codex and wins)

NOTE: codex and hermes both write AGENTS.md. The hermes version is a superset
(adds agentskills.io note). If you use both agents, run `hermes` or `all`.
"""

import sys
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


AGENTS = {
    "claude-code": generate_claude_code,
    "codex": generate_codex,
    "cursor": generate_cursor,
    "gemini-cli": generate_gemini_cli,
    "windsurf": generate_windsurf,
    "openclaw": generate_openclaw,
    "hermes": generate_hermes,
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
]


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nNo agent specified. Use one of:")
        for agent in AGENTS:
            print(f"  - {agent}")
        sys.exit(1)

    agent_name = sys.argv[1].lower()
    project_root = Path(__file__).parent.parent

    if agent_name == "all":
        print("Generating configurations for all agents...\n")
        for name in ALL_ORDER:
            print(f"=== {name.upper()} ===")
            result = AGENTS[name](project_root)
            print(result)
            if name == "hermes":
                print("  (overwrote codex AGENTS.md — hermes version is superset)")
            print()
        print("Done. Memory files (memory/, dev/, DECISIONS.md) are shared across all agents.")
        return

    if agent_name not in AGENTS:
        print(f"Unknown agent: {agent_name}")
        print(f"\nSupported agents: {', '.join(AGENTS.keys())}")
        sys.exit(1)

    generator = AGENTS[agent_name]
    result = generator(project_root)
    print(result)


if __name__ == "__main__":
    main()
