# Project Context — applycling

**applycling** is CLI tool that turns a job URL into a complete application package: tailored resume, cover letter, positioning brief, email/InMail, and fit summary.

---

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

---

## Architecture

Before implementing a feature, read `vision.md`. It is the canonical record of architectural principles, load-bearing assumptions, and planned capabilities — not current build state (that lives in `memory/semantic.md`).


---

## Key conventions

- _clean_llm_output() strips code fences, preamble, leaked prompt markers, and trailing sign-offs from all LLM output — always apply it
- Profile summary section header must be ## PROFILE (all caps) to match the format template
- storage.save_config() merges — never call it with only partial keys unless merging is the intent
- Skill templates use `str.format` — escape braces with `{{` and `}}`
- Conditional logic stays in Python, not skill templates
- All API keys live in .env at repo root (gitignored)
- vision.md holds vision + assumptions only — on merge, move shipped capabilities to memory/semantic.md and remove from the Vision section; update Assumptions if a premise is invalidated
