# Agent Agnostic Memory Adapters

This directory contains adapters for integrating the applycling memory system with different AI coding agents.

## Structure

```
.agent/
  project.yaml          # Applycling-specific configuration
  generate.py           # Main generator script (thin wrapper around memory-kit)
  adapters/             # Thin wrappers that load project.yaml and delegate to memory-kit
  memory-kit/           # THE REUSABLE CORE — copy this to other repos
    README.md           # Full documentation for the kit
    generate.py         # Standalone generator
    templates/          # Generic templates (preprompt, stop hook, memory protocol)
    adapters/           # Parameterized adapters for each agent
```

## How it works

1. **Project config** lives in `.agent/project.yaml` — name, description, architecture file, conventions, enabled agents.
2. **Generic protocol** lives in `.agent/memory-kit/templates/` — preprompt instructions, stop hook, memory rules. These are agent-agnostic.
3. **Agent adapters** in `.agent/memory-kit/adapters/` combine project config + generic templates to produce the right entry-point file for each agent.
4. **Thin wrappers** in `.agent/adapters/` load `.agent/project.yaml` and call the memory-kit adapter. This keeps the existing `generate.py` interface unchanged.

## Usage

```bash
# From project root
python .agent/generate.py <agent>
```

Where `<agent>` is one of:
- `claude-code` — generates `CLAUDE.md` + `.claude/settings.json` hooks
- `codex` — generates `AGENTS.md` (hooks not supported)
- `hermes` — generates `AGENTS.md` (superset of codex; also readable by Codex)
- `openclaw` — generates `.openclaw-system.md`
- `cursor` — generates `.cursor/rules/memory.mdc`
- `windsurf` — generates `.windsurfrules`
- `gemini-cli` — generates `GEMINI.md`
- `antigravity` — generates `.agents/rules/` + `.agents/workflows/`
- `all` — generates only the agents enabled in `.agent/project.yaml`

Use `--force` with `all` to generate every agent regardless of config.

## Using this in another repo

See `.agent/memory-kit/README.md` for the full cross-repo setup guide. The short version:

1. Copy `.agent/memory-kit/` into your new repo
2. Create `.agent/project.yaml` with your project details
3. Create `ARCHITECTURE.md` with your project architecture
4. Run `python .agent/memory-kit/generate.py all`

## Memory Files (Portable)

These live at project root and are shared across all agents:
- `memory/semantic.md` — distilled project knowledge (≤500 lines)
- `memory/working.md` — live task state (≤300 lines)
- `DECISIONS.md` — append-only decisions log
- `dev/[task]/` — active task context
