# DECISIONS — applycling

Append-only architectural decisions log. To reverse a prior decision, append a new entry that explicitly supersedes it by date.

---

## 2026-04-21 — Memory System Implementation

**Decision:** Implement file-based memory system with hook enforcement per operational manual.

**Reasoning:**
- Solo developer workflow needs persistent context across sessions without token bloat
- Remote MCP calls for project knowledge are expensive and unnecessary — local markdown files are faster
- Hook-based enforcement ensures memory stays current without manual maintenance overhead
- Separation of concerns: `semantic.md` (long-lived knowledge, ≤500 tokens, approval-required updates), `working.md` (ephemeral state, ≤300 tokens, auto-updated), `DECISIONS.md` (append-only log)

**Impact:**
- CLAUDE.md updated with session-startup instruction to read `semantic.md`
- `hooks/preprompt.txt` injected before every user prompt — reads `working.md`, enforces "check local files before MCP" rule
- `hooks/stop.sh` fires after each response — inspects git diff, proposes memory updates for human approval
- `/dev/[task]/` structure for task-specific context (plan.md, context.md, tasks.md)
- Task-switching protocol: archive current `working.md` to `dev/[task]/context.md` before rewriting for new focus

**Rejected alternatives:**
- Notion-based memory (requires MCP call, slower than local file)
- Embedding-based retrieval (overkill for ≤500 token memory, adds infra dependency)
- No memory system (context lost every session, re-explanation tax)

**Affects:** CLAUDE.md, hooks/, memory/, dev/

---

## 2026-04-22 — Agent Agnostic Memory Adapters

**Decision:** Implement adapter pattern in `.agent/` to generate entry-point files and hook configurations for multiple AI coding agents (Claude Code, Codex, Cursor, Gemini CLI).

**Reasoning:**
- User is adding Codex (OpenAI) alongside Claude Code for coding tasks
- Memory files (`semantic.md`, `working.md`, `dev/`, `DECISIONS.md`) are portable, but entry-point files and hook mechanisms are agent-specific
- Without adapters: switching agents requires manual reconfiguration and loses memory continuity
- With adapters: run `python .agent/generate.py <agent>` and memory works across all tools

**Impact:**
- `.agent/` directory with adapter scripts per agent
- `generate.py` CLI generates:
  - Claude Code: `CLAUDE.md` + `.claude/settings.json` hooks
  - Codex: `AGENTS.md` (hooks not supported)
  - Cursor: `.cursor/rules/memory.mdc` with auto-attach globs
  - Gemini CLI: `GEMINI.md` + `.gemini/context.md`
- Memory files remain unchanged and shared
- `ARCHITECTURE_VISION.md` updated with agent agnosticism section

**Rejected alternatives:**
- Maintaining separate entry-point files manually (error-prone, drift between configs)
- Claude Code-only memory (locks user to one agent, defeats purpose of portable memory)
- Universal entry-point file (no such thing — each agent has its own convention)

**Affects:** `.agent/`, `ARCHITECTURE_VISION.md`, `memory/semantic.md`

---

## 2026-04-22 — Extended Agent Support (Windsurf, OpenClaw, Hermes)

**Decision:** Extend the adapter system with three additional agents: Windsurf, OpenClaw, and Hermes (Nous Research).

**Reasoning:**
- User adopted Windsurf and Hermes alongside Codex; without adapters each required manual re-configuration on every switch
- OpenClaw is already integrated with applycling's pipeline (see §4); aligning its system prompt with the same memory loading pattern avoids divergence
- Hermes supports the agentskills.io skill frontmatter standard natively — applycling skills are already in that shape, so `/skills` browsing works out of the box with no extra work

**Impact:**
- `generate.py` now supports 7 agents; `generate.py all` covers all of them
- Hermes and Codex both write `AGENTS.md`; hermes version is a superset (codex reads it fine)
- `.agent/templates/architecture.md` introduced as a shared template — eliminates 7-way drift when architecture evolves
- All adapters refactored to `Path.read_text()`/`write_text()`; `claude_code.py` hooks now deep-merge instead of replacing existing hook events
- `.agent/OPERATIONAL_MANUAL.md` updated with "Switching agents" command table

**Rejected alternatives:**
- Per-agent branches (merge overhead for one-person project)
- Asking each agent to read a single universal entry-point file (no such convention exists)

**Affects:** `.agent/`, `ARCHITECTURE_VISION.md`, `memory/semantic.md`, `.agent/OPERATIONAL_MANUAL.md`
