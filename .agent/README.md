# Agent Agnostic Memory Adapters

This directory contains adapters for integrating the applycling memory system with different AI coding agents.

## The Problem

The memory system (`memory/semantic.md`, `memory/working.md`, `dev/[task]/`) is portable across agents. However, each agent has its own:
- Entry-point file (`CLAUDE.md`, `AGENTS.md`, `.cursor/rules/`)
- Hook configuration format (or none at all)
- Memory loading mechanism

## The Solution

Run the adapter generator for your target agent. It creates the right entry-point file and hook configuration.

## Usage

```bash
# From project root
python .agent/generate.py <agent>
```

Where `<agent>` is one of:
- `claude-code` — generates `CLAUDE.md` + `.claude/settings.json` hooks
- `codex` — generates `AGENTS.md` (hooks not supported)
- `cursor` — generates `.cursor/rules/memory.mdc` with auto-attach globs
- `gemini-cli` — generates `GEMINI.md` + sub-directory files
- `windsurf` — generates `.windsurfrules` (no hook support)
- `openclaw` — generates `.openclaw-system.md` (system prompt include)
- `hermes` — generates `AGENTS.md` (superset of codex; also readable by Codex)
- `all` — generates all of the above (hermes runs after codex so hermes AGENTS.md wins)

**codex vs hermes:** Both write `AGENTS.md`. The hermes version is a superset (adds
agentskills.io skills note). If you use both agents, run `hermes` or `all`.

## File Structure

```
.agent/
  generate.py          # Main generator script
  adapters/
    claude_code.py     # Claude Code adapter
    codex.py           # OpenAI Codex adapter
    cursor.py          # Cursor IDE adapter
    gemini_cli.py      # Gemini CLI adapter
    windsurf.py        # Windsurf adapter
    openclaw.py        # OpenClaw adapter
    hermes.py          # Hermes Agent adapter (Nous Research)
  templates/
    preprompt.txt      # Shared preprompt template
    stop.sh            # Shared stop hook (Claude Code only)
```

## Memory Files (Portable)

These live at project root and are shared across all agents:
- `memory/semantic.md` — distilled project knowledge (≤500 tokens)
- `memory/working.md` — live task state (≤300 tokens)
- `DECISIONS.md` — append-only decisions log
- `dev/[task]/` — active task context

## How It Works

1. **Claude Code**: Uses hooks (`UserPromptSubmit`, `Stop`) to load memory automatically
2. **Codex**: Entry-point file (`AGENTS.md`) instructs the agent to read memory files
3. **Cursor**: Rules with auto-attach globs trigger on file changes
4. **Gemini CLI**: Entry-point file + sub-directory context files
5. **Windsurf**: `.windsurfrules` file at project root; no hook support — instruction-driven
6. **OpenClaw**: `.openclaw-system.md` as a system prompt include; paste or reference via `system_prompt_file`
7. **Hermes**: `AGENTS.md` at project root; skills in `applycling/skills/` are natively browsable via Hermes's `/skills`

The adapter generator ensures each agent gets the right integration format while sharing the same underlying memory files.
