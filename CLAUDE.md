# applycling — Developer Guide

**applycling** is CLI tool that turns a job URL into a complete application package: tailored resume, cover letter, positioning brief, email/InMail, and fit summary.

---

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
To add a new pipeline step, see ARCHITECTURE_VISION.md — section "Adding a New Pipeline Step".

---

## Skills architecture

All LLM prompt templates live in `applycling/skills/<name>/SKILL.md`. There are no prompt strings in Python source files.

Frontmatter is parsed with `pyyaml`. Template engine is plain `str.format` — no Jinja2, no exceptions.

---

## Key conventions

- _clean_llm_output() strips code fences, preamble, leaked prompt markers, and trailing sign-offs from all LLM output — always apply it
- Profile summary section header must be ## PROFILE (all caps) to match the format template
- storage.save_config() merges — never call it with only partial keys unless merging is the intent
- Skill templates use `str.format` — escape braces with `{{` and `}}`
- Conditional logic stays in Python, not skill templates
- All API keys live in .env at repo root (gitignored)
- Keep ARCHITECTURE_VISION.md canonical — update it when adding/removing skills, changing pipeline contract, introducing new providers, shipping phases, or discovering risks
