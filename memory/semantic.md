# Semantic Memory — applycling

## Core Systems

- **Skills architecture (T7):** 16 LLM prompts live in `applycling/skills/<name>/SKILL.md` with YAML frontmatter (name, description, inputs, output_file, model_hint, temperature). Loader in `applycling/skills/loader.py` — `load_skill(name).render(**kwargs)` validates inputs, renders via `str.format`.
- **Pipeline (T2):** `applycling/pipeline.py` — `PipelineContext`, `PipelineStep`, `PipelineRun`. Linear deterministic flow: `role_intel → resume_tailor → profile_summary → format_resume → positioning_brief → cover_letter → email_inmail → fit_summary`. All callers (CLI, OpenClaw, future web UI) use this library API.
- **LLM routing:** `applycling/llm.py` — ollama, anthropic, google, openai providers. API keys in `.env` (gitignored), loaded via `python-dotenv`.
- **Tracker abstraction:** `applycling/tracker/` — `get_store()` auto-detects Notion (`data/notion.json`) or falls back to SQLite. Never call stores directly from CLI.
- **Renderer:** `applycling/render.py` — markdown → HTML → PDF via Playwright/Chromium. `h3 em { float: right }` right-aligns dates.

## Key Patterns

- **Thin harness, fat skills:** Python is boring plumbing. Intelligence lives in `.md` files.
- **Library-first design:** `pipeline.run_add()` is the public contract. CLI is a thin wrapper.
- **Deterministic pipeline:** User intent is always "URL → package". No agent routing needed yet (T8+ will add context-based resolvers).
- **Escaped braces in skills:** `{{` and `}}` render as literal `{`/`}` after `str.format`.
- **Conditional logic stays in Python:** Skills have no `if/else`. Caller pre-computes strings, passes as inputs.

## Important Decisions (see DECISIONS.md for full log)

- **2026-04-21:** Memory system implemented — `memory/semantic.md` (≤500 tokens), `memory/working.md` (≤300 tokens), `DECISIONS.md` (append-only), `/dev/[task]/` for active work. Hooks: `preprompt.txt` (per-turn context), `stop.sh` (post-response memory proposals).

## Known Gotchas

- **Skill name mismatch:** Loader raises `SkillError` if frontmatter `name` doesn't match directory name.
- **Profile summary header:** Must be `## PROFILE` (all caps) to match format template.
- **`storage.save_config()` merges:** Never call with partial keys unless merging is intent.
- **`_clean_llm_output()` required:** Strips code fences, preamble, leaked prompt markers from all LLM output.

## Active Areas

- **T8 (next):** Context-based resolvers + variant skills (`trigger`, `when`, `variant_of` frontmatter fields). First variant: `positioning_brief_ai.md` for AI/ML roles.
- **T9 (after):** Learning loops — `LEARNED.md` per skill, injected as `{learned_patterns}`.
- **T10 (later):** User-override skills in `~/.applycling/skills/`.
