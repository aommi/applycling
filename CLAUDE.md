# applycling — Developer Guide

**applycling** is CLI tool that turns a job URL into a complete application package: tailored resume, cover letter, positioning brief, email/InMail, and fit summary.

<!-- amk:start -->
## Memory System (Session Startup + Hooks)

**On session start:** Read `memory/semantic.md` ONCE to load project context.

**On every turn:** The preprompt hook (`hooks/preprompt.txt`) handles reading `memory/working.md`.

**Task files:** Only load `/dev/[task]/*` files when actively working on that task.

**MCP efficiency:** Before calling any MCP tool to retrieve information, first check if that information might exist in `memory/semantic.md` or `dev/[task]/context.md` — local files are cheaper than remote MCP queries.

**Keep context minimal:** Do not speculatively load files "just in case".

**Mid-session drift:** If reasoning becomes uncertain or inconsistent with prior context, re-read `memory/semantic.md` before continuing.

---

## Architecture vision

Before implementing a feature, read `ARCHITECTURE_VISION.md`. It is the canonical record of architectural principles, product direction, design-decision rationale, and known risks.
<!-- amk:end -->
<!-- skills:pm:start -->
## PM Skills

### sprint-scoping
Given a sprint plan (goals, architecture, resolved tier-1 design decisions), produce a set of actionable, sequenced, unambiguous implementation tickets that an autonomous agent or engineer can execute without asking clarifying questions

**When to use:** User provides a sprint plan and wants it translated into executable implementation tickets, or is scoping a sprint and wants to produce agent-ready work items.

**Full skill:** Read `skills/pm/sprint-scoping/SKILL.md` before responding.
<!-- skills:pm:end -->
