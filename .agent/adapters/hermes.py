"""
Hermes Agent Adapter — generates AGENTS.md (superset of the Codex adapter)

Hermes (Nous Research) reads AGENTS.md as workspace-level context and supports
the agentskills.io skill frontmatter standard natively via its /skills browser.

NOTE: Both this adapter and the Codex adapter write AGENTS.md. This version is
a superset — it adds the agentskills.io note and optional Hermes memory mirroring.
Codex reads the result fine. If you run both agents, use this adapter (or run
`generate.py all`, which runs codex then hermes so hermes wins).
"""
from pathlib import Path


def generate(project_root: Path):
    """Generate Hermes Agent configuration."""

    preprompt_path = project_root / ".agent" / "templates" / "preprompt.txt"
    with open(preprompt_path, "r") as f:
        preprompt_content = f.read()

    agents_md_content = f"""# Project Context — applycling

**applycling** is a CLI tool that turns a job URL into a complete application package:
tailored resume, cover letter, positioning brief, email/InMail, and fit summary.
Supports Anthropic (Claude), Google AI Studio (Gemini), Ollama, and OpenAI.

---

## Memory System

This project uses a file-based memory system to maintain context across sessions.

### On Session Start

Read `memory/semantic.md` ONCE to load project context before answering.

### On Every Turn

{preprompt_content.strip()}

---

## Architecture

Before implementing a feature, read `ARCHITECTURE_VISION.md`. It is the canonical
record of architectural principles, product direction, and design-decision rationale.

### Skills

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
Prompt body using {{input_key}} via str.format.
```

Loader: `from applycling.skills import load_skill` → `load_skill(name).render(**kwargs)`

These follow the agentskills.io frontmatter shape — Hermes's `/skills` browser can
enumerate them natively.

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
- Skill templates use `str.format` — escape braces with `{{{{` and `}}}}`
- Conditional logic stays in Python, not skill templates
- All API keys in `.env` (gitignored)

---

## Optional: Hermes Memory Mirroring

Hermes has its own `MEMORY.md` / `USER.md` persistence layer. These are complementary,
not replacements, for this project's `memory/` files. If you want high-signal lessons
visible inside Hermes's built-in persistence, you can mirror manually or symlink:

```bash
# Mirror preferences into Hermes's USER.md (optional)
ln -s memory/semantic.md MEMORY.md
```

The project's `memory/semantic.md` remains the single source of truth.
"""

    with open(project_root / "AGENTS.md", "w") as f:
        f.write(agents_md_content)

    return (
        "Hermes configuration generated:\n"
        "  - AGENTS.md (superset — also readable by Codex)\n\n"
        "Note: Hermes reads AGENTS.md natively. Skills in applycling/skills/ follow\n"
        "the agentskills.io frontmatter shape and are browsable via Hermes's /skills."
    )
