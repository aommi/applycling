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

- `memory/semantic.md` — propose updates; wait for approval before writing
- `memory/working.md` — update freely after each response; no approval needed
- `DECISIONS.md` — append-only; propose entries for approval
- `dev/[task]/context.md` — log confirmed assumptions immediately; no approval needed

---

## Architecture

Before implementing a feature, read `ARCHITECTURE_VISION.md`. It is the canonical record of architectural principles, product direction, design-decision rationale, and known risks.

These skill files follow the agentskills.io frontmatter standard — Hermes's `/skills` browser can enumerate them natively.


---

## Key conventions

- _clean_llm_output() strips code fences, preamble, leaked prompt markers, and trailing sign-offs from all LLM output — always apply it
- Profile summary section header must be ## PROFILE (all caps) to match the format template
- storage.save_config() merges — never call it with only partial keys unless merging is the intent
- Skill templates use `str.format` — escape braces with `{{` and `}}`
- Conditional logic stays in Python, not skill templates
- All API keys live in .env at repo root (gitignored)
- Keep ARCHITECTURE_VISION.md canonical — update it when adding/removing skills, changing pipeline contract, introducing new providers, shipping phases, or discovering risks

---

## Optional: Hermes Memory Mirroring

Hermes has its own `MEMORY.md` / `USER.md` persistence layer. These are complementary,
not replacements, for this project's `memory/` files. If you want high-signal lessons
visible inside Hermes's built-in persistence, you can symlink:

```bash
ln -s memory/semantic.md MEMORY.md
```

The project's `memory/semantic.md` remains the single source of truth.

<!-- skills:pm:start -->
## PM Skills

### sprint-scoping
Given a sprint plan (goals, architecture, resolved tier-1 design decisions), produce a set of actionable, sequenced, unambiguous implementation tickets that an autonomous agent or engineer can execute without asking clarifying questions

**When to use:** User provides a sprint plan and wants it translated into executable implementation tickets, or is scoping a sprint and wants to produce agent-ready work items.

**Full skill:** Read `skills/pm/sprint-scoping/SKILL.md` before responding.
<!-- skills:pm:end -->
