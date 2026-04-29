# Semantic Memory — applycling

## Core Systems

- **Skills architecture:** 16 LLM prompts live in `applycling/skills/<name>/SKILL.md` with YAML frontmatter (name, description, inputs, output_file, model_hint, temperature). Loader in `applycling/skills/loader.py` — `load_skill(name).render(**kwargs)` validates inputs, renders via `str.format`.
- **Pipeline:** `applycling/pipeline.py` — `PipelineContext`, `PipelineStep`, `PipelineRun`. Linear deterministic flow: `role_intel → resume_tailor → profile_summary → format_resume → positioning_brief → cover_letter → email_inmail → fit_summary`. All callers (CLI, local workbench, OpenClaw) use this library API.
- **Additional capabilities:** `interview_prep` (composes `interview_prep` + `questions` skills) and `follow_up_outreach` (composes follow-up skills) — both shipped and usable today via CLI.
- **Queue/intake (partial):** `applycling/queue.py` — drives OpenClaw integration; not yet fully wired for multi-source intake.
- **LLM routing:** `applycling/llm.py` — ollama, anthropic, google, openai providers. API keys in `.env` (gitignored), loaded via `python-dotenv`.
- **Tracker abstraction:** `applycling/tracker/` — `get_store()` auto-detects Notion (`data/notion.json`) or falls back to SQLite. Never call stores directly from CLI.
- **Canonical state machine:** `applycling/statuses.py` — 11 states, 25 transitions, frozen dataclasses (`Status`, `StatusAction`). Single source of truth for all paths: CLI, UI, Telegram, API, MCP. `OLD_TO_NEW` maps legacy vocab (`tailored`, `interview`, `offer`, `inbox`, `running`, `generated`, `skipped`) to canonical states.
- **Local web workbench:** `applycling/ui/` — FastAPI + Jinja2 at `http://127.0.0.1:8080`. Job board, detail view, submit form, artifact serving, status transitions. Pipeline runs via `asyncio.to_thread()` (Playwright is sync). Regenerate is a dedicated endpoint (`POST /jobs/{id}/regenerate`), not a status transition — gated to `new`/`reviewing`/`failed`.
- **Pipeline duplicate-prevention:** `persist_job=False` in `PipelineContext` — when the caller owns the job row (workbench), `run_add()` creates a transient `Job` with the caller's id but skips `save_job()`. No duplicate rows, no fragile delete/merge.
- **Artifact fallback:** `jobs_service.list_artifacts()` scans the package folder when `artifacts.json` is missing (Telegram/CLI-created jobs). `_INFER_KIND` maps filenames to artifact kinds.
- **Renderer:** `applycling/render.py` — markdown → HTML → PDF via Playwright/Chromium. `h3 em { float: right }` right-aligns dates.
- **Agent agnosticism:** `.agent/generate.py <agent>` generates entry-point files + hooks for 7 agents: Claude Code, Codex, Hermes, Cursor, Gemini CLI, Windsurf, OpenClaw. Memory files (`memory/`, `dev/`, `DECISIONS.md`) are portable across all agents. Architecture vision doc: `vision.md` (was `ARCHITECTURE_VISION.md`).
- **Telegram intake (Phase 1):** Inbound job URLs reach applycling via a dedicated Hermes profile (`~/.hermes/profiles/applycling/`) and wrapper command `applycling-hermes`. The Hermes gateway polls Telegram, extracts the URL, and runs `.venv/bin/python -m applycling.cli telegram _run <url>`. Outbound delivery uses `applycling/telegram_notify.py`. Provision: `scripts/setup_hermes_telegram.sh`. See `DECISIONS.md` §2026-04-27.
- **Two-layer LLM:** Hermes profile uses DeepSeek for routing; applycling pipeline uses Anthropic Claude for generation. Configs: `~/.hermes/profiles/applycling/config.yaml` (routing) vs `data/config.json` (generation).

## Key Patterns

- **Thin harness, fat skills:** Python is boring plumbing. Intelligence lives in `.md` files.
- **Library-first design:** `pipeline.run_add()` is the public contract. CLI is a thin wrapper.
- **Deterministic pipeline:** User intent is always "URL → package". No agent routing needed yet (context-based resolvers are planned).
- **Escaped braces in skills:** `{{` and `}}` render as literal `{`/`}` after `str.format`.
- **Conditional logic stays in Python:** Skills have no `if/else`. Caller pre-computes strings, passes as inputs.

## Important Decisions (see DECISIONS.md for full log)

- **2026-04-21:** Memory system implemented — `memory/semantic.md` (≤500 lines), `memory/working.md` (≤300 lines), `DECISIONS.md` (append-only), `/dev/[task]/` for active work. Hooks: `preprompt.txt` (per-turn context), `stop.sh` (post-response memory proposals).

## Known Gotchas

- **Skill name mismatch:** Loader raises `SkillError` if frontmatter `name` doesn't match directory name.
- **Profile summary header:** Must be `## PROFILE` (all caps) to match format template.
- **`storage.save_config()` merges:** Never call with partial keys unless merging is intent.
- **`_clean_llm_output()` required:** Strips code fences, preamble, leaked prompt markers from all LLM output.
- **`_profile_header_markdown()` builds static header:** Constructs the name/contact block from `profile.json` for resume output. Never let the LLM generate this section — always use the pre-computed static header.

## Active Areas

- **Context-based resolvers (next):** Variant skills via `trigger`, `when`, `variant_of` frontmatter fields. First variant: `positioning_brief_ai.md` for AI/ML roles.
- **Learning loops (after):** `LEARNED.md` per skill, injected as `{learned_patterns}`.
- **User-override skills (later):** `~/.applycling/skills/` override built-ins.
