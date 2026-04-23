# Memory System Analysis — Current State & Honest Assessment

## What You Built

A file-based memory system with an adapter pattern that generates agent-specific entry-point files and hook configurations. The underlying memory files (`memory/semantic.md`, `memory/working.md`, `DECISIONS.md`, `dev/[task]/`) are portable. The adapters translate a shared template into each agent's native format.

---

## How It Works Per Agent

### 1. Claude Code (Anthropic)

**Files generated:** `CLAUDE.md`, `.claude/settings.json`, `hooks/preprompt.txt`, `hooks/stop.sh`

**Mechanism:**
- `CLAUDE.md` is the project constitution — Claude Code reads it automatically at session start
- `.claude/settings.json` registers two hooks:
  - `UserPromptSubmit`: runs `cat hooks/preprompt.txt` before every user message → injects working-memory rules
  - `Stop`: runs `bash hooks/stop.sh` after every response → triggers diff inspection + memory update proposals

**Will it work?** YES — this is the most robust integration. Claude Code hooks are first-class, well-documented, and the `UserPromptSubmit` / `Stop` events are stable. The preprompt guarantees working.md is considered every turn. The stop hook guarantees post-hoc reflection.

**Confidence:** HIGH

---

### 2. Hermes (Nous Research)

**Files generated:** `AGENTS.md` (overwrites Codex version)

**Mechanism:**
- Hermes reads `AGENTS.md` at project root as workspace-level context
- `AGENTS.md` contains instructions to read `memory/semantic.md` once and `memory/working.md` every turn
- Includes an `agentskills.io` note because Hermes can natively browse `applycling/skills/` via `/skills`
- Includes optional memory mirroring via symlink: `ln -s memory/semantic.md MEMORY.md`

**Will it work?** PARTIALLY. Hermes does read `AGENTS.md` and it has its own `MEMORY.md` / `USER.md` persistence layer. However:
- Hermes has NO hooks. The "read working.md on every turn" instruction is embedded in a static markdown file. Whether Hermes re-reads it consistently depends on context window pressure and how strongly the instruction is worded.
- The symlink trick helps bridge Hermes native memory with your file-based memory, but it only covers `semantic.md`, not `working.md` or `DECISIONS.md`.
- Hermes's built-in memory system may compete with or override your instructions.

**Confidence:** MEDIUM — the system prompt inclusion is decent, but without hooks you lose the per-turn enforcement. The agent might drift after a few turns.

---

### 3. OpenClaw

**Files generated:** `.openclaw-system.md`

**Mechanism:**
- OpenClaw has no native project-root file convention
- Two install options: (A) point `system_prompt_file` config at `.openclaw-system.md`, or (B) paste contents into OpenClaw's system prompt settings
- The file is treated as a system prompt include, so it lives in the system context on every turn

**Will it work?** MODERATELY WELL. Because `.openclaw-system.md` is injected into the system prompt (not just read once as a file), the memory rules are present on every response. This is actually stronger than Hermes/Codex entry-point files. However:
- OpenClaw has NO post-response hooks, so the `stop.sh` behavior (diff inspection, memory update proposals) is completely missing.
- You rely on the agent to self-police and propose updates, or you must prompt it manually.
- The install step is manual (config edit or paste), unlike Claude Code where `.claude/settings.json` is automatic.

**Confidence:** MEDIUM-HIGH for memory loading, LOW for automatic memory maintenance.

---

### 4. Codex (OpenAI)

**Files generated:** `AGENTS.md` (Hermes overwrites this if you run `all` or `hermes` after)

**Mechanism:**
- Codex reads `AGENTS.md` at project root as workspace context
- Same content as Hermes minus the `agentskills.io` note and memory mirroring section
- No hooks. Memory loading is instruction-driven.

**Will it work?** PARTIALLY. Same caveats as Hermes:
- No hooks means no guaranteed per-turn working.md reload
- Codex's behavior with `AGENTS.md` is less documented than Claude Code's with `CLAUDE.md`
- OpenAI has been evolving Codex rapidly; `AGENTS.md` support is not a guaranteed stable contract
- The stop-hook behavior (diff inspection, proposals) is entirely absent

**Confidence:** LOW-MEDIUM. It might work on a good day, but there's no enforcement mechanism.

---

## The Honest Summary

| Agent | Memory Loading | Per-Turn Working Memory | Post-Response Reflection | Overall Confidence |
|---|---|---|---|---|
| Claude Code | Automatic (CLAUDE.md) | Hook-enforced (preprompt.txt) | Hook-enforced (stop.sh) | HIGH |
| Hermes | Automatic (AGENTS.md) | Instruction only, no enforcement | None | MEDIUM |
| OpenClaw | System prompt include | System prompt, always present | None | MEDIUM |
| Codex | Automatic? (AGENTS.md) | Instruction only, no enforcement | None | LOW-MEDIUM |

**The hard truth:** Your memory system is really a *Claude Code memory system* with best-effort portability to other agents. The portable files (`memory/`, `dev/`, `DECISIONS.md`) work everywhere because they're just markdown. The enforcement layer (hooks) only exists for Claude Code. For the other agents, you're relying on the agent's willingness to follow instructions in a static file — which degrades with context pressure.

This is not a flaw in your design. It's a limitation of the agent ecosystems. Only Claude Code exposes a hook API. Everything else is static file ingestion.

---

## What's Actually Reusable Today

1. **The file structure** (`memory/semantic.md`, `memory/working.md`, `DECISIONS.md`, `dev/[task]/`) — 100% portable
2. **The preprompt text** — portable as an instruction block
3. **The stop.sh logic** — portable as a manual reminder script (even without hooks, you can run it yourself)
4. **The adapter generator pattern** — good idea, but currently hardcoded to applycling

---

## What's Blocking Reusability

1. **applycling-specific content in templates**
   - `.agent/templates/architecture.md` names `applycling/skills/`, `applycling/pipeline.py`, `applycling/llm.py`
   - Every adapter hardcodes the project description: "CLI tool that turns a job URL into..."
   - The `CLAUDE.md` adapter writes a 130-line project constitution specific to applycling

2. **No separation of concerns**
   - "Memory protocol" (generic: how to use semantic.md, working.md, DECISIONS.md) is mixed with
   - "Project architecture" (specific: skills system, pipeline, tracker, renderer)

3. **No project configuration**
   - The generator has no way to learn about a new project. It only knows applycling.

4. **Embedded in repo**
   - `.agent/` lives inside applycling. To use it elsewhere you'd have to copy-paste and edit, which defeats the purpose.
