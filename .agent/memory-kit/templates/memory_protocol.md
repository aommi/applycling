## Memory System

This project uses a file-based memory system to maintain context across sessions.

### On Session Start

Read `memory/semantic.md` ONCE to load project context before answering.

### On Every Turn

The preprompt hook handles reading `memory/working.md`.

### Task Files

Only load `/dev/[task]/*` files when actively working on that task.

### MCP Efficiency

Before calling any MCP tool to retrieve information, first check if that information might exist in `memory/semantic.md` or `dev/[task]/context.md` — local files are cheaper than remote MCP queries.

### Keep Context Minimal

Do not speculatively load files "just in case".

### Mid-Session Drift

If reasoning becomes uncertain or inconsistent with prior context, re-read `memory/semantic.md` before continuing.

### Memory Discipline

- `memory/semantic.md` — current build state; propose updates; wait for approval before writing
- `memory/working.md` — live task state; update freely after each response; no approval needed
- `DECISIONS.md` — append-only log of architectural decisions; propose entries for approval
- `vision.md` (or project-configured name) — principles, load-bearing assumptions, planned capabilities; update only on merge when a capability ships or an assumption is invalidated; **never put current state here** (that's `semantic.md`), **never put planning details here** (tickets, checklists, phases)
- `dev/[task]/context.md` — log confirmed assumptions immediately; no approval needed

**DECISIONS.md vs. Assumptions distinction:**
- `DECISIONS.md` = immutable log — "we chose X on date Y because Z" — never edited, only superseded by appending
- vision doc Assumptions = live load-bearing premises — mutable; when invalidated, append a supersession to `DECISIONS.md` first, then update the assumption

**On PR merge:** check the vision doc — move shipped capabilities to `memory/semantic.md` and remove them from the Vision section; append a supersession to `DECISIONS.md` then update or remove any invalidated Assumption.
