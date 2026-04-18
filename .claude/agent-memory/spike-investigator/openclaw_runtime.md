---
name: OpenClaw Runtime
description: OpenClaw execution model, timeout limits, SKILL.md format, Python skill invocation — from T0 spike research
type: project
---

OpenClaw is an open-source AI agent framework (TypeScript/Node/Electron), originally "Clawdbot" (Nov 2025), renamed Jan 2026. 250k+ GitHub stars. Skills are NOT Python packages — they are markdown-defined instruction sets that teach the LLM agent how to invoke tools (shell commands, scripts).

## SKILL.md Format

Directory: `~/.openclaw/workspace/skills/<skill-name>/`

Required frontmatter (YAML):
- `name`: unique snake_case identifier (also registers as slash command if `user-invocable: true`)
- `description`: one-line summary used by the agent to select the skill

Optional frontmatter:
- `user-invocable: true|false` — expose as slash command
- `disable-model-invocation: true` — exclude from model prompt
- `command-dispatch: tool` — bypass model, dispatch directly
- `metadata`: single-line JSON object — OS filtering, required bins, required env vars, config gates
  - `metadata.openclaw.os` — OS filter
  - `metadata.openclaw.requires.bins` — required binaries
  - `metadata.openclaw.requires.config` — config dependencies

Body: Markdown instructions for the agent on how to use tools/scripts. The agent reads these and calls tools accordingly.

Optional bundled directories: `scripts/`, `references/`, `assets/`

## Execution Model

**Subprocess, not in-process.** Skills invoke Python via shell exec:
  `uv run python {baseDir}/script.py "<ARG>"`
where `{baseDir}` resolves to the skill folder at runtime.

OpenClaw's `exec` tool runs commands in isolated subprocesses. The LLM reads SKILL.md instructions and decides what shell command to run.

## Timeout Configuration

Declared in SKILL.md frontmatter or metadata:
- Default: 30 seconds (shell tool default)
- `execution.timeout`: configurable up to 600 seconds (10 min)
- `longRunning: true`: marks skill as long-running, enables progress reporting mechanism
- `backgroundMs`: background process monitoring interval (e.g., 10000ms)
- `timeoutSec`: up to 1800 (30 min) seen in gateway config examples
- `cleanupMs`: cleanup delay after completion

**Critical for applycling:** 10-min pipeline needs `longRunning: true` + `execution.timeout: 600` minimum, or a background-worker pattern where the skill returns immediately and posts results async.

## Status Streaming

`notifyOnExit: true` — runtime notifies caller when subprocess exits. No real-time line-by-line streaming documented. For mid-pipeline status updates, the pattern is to spawn a background subprocess and have it post messages via the Telegram bot API directly, OR use OpenClaw's native background-job primitive if available.

**Why:** The 10-min applycling pipeline exceeds conversational response windows. AutoResolver + background subprocess is the cleanest sprint approach.

## Python Invocation Pattern

Skills call Python scripts via shell commands in the SKILL.md body instructions. Scripts print output; the LLM processes it. Arguments passed as shell args. `{baseDir}` template resolves to skill folder.

## Skill Registry

ClawHub (clawhub.com / clawskills.sh) hosts community skills. Skills installed to `~/.openclaw/workspace/skills/` (workspace) or globally. Workspace skills take precedence.

## What This Means for Ticket 4

- applycling skill = a directory with SKILL.md + scripts/apply.py
- SKILL.md instructs agent: "when user sends a URL, run: `python {baseDir}/scripts/apply.py '<URL>'`"
- apply.py calls `queue.append(url)` + spawns background worker (`pipeline.add()`) + returns ack immediately
- Background worker posts Telegram status updates directly via bot API
- Fallback: `applycling process-queue` as launchd service; skill only enqueues
