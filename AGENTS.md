# Project Context — applycling

**applycling** is a CLI tool that turns a job URL into a complete application package: tailored resume, cover letter, positioning brief, email/InMail, and fit summary.

---

## Memory System

This project uses a file-based memory system to maintain context across sessions.

### On Session Start

Read `memory/semantic.md` ONCE to load project context before answering.

### On Every Turn

Before answering:

1. Read memory/working.md for current state (semantic.md was loaded at session start)
2. If your reasoning feels uncertain or inconsistent with prior context, re-read memory/semantic.md
3. Only load /dev/[task]/* if this turn involves that specific task
4. Before calling any MCP tool for information, first check if it's already in semantic.md or context.md — local files are cheaper than remote MCP queries
5. Keep context minimal and relevant
6. If the user's message describes work outside the current working.md focus, ask:
   "This looks like a different task — should I archive the current state first?"
7. If context is missing:
   a. Check relevant dev/[task]/context.md
   b. If still unclear, state the assumption you are making explicitly
   c. Ask the user to confirm the assumption before proceeding with irreversible work
   d. Once confirmed, log the answer in dev/[task]/context.md under Assumptions

---

## Architecture

Before implementing a feature, read `ARCHITECTURE_VISION.md`. It is the canonical record of architectural principles.

### Skills Architecture

All LLM prompt templates live in `applycling/skills/<name>/SKILL.md` with YAML frontmatter:

```markdown
---
name: skill_name
description: One-line purpose
inputs:
  - input_key
output_file: result.md
model_hint: claude-3-5-haiku-20241022  # optional
temperature: 0.3  # optional
---
Prompt body using {input_key}.
```

Loader: `from applycling.skills import load_skill` → `load_skill(name).render(**kwargs)`

### Tracker

`get_store()` in `tracker/__init__.py` auto-detects Notion or SQLite. Use the `TrackerStore` interface — never call stores directly.

---

## Key Conventions

- All API keys in `.env` (gitignored)
- `_clean_llm_output()` strips code fences from LLM output
- Profile header: `## PROFILE` (all caps)
- `storage.save_config()` merges — don't call with partial keys
- Skill templates use `str.format` — escape braces with `{` and `}`
- Conditional logic stays in Python, not skills
