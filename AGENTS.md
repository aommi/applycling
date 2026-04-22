# Project Context — applycling

**applycling** is a CLI tool that turns a job URL into a complete application package: tailored resume, cover letter, positioning brief, email/InMail, and fit summary. Supports Anthropic (Claude), Google AI Studio (Gemini), Ollama, and OpenAI.

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

Before implementing a feature, read `ARCHITECTURE_VISION.md`. It is the canonical record of architectural principles, product direction, and design-decision rationale.

### Skills

All LLM prompt templates live in `applycling/skills/<name>/SKILL.md`:

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
Prompt body using {input_key} via str.format.
```

Loader: `from applycling.skills import load_skill` → `load_skill(name).render(**kwargs)`
These skill files follow the agentskills.io frontmatter shape — Hermes's `/skills` browser can enumerate them natively.


### Pipeline

`applycling/pipeline.py` — library API with `PipelineContext`, `PipelineStep`, `PipelineRun`.
Linear flow: `role_intel → resume_tailor → profile_summary → format_resume → positioning_brief → cover_letter → email_inmail → fit_summary`

### LLM Routing

`applycling/llm.py` — supports ollama, anthropic, google, openai.
API keys in `.env` (gitignored), loaded via `python-dotenv`.

### Tracker

`get_store()` in `tracker/__init__.py` — auto-detects Notion or falls back to SQLite.
Use the `TrackerStore` interface only — never call either store directly from `cli.py`.

---

## Key Files

| File | Purpose |
|------|---------|
| `memory/semantic.md` | Distilled project knowledge (≤500 tokens) |
| `memory/working.md` | Live task state (≤300 tokens) |
| `DECISIONS.md` | Append-only decisions log |
| `dev/[task]/` | Active task context (plan.md, context.md, tasks.md) |
| `ARCHITECTURE_VISION.md` | Canonical architectural reference |

---

## Key Conventions

- `_clean_llm_output()` strips code fences from all LLM output — always apply it
- Profile header: `## PROFILE` (all caps)
- `storage.save_config()` merges — don't call with partial keys
- Skill templates use `str.format` — escape braces with `{{` and `}}`
- Conditional logic stays in Python, not skill templates
- All API keys in `.env` (gitignored)


---

## Optional: Hermes Memory Mirroring

Hermes has its own `MEMORY.md` / `USER.md` persistence layer. These are complementary,
not replacements, for this project's `memory/` files. If you want high-signal lessons
visible inside Hermes's built-in persistence, you can symlink:

```bash
ln -s memory/semantic.md MEMORY.md
```

The project's `memory/semantic.md` remains the single source of truth.
