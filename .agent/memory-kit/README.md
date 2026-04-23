# Agent Memory Kit

A file-based memory system for solo developers who switch between AI coding agents. Works across any repository. Supports Claude Code, Hermes, OpenClaw, Codex, Cursor, Gemini CLI, and Windsurf.

---

## What problem this solves

You work on multiple repos. You use multiple agents (Claude Code for deep work, Hermes for quick questions, OpenClaw for Telegram, etc.). Each session, you re-explain the same context. Token costs climb. Context drifts. Decisions get re-made.

This kit gives you:
- **One file structure** that lives in every repo (`memory/semantic.md`, `memory/working.md`, `DECISIONS.md`, `dev/[task]/`)
- **One generator** that produces the right entry-point file for each agent
- **Hook-based enforcement** where supported (Claude Code), instruction-driven where not (everyone else)

---

## Architecture

### Two-layer design

```
┌─────────────────────────────────────────────────────────────┐
│  LAYER 1: MEMORY-KIT (generic, copyable)                    │
│                                                             │
│  - templates/preprompt.txt    (per-turn instructions)       │
│  - templates/stop.sh          (post-response reminder)      │
│  - templates/memory_protocol.md (memory system rules)       │
│  - adapters/                   (one per agent)              │
│  - generate.py                 (CLI entry point)            │
└─────────────────────────────────────────────────────────────┘
                              ↓ reads
┌─────────────────────────────────────────────────────────────┐
│  LAYER 2: PROJECT CONFIG (per repo)                         │
│                                                             │
│  - .agent/project.yaml         (name, description, arch)    │
│  - ARCHITECTURE_VISION.md      (project-specific knowledge) │
│  - memory/semantic.md          (runtime: distilled facts)   │
│  - memory/working.md           (runtime: current task)      │
│  - DECISIONS.md                (runtime: decisions log)     │
│  - dev/[task]/                 (runtime: active tasks)      │
└─────────────────────────────────────────────────────────────┘
```

**The rule:** Layer 1 never contains project-specific text. Layer 2 never contains agent-specific logic. You can copy `memory-kit/` into any repo, write a `project.yaml`, and generate configs for all your agents.

---

## Setup in a new repo

### Step 1: Copy the kit

From your source repo (e.g., applycling):

```bash
cd ~/projects/my-new-project
cp -r ~/projects/applycling/.agent/memory-kit .agent-memory-kit
# Or copy into .agent/ if you want it hidden:
cp -r ~/projects/applycling/.agent/memory-kit .agent/
```

### Step 2: Create project.yaml

```bash
cat > .agent/project.yaml << 'EOF'
project:
  name: my-new-project
  description: A web service that does X. Supports Y and Z.
  llm_providers:
    - openai
    - anthropic

architecture:
  file: ARCHITECTURE.md

conventions:
  - "Use pytest for all tests"
  - "API keys live in .env"

skills:
  enabled: false

agents:
  claude_code:
    enabled: true
    hooks:
      preprompt: true
      stop: true
  hermes:
    enabled: true
  openclaw:
    enabled: true
  codex:
    enabled: true
EOF
```

### Step 3: Create your architecture doc

```bash
cat > ARCHITECTURE.md << 'EOF'
# Architecture — my-new-project

## Core Systems

- **API:** FastAPI in `api/`
- **DB:** SQLAlchemy + asyncpg

## Key Conventions

- `pytest --asyncio-mode=auto`
- Never commit `.env`
EOF
```

### Step 4: Generate agent configs

```bash
python .agent/memory-kit/generate.py all
```

This creates:
- `CLAUDE.md` + `.claude/settings.json` + `hooks/` (Claude Code)
- `AGENTS.md` (Hermes + Codex)
- `.openclaw-system.md` (OpenClaw)
- `.cursor/rules/memory.mdc` (Cursor)
- `.windsurfrules` (Windsurf)
- `GEMINI.md` + `.gemini/context.md` (Gemini CLI)

### Step 5: Create runtime memory files

```bash
mkdir -p memory dev
# Seed with empty templates or copy from another repo
touch DECISIONS.md
```

---

## Daily Use by Agent

### Claude Code (HIGH confidence — hooks enforced)

**Files:** `CLAUDE.md`, `.claude/settings.json`, `hooks/preprompt.txt`, `hooks/stop.sh`

**How it works:**
- On session start, Claude Code reads `CLAUDE.md` automatically
- Before every user message, `hooks/preprompt.txt` is injected → agent reads `memory/working.md`
- After every response, `hooks/stop.sh` runs → agent inspects diff, proposes memory updates

**Your workflow:**
1. Open terminal, run `claude`
2. Agent reads `semantic.md` + `working.md` automatically
3. Work normally. After code changes, the stop hook fires
4. Agent asks about intent if unclear, then proposes `semantic.md` / `DECISIONS.md` updates
5. Approve or correct. `working.md` updates automatically

**If something breaks:**
- Hooks not firing? Check `.claude/settings.json` exists and `hooks/stop.sh` is executable (`chmod +x`)
- Agent forgetting context? Say "re-read semantic.md"
- Agent skipping hook output in long sessions? Say "check the diff and propose memory updates"

---

### Hermes (MEDIUM confidence — instruction-driven)

**Files:** `AGENTS.md`

**How it works:**
- Hermes reads `AGENTS.md` at project root as workspace context
- No hooks. The per-turn instructions are embedded in `AGENTS.md` as static text
- Hermes also has native `MEMORY.md` / `USER.md` persistence

**Your workflow:**
1. Open Hermes in the repo
2. Agent reads `AGENTS.md` at session start
3. Because there are no hooks, you must manually prompt: "Read memory/working.md before answering"
4. After significant changes, prompt: "Inspect the diff and propose memory updates"

**Synergy with Hermes native memory:**
```bash
ln -s memory/semantic.md MEMORY.md
```
This mirrors your file-based memory into Hermes's built-in persistence. `memory/semantic.md` remains the source of truth.

---

### OpenClaw (MEDIUM-HIGH confidence — system prompt)

**Files:** `.openclaw-system.md`

**How it works:**
- `.openclaw-system.md` is injected into the system prompt on every turn
- Stronger than Hermes/Codex because it lives in the system context, not just an entry-point file
- No post-response hooks

**Your workflow:**
1. Configure OpenClaw to use `.openclaw-system.md` as `system_prompt_file`
2. The memory rules are present on every response
3. After significant changes, manually prompt: "Propose memory updates"

---

### Codex (LOW-MEDIUM confidence — instruction-driven)

**Files:** `AGENTS.md` (Hermes version overwrites this if you run `all`)

**How it works:**
- Same as Hermes but without the `agentskills.io` note
- Codex's `AGENTS.md` support is less documented and evolves rapidly
- No hooks

**Your workflow:**
- Same as Hermes, but less reliable. If Codex drifts, explicitly say: "Read memory/semantic.md and memory/working.md"

---

## The Memory Files

These are the same across all agents. This is what makes the system portable.

| File | Purpose | Size limit | Who writes | Approval? |
|---|---|---|---|---|
| `memory/semantic.md` | Distilled project knowledge | ≤500 lines | Agent (proposed) | **Yes** |
| `memory/working.md` | Live task state | ≤300 lines | Agent (auto) | No |
| `DECISIONS.md` | Append-only decisions log | No limit | Agent (proposed) | **Yes** |
| `dev/[task]/plan.md` | Task goal and approach | No limit | Agent | No |
| `dev/[task]/context.md` | Constraints, assumptions | No limit | Agent | No |
| `dev/[task]/tasks.md` | Progress checklist | No limit | Agent | No |

**Approval flow:**
- `semantic.md` and `DECISIONS.md` require your approval before writing
- `working.md` updates freely
- `dev/[task]/` files update freely

---

## Task Switching Protocol

When you change topics mid-session, the agent should ask:
> "This looks like a different task — should I archive the current state first?"

Say yes. The agent:
1. Archives `working.md` into `dev/[old-task]/context.md`
2. Creates/loads `dev/[new-task]/`
3. Rewrites `working.md` for the new focus

To resume later:
> "Resume dev/[original-task]/"

---

## Weekly Maintenance (10 minutes)

1. **Skim `semantic.md`** — anything stale? Tell the agent to propose a correction
2. **Check `DECISIONS.md`** — reversed decisions should have "Supersedes" entries
3. **Check `dev/`** — ship tasks to `dev/archive/`
4. **Check agent entry-point files** — delete dead rules (they train the agent to ignore live ones)

---

## Keeping the kit in sync across repos

Since this is a solo workflow, the simplest approach is copy-paste:

1. `applycling/.agent/memory-kit/` is your source of truth
2. When you improve an adapter, copy the improved files to other repos
3. Or use git subtree if you prefer:
   ```bash
   git subtree add --prefix .agent/memory-kit <kit-repo-url> main --squash
   ```

Do not over-engineer this. For 1–5 repos, copy-paste is faster than any automation.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Agent re-explains known context | `semantic.md` not loaded or stale | Check entry-point file references it; say "re-read semantic.md" |
| Answers feel off mid-session | Context drift | Say "re-read semantic.md and try again" |
| `semantic.md` > 500 lines | Bloat | "Compact semantic.md — keep only high-signal entries, propose for approval" |
| Agent stops proposing updates | Context pressure suppressing hook | "Inspect diff since last memory check and propose updates" |
| Agent asks same question across sessions | Assumptions not logged | Check `dev/[task]/context.md` Assumptions section |
| Claude Code hooks not firing | `settings.json` missing or `stop.sh` not executable | `chmod +x hooks/stop.sh`; verify `.claude/settings.json` |
| Generated files missing architecture section | `ARCHITECTURE_VISION.md` (or configured arch file) not found | Create it, or the adapter falls back to `.agent/templates/architecture.md` |

---

## File Reference

```
.agent/
  project.yaml              # Your project config (name, description, conventions)
  generate.py               # Thin wrapper — loads config, calls memory-kit
  adapters/                 # Thin wrappers — load config, call memory-kit adapters
  memory-kit/               # THE REUSABLE CORE
    README.md               # This file
    generate.py             # Standalone generator for any repo
    templates/
      preprompt.txt         # Per-turn instructions (generic)
      stop.sh               # Post-response diff reminder (generic)
      memory_protocol.md    # Memory system rules (generic)
    adapters/
      claude_code.py        # Parameterized Claude Code adapter
      hermes.py             # Parameterized Hermes adapter
      openclaw.py           # Parameterized OpenClaw adapter
      codex.py              # Parameterized Codex adapter
      cursor.py             # Parameterized Cursor adapter
      windsurf.py           # Parameterized Windsurf adapter
      gemini_cli.py         # Parameterized Gemini CLI adapter

memory/
  semantic.md               # Distilled knowledge (≤500 lines)
  working.md                # Current task (≤300 lines)
DECISIONS.md                # Append-only decisions log
dev/                        # Active task folders
```
