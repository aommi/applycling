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
- `ARCHITECTURE_VISION.md` — principles, load-bearing assumptions, planned capabilities; update only on merge when a capability ships or an assumption is invalidated; **never put current state here** (that's `semantic.md`), **never put planning details here** (tickets, checklists, phases)
- `dev/[task]/context.md` — log confirmed assumptions immediately; no approval needed

**DECISIONS.md vs. Assumptions distinction:**
- `DECISIONS.md` = immutable log — "we chose X on date Y because Z" — never edited, only superseded by appending
- `ARCHITECTURE_VISION.md` Assumptions = live load-bearing premises — mutable; when invalidated, append a supersession to `DECISIONS.md` first, then update the assumption

**On PR merge:** check `ARCHITECTURE_VISION.md` — mark shipped capabilities as built by moving them to `memory/semantic.md` and removing from the Vision section; remove or rewrite any Assumption the merge invalidates.

---

## Architecture vision

Before implementing a feature, read `ARCHITECTURE_VISION.md`. It is the canonical record of architectural principles, load-bearing assumptions, and planned capabilities — not current build state (that lives in `memory/semantic.md`).

These skill files follow the agentskills.io frontmatter standard — Hermes's `/skills` browser can enumerate them natively.


---

## Key conventions

- _clean_llm_output() strips code fences, preamble, leaked prompt markers, and trailing sign-offs from all LLM output — always apply it
- Profile summary section header must be ## PROFILE (all caps) to match the format template
- storage.save_config() merges — never call it with only partial keys unless merging is the intent
- Skill templates use `str.format` — escape braces with `{{` and `}}`
- Conditional logic stays in Python, not skill templates
- applycling pipeline API keys live in `.env` at repo root (gitignored). Hermes gateway keys live in `~/.hermes/profiles/applycling/.env`, populated by `scripts/setup_hermes_telegram.sh`. See `.env.example` for which keys power which layer.
- **Two-layer LLM architecture:** Hermes (DeepSeek) routes Telegram messages; applycling pipeline (Anthropic Claude) generates packages. See `DECISIONS.md` §2026-04-27.
- **Hermes applycling profile:** Inbound Telegram intake runs through the `applycling-hermes` wrapper for `~/.hermes/profiles/applycling/`. Profile has toolsets locked to `terminal` only. Provision via `scripts/setup_hermes_telegram.sh`.
- `ARCHITECTURE_VISION.md` holds vision + assumptions only — on merge, move shipped capabilities to `memory/semantic.md` and remove from the Vision section; update Assumptions if a premise is invalidated

---

## Hermes Profile (Telegram Gateway)

The project ships a dedicated Hermes profile for Telegram intake: `~/.hermes/profiles/applycling/`.

- **Provision:** `./scripts/setup_hermes_telegram.sh` (idempotent)
- **Start/install:** `applycling-hermes gateway install`
- **Status:** `applycling-hermes gateway status`
- **Logs:** `~/.hermes/profiles/applycling/logs/gateway.log`
- **SOUL.md:** Located at `~/.hermes/profiles/applycling/SOUL.md` — single-purpose: receives URL, runs `.venv/bin/python -m applycling.cli telegram _run <url>`
- **Toolsets:** Terminal only. All other tools (browser, vision, file, etc.) are disabled.
- **Model:** deepseek-v4-pro (routing only — pipeline uses its own config)
- **Naming caution:** `hermes profile create applycling` may also create a bare `applycling` wrapper in `~/.local/bin`. Use `applycling-hermes` for Hermes commands and `python3 -m applycling.cli ...` for the project CLI.

<!-- skills:pm:start -->
## PM Skills

### sprint-scoping
Given a sprint plan (goals, architecture, resolved tier-1 design decisions), produce a set of actionable, sequenced, unambiguous implementation tickets that an autonomous agent or engineer can execute without asking clarifying questions

**When to use:** User provides a sprint plan and wants it translated into executable implementation tickets, or is scoping a sprint and wants to produce agent-ready work items.

**Full skill:** See `CLAUDE.md` → PM Skills → sprint-scoping.
<!-- skills:pm:end -->
