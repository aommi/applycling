# DECISIONS — applycling

Append-only architectural decisions log. To reverse a prior decision, append a new entry that explicitly supersedes it by date.

---

## 2026-04-21 — Memory System Implementation

**Decision:** Implement file-based memory system with hook enforcement per operational manual.

**Reasoning:**
- Solo developer workflow needs persistent context across sessions without token bloat
- Remote MCP calls for project knowledge are expensive and unnecessary — local markdown files are faster
- Hook-based enforcement ensures memory stays current without manual maintenance overhead
- Separation of concerns: `semantic.md` (long-lived knowledge, ≤500 tokens, approval-required updates), `working.md` (ephemeral state, ≤300 tokens, auto-updated), `DECISIONS.md` (append-only log)

**Impact:**
- CLAUDE.md updated with session-startup instruction to read `semantic.md`
- `hooks/preprompt.txt` injected before every user prompt — reads `working.md`, enforces "check local files before MCP" rule
- `hooks/stop.sh` fires after each response — inspects git diff, proposes memory updates for human approval
- `/dev/[task]/` structure for task-specific context (plan.md, context.md, tasks.md)
- Task-switching protocol: archive current `working.md` to `dev/[task]/context.md` before rewriting for new focus

**Rejected alternatives:**
- Notion-based memory (requires MCP call, slower than local file)
- Embedding-based retrieval (overkill for ≤500 token memory, adds infra dependency)
- No memory system (context lost every session, re-explanation tax)

**Affects:** CLAUDE.md, hooks/, memory/, dev/

---

## 2026-04-22 — Agent Agnostic Memory Adapters

**Decision:** Implement adapter pattern in `.agent/` to generate entry-point files and hook configurations for multiple AI coding agents (Claude Code, Codex, Cursor, Gemini CLI).

**Reasoning:**
- User is adding Codex (OpenAI) alongside Claude Code for coding tasks
- Memory files (`semantic.md`, `working.md`, `dev/`, `DECISIONS.md`) are portable, but entry-point files and hook mechanisms are agent-specific
- Without adapters: switching agents requires manual reconfiguration and loses memory continuity
- With adapters: run `python .agent/generate.py <agent>` and memory works across all tools

**Impact:**
- `.agent/` directory with adapter scripts per agent
- `generate.py` CLI generates:
  - Claude Code: `CLAUDE.md` + `.claude/settings.json` hooks
  - Codex: `AGENTS.md` (hooks not supported)
  - Cursor: `.cursor/rules/memory.mdc` with auto-attach globs
  - Gemini CLI: `GEMINI.md` + `.gemini/context.md`
- Memory files remain unchanged and shared
- `ARCHITECTURE_VISION.md` updated with agent agnosticism section

**Rejected alternatives:**
- Maintaining separate entry-point files manually (error-prone, drift between configs)
- Claude Code-only memory (locks user to one agent, defeats purpose of portable memory)
- Universal entry-point file (no such thing — each agent has its own convention)

**Affects:** `.agent/`, `ARCHITECTURE_VISION.md`, `memory/semantic.md`

---

## 2026-04-22 — Extended Agent Support (Windsurf, OpenClaw, Hermes)

**Decision:** Extend the adapter system with three additional agents: Windsurf, OpenClaw, and Hermes (Nous Research).

**Reasoning:**
- User adopted Windsurf and Hermes alongside Codex; without adapters each required manual re-configuration on every switch
- OpenClaw is already integrated with applycling's pipeline (see §4); aligning its system prompt with the same memory loading pattern avoids divergence
- Hermes supports the agentskills.io skill frontmatter standard natively — applycling skills are already in that shape, so `/skills` browsing works out of the box with no extra work

**Impact:**
- `generate.py` now supports 7 agents; `generate.py all` covers all of them
- Hermes and Codex both write `AGENTS.md`; hermes version is a superset (codex reads it fine)
- `.agent/templates/architecture.md` introduced as a shared template — eliminates 7-way drift when architecture evolves
- All adapters refactored to `Path.read_text()`/`write_text()`; `claude_code.py` hooks now deep-merge instead of replacing existing hook events
- `.agent/OPERATIONAL_MANUAL.md` updated with "Switching agents" command table

**Rejected alternatives:**
- Per-agent branches (merge overhead for one-person project)
- Asking each agent to read a single universal entry-point file (no such convention exists)

**Affects:** `.agent/`, `ARCHITECTURE_VISION.md`, `memory/semantic.md`, `.agent/OPERATIONAL_MANUAL.md`

---

## 2026-04-27 — Hermes Gateway For Telegram Intake

**Decision:** Use Hermes Agent's Telegram gateway (via a dedicated `applycling` profile) for inbound job URL intake, rather than building a custom Telegram polling listener inside applycling.

**Reasoning:**
- Hermes already ships a production-grade Telegram gateway with long-polling, multi-chat routing, DM pairing, slash commands, error recovery, and platform parity (Discord, Slack, WhatsApp share the same gateway layer).
- Building a custom listener inside applycling (~90 lines of `get_updates()`/`poll()` code) reinvents this surface with zero hardening: no multi-chat support, no auth, no error recovery, no background service management.
- Hermes profiles provide full isolation: the applycling bot gets its own Telegram token, model config, toolsets, SOUL.md, and session store. Adding a second bot later costs nothing.
- The Hermes profile is the Phase 1 validation vehicle. When applycling reaches SaaS scale (Phase 3), it gets its own standalone gateway — the Hermes profile outlives its usefulness gracefully.

**Impact:**
- Inbound Telegram intake: the `applycling-hermes` wrapper for `~/.hermes/profiles/applycling/` receives the URL, runs `.venv/bin/python -m applycling.cli telegram _run <url>`, pipeline delivers results via outbound `TelegramNotifier`.
- Hermes profile toolsets locked to `terminal` only — no browser, file system, or other tool access.
- `scripts/setup_hermes_telegram.sh` automates the entire profile provisioning (idempotent) and creates the `applycling-hermes` wrapper alias.
- Removed: custom `TelegramNotifier.get_updates()`, `poll()`, `telegram listen` command, `test_telegram_listener_contract.py`.
- Kept: outbound `TelegramNotifier.notify()` and `send_document()` — the delivery channel.

**Rejected alternatives:**
- Custom polling listener in applycling (redundant with Hermes gateway, ~90 lines of untested networking code, no multi-chat, no production hardening).
- Webhook-based intake (requires public HTTPS endpoint, DNS, TLS certs — Phase 3 infrastructure, not Phase 1).
- OpenClaw gateway (already the architecture vision's aspirational path, but Hermes is lighter-weight and already installed for the user's workflow).

**Affects:** `applycling/telegram_notify.py`, `applycling/cli.py`, `scripts/setup_hermes_telegram.sh`, docs/planning/, ARCHITECTURE_VISION.md

---

## 2026-04-27 — Two-Layer LLM Architecture

**Decision:** Decouple the LLM that handles Telegram message routing from the LLM that generates application packages. They use different providers, models, and config files.

**Reasoning:**
- The Hermes applycling profile needs a fast, cheap model for message comprehension and command dispatch (DeepSeek v4 Pro). The applycling pipeline needs a high-quality model for resume and cover letter generation (Anthropic Claude Sonnet 4.6).
- Mixing concerns would force suboptimal choices: either overpaying for the routing layer or underpowering the generation layer.
- Hermes profiles have isolated `.env` files — the setup script auto-merges parent API keys so both layers work without manual key duplication.

**Architecture:**
```
Telegram → Hermes (deepseek-v4-pro) → terminal → applycling pipeline (claude-sonnet-4-6) → PDFs
           │  ~/.hermes/profiles/         │              data/config.json
           │  applycling/config.yaml      │              .env (ANTHROPIC_API_KEY)
           │  .env (DEEPSEEK_API_KEY)      │
           └─ routing only ───────────────┘─ generation only ──────────────────────┘
```

**Impact:**
- `.env.example` updated to clarify which API keys belong to which layer
- `scripts/setup_hermes_telegram.sh` validates that the configured Hermes provider has a corresponding API key
- Applying a new machine: run `applycling telegram setup` once, then `scripts/setup_hermes_telegram.sh`

**Rejected alternatives:**
- Single model for both routing and generation (routing doesn't need Claude quality; using DeepSeek for generation produces inferior resumes).
- Same provider for both layers (locks the user into one ecosystem; Anthropic outage would kill both routing and generation).

**Affects:** `.env.example`, `scripts/setup_hermes_telegram.sh`, docs/

---

## 2026-04-23 — Skill Template Engine: str.format vs Jinja2

**Decision:** Use Python's built-in `str.format` as the sole template engine for skill files. Jinja2 is forbidden.

**Reasoning:**
- `str.format` is in the Python standard library — no external dependency
- Jinja2's control-flow syntax (`{% if %}`, `{% for %}`) encourages putting logic in templates, which violates the "conditional logic stays in Python" principle
- LLMs generate `str.format` placeholders more reliably than Jinja2 syntax
- Escaped braces (`{{` and `}}`) are sufficient for literal brace output; no need for Jinja2's complexity
- If template logic becomes complex, the correct fix is to move the logic to the Python caller and pre-compute strings, not to upgrade the template engine

**Impact:**
- All skill files use `{placeholder}` syntax with YAML frontmatter
- Callers pre-compute conditional strings and pass them as inputs
- `{{` and `}}` in skill bodies render as literal `{`/`}` after formatting

**Rejected alternatives:**
- Jinja2 (adds dependency, encourages template logic, overkill for simple string substitution)
- f-strings embedded in skills (not portable, require Python evaluation context)
- Custom template syntax (unnecessary when `str.format` exists)

**Affects:** `applycling/skills/`, `memory/semantic.md`, `ARCHITECTURE_VISION.md`

---

## 2026-04-28 — Canonical State Machine

**Decision:** Replace dual-vocabulary status chaos (old CLI: `tailored`, `interview`, `offer`; old workbench: `inbox`, `running`, `generated`, `skipped`) with a single canonical 11-state machine in `applycling/statuses.py`.

**Reasoning:**
- Multiple intake paths (CLI, UI, Telegram, API, MCP) were using different status vocabularies for the same lifecycle stages. Pipeline wrote `"tailored"`, UI read `"reviewing"`, Telegram showed intermediate states — no single view of job progress.
- A frozen-dataclass design (`Status`, `StatusAction`) with `frozenset` transitions makes the machine data-driven: templates, routes, and CLI all read from one source.
- `OLD_TO_NEW` migration handles legacy statuses at load time — no data migration required.

**Impact:**
- `applycling/statuses.py` — 11 states, 25 transitions, `STATUS_VALUES`, `STATUS_BY_VALUE`, `DEFAULT_INITIAL_STATUS`, `can_transition()`, `assert_valid_status()`.
- `StatusAction` dataclass — `target`, `label`, `css_class` — used by templates to render buttons data-driven instead of hardcoded.
- UI actions (`job_actions(status)`) and template globals (`status_color`, `status_label`) all derive from the same frozen data.
- `generating` is a system-only state (no user actions). `failed` has no status-transition actions — Regenerate is the only exit, handled as a separate command endpoint.

**Rejected alternatives:**
- Per-path state vocabularies (CLI uses X, UI uses Y) — causes data inconsistency, breaks cross-path visibility.
- SQL CHECK constraints for state validation — faster but duplicates the truth; Python validation keeps migration DB-independent.

**Affects:** `applycling/statuses.py`, `applycling/ui/routes.py`, `applycling/ui/templates/`, `applycling/tracker/__init__.py`

---

## 2026-04-28 — Regenerate As Command, Not Status Transition

**Decision:** Regenerate is a dedicated endpoint (`POST /jobs/{job_id}/regenerate`), not an action on any status. The UI renders a separate Regenerate button for `new`, `reviewing`, and `failed`.

**Reasoning:**
- Putting Regenerate in the status-action system as a `generating` transition was misleading — `generating` is a system-only intermediate state, not a user destination. The action set should represent user decisions about the job's lifecycle, not technical re-runs.
- Regenerate has different semantics from status transitions: it triggers a long-running pipeline, requires `asyncio.to_thread()`, and has its own guard logic (only allowed from `new`/`reviewing`/`failed`).

**Impact:**
- `POST /jobs/{job_id}/regenerate` in `routes.py` — calls `run_pipeline()` via `asyncio.to_thread()`.
- Template renders Regenerate button separately from status-action buttons.
- `run_pipeline()` guards starting status — rejects jobs in `applied`, `accepted`, `rejected`, etc.
- `new → generating` transition kept in `TRANSITIONS` for programmatic use but has no UI action — pipeline sets it internally.

**Rejected alternatives:**
- `generating` as a `StatusAction` on `new` and `reviewing` — creates a two-click flow (`new → generating → reviewing`) that confuses user intent.

**Affects:** `applycling/ui/routes.py`, `applycling/jobs_service.py`, `applycling/statuses.py`

---

## 2026-04-28 — `persist_job=False` for Duplicate Prevention

**Decision:** When the caller already owns the job row (workbench `run_pipeline`), pass `persist_job=False` through `PipelineContext` so `run_add()` creates a transient `Job` with the caller's id but skips `save_job()`. Metadata (title, company, fit_summary) is read from `job.json` in the assembled package folder.

**Reasoning:**
- The old approach — pipeline creates a second tracker row, caller finds it, copies fields, deletes it — was fragile, DB-dependent, and broke when the "find" heuristic failed.
- `persist_job=False` is a flag, not a side-effect. The pipeline creates the same `Job` object either way; the flag just gates `save_job()`. Adding `job_id` to `PipelineContext` lets the transient job carry the real workbench identity through package assembly (folder name, manifest `id`).
- Metadata consolidation via `job.json` manifest — `package.assemble()` now writes `fit_summary` into the manifest alongside `title`/`company`. The caller reads one file instead of parsing individual artifacts.

**Impact:**
- `PipelineContext` gains `persist_job: bool = True` and `job_id: str = ""`.
- `run_add()` uses `context.job_id` for the transient `Job`, skips `save_job()` when `persist_job=False`.
- `run_add_notify()` passes both params through.
- `jobs_service.run_pipeline()` calls `run_add_notify(persist_job=False, job_id=job_id)`, then reads metadata from `folder/job.json`.

**Rejected alternatives:**
- Find-and-delete duplicate (fragile heuristic, DB-dependent, breaks when tracker rows shift).
- Pipeline caller supplies metadata callback (adds coupling; manifest is self-contained).
- `run_add()` returns metadata without persisting at all (would require splitting `AddResult` — harder to roll back).

**Affects:** `applycling/pipeline.py`, `applycling/jobs_service.py`, `applycling/package.py`

---

## 2026-04-29 — Postgres Tracker Backend (opt-in, local dev only)

**Decision:** Add Postgres as an opt-in tracker backend via `APPLYCLING_DB_BACKEND=postgres` env var. SQLite remains the default. Defer connection pooling, multi-tenancy, and hosted Postgres to later phases.

**Reasoning:**
- **Backend selection:** `get_store()` checks `APPLYCLING_DB_BACKEND` before the Notion probe. Explicit `sqlite` skips Notion entirely. Unset falls back to legacy Notion→SQLite resolution.
- **Schema:** Alembic with hand-authored raw-SQL migrations (`op.create_table()`). No ORM (`target_metadata = None` intentional). Tables: `users`, `jobs`, `pipeline_runs`, `artifacts` with CHECK constraints and partial indexes on `deleted_at IS NULL`.
- **PostgresStore:** psycopg v3 with `dict_row` factory. UUID primary keys. `migrate_old_status()` on all writes. Non-UUID IDs raise `TrackerError` with a clear message. Timestamps owned by Python (DB defaults are safety-net only). `_COLUMNS` constant for explicit column lists.
- **Packaging:** `psycopg[binary]` in `[project.optional-dependencies] postgres` extra. SQLite-only users do not pull the ~10MB wheel. `pip install .[postgres]` for full Postgres support.
- **Docker:** `docker-compose.yml` with Postgres 16 + healthcheck. `Dockerfile` copies `pyproject.toml` + `README.md` + `applycling/` before `pip install .[postgres]` for layer caching.
- **Seed:** `applycling/db_seed.py` with well-known UUID `00000000-...-000001`. `ON CONFLICT DO NOTHING` — idempotent.
- **Status migration:** Frozen copy of `statuses.STATUS_VALUES` in migration CHECK constraint. Adding a status requires a paired migration (tracked as P2 drift risk).

**P2 deferred items (11 items, tracked in `docs/planning/LOCAL_WORKBENCH_SPRINT.md`):**
- Connection pooling (`psycopg_pool.ConnectionPool`)
- Test isolation (per-test cleanup fixture)
- Dockerfile `|| true` on Playwright install
- `env.py` URL normalization brittleness
- Migration downgrade missing `CASCADE`
- `docker-compose.yml` tty flags on `--help` container
- Raw `psycopg` INSERT in `test_load_jobs_scoped_to_user`
- `PLAYWRIGHT_CHROMIUM_EXECUTABLE` unused
- Shallow `sqlalchemy.url` in `alembic.ini`
- `_COLUMNS` excludes `status_reason`/`notion_page_id`
- Status enum drift between migration and `statuses.py`

**Impact:** Tracker abstraction now spans three backends. Postgres path is local single-user only — no auth, no multi-tenancy, no connection pool. Ready for local development use.

**Rejected alternatives:**
- ORM with SQLAlchemy models (adds dependency, project does not use ORM elsewhere).
- `sqlalchemy.url` left empty in `alembic.ini` (inconvenient for local dev; DATABASE_URL override in `env.py` covers security).
- Connection pool in this PR (unnecessary for single-user local tool; tracked for follow-up).

**Affects:** `applycling/tracker/`, `applycling/db_seed.py`, `migrations/`, `Dockerfile`, `docker-compose.yml`, `alembic.ini`, `pyproject.toml`, `tests/test_postgres_store.py`

**Cross-backend migration convention:** When a schema change ships (add/alter/drop column), the PR must update both the Alembic migration (Postgres) and `applycling/tracker/sqlite_store.py` table creation SQL (SQLite auto-creates schema on first use). NotionStore is document-based and has no schema concern. A schema change is not done until all active backends are updated.

---

## 2026-04-29 — Host Dogfooding Sprint Architecture

**Decision:** Ship private hosted dogfooding on a Kamatera VPS using Docker Compose, Caddy TLS, Postgres, app-level Basic Auth, active-run rejection, async in-process generation, durable bind-mounted artifacts, and Hermes-to-workbench intake via `/api/intake`.

**Reasoning:**
- Kamatera gives predictable $6/mo cost; Railway's resource billing was less predictable for dogfooding.
- Docker Compose + Caddy keeps the deployment portable without introducing platform-specific infrastructure.
- One active run per user is sufficient for private dogfood and prevents duplicate token-burning generations.
- Async in-process background tasks are acceptable for this stage because startup sweep marks orphaned runs failed after restart.
- Intake secret is separate from UI credentials because Hermes forwarding is machine-to-machine, not browser auth.

**Rejected alternatives:**
- Railway for first hosted dogfood deployment.
- Queue/worker pool before private dogfood validation.
- Custom Telegram polling inside applycling.
- Shared UI credentials for Hermes intake.

**Affects:** `docker-compose.prod.yml`, `Caddyfile`, `Dockerfile.hermes`, `applycling/ui/__init__.py`, `applycling/ui/routes.py`, `applycling/jobs_service.py`, `applycling/tracker/postgres_store.py`, `applycling/tracker/__init__.py`, `migrations/`, `docs/deploy/`

---

## 2026-05-04 — MCP Action Tools Shipped Before Non-Author Setup UX

**Decision:** Supersede the earlier sprint sequencing that deferred MCP action/refinement tools until after MCP-T4. MCP-T3 shipped before MCP-T4 because it was independent of non-author setup UX and completed the local MCP package loop.

**Reasoning:**
- MCP-T3 depended on MCP-T2's read surface, not on MCP-T4's setup documentation or local trial checklist.
- Implementing `update_job_status`, `interview_prep`, and `refine_package` early closed the CLI/MCP drift risk by extracting shared package-action helpers.
- Starting MCP-T4 against a complete tool surface gives the non-author trial a more accurate setup path.

**Impact:**
- MCP local package loop is now `add_job -> list_jobs -> get_package -> refine_package / interview_prep -> update_job_status`.
- `applycling/package_actions.py` is the shared helper boundary for CLI and MCP package actions; MCP must not call or shell out to CLI.
- Sprint sequencing is cleanup/documentation next, then MCP-T4 local setup UX, then alpha recruitment/session work.

**Supersedes:** 2026-05 sprint README sequencing that placed MCP-T4 before MCP-T3 and deferred action/refinement tools until after non-author validation.

**Affects:** `applycling/mcp_server.py`, `applycling/package_actions.py`, `applycling/cli.py`, `architecture/MCP.md`, `memory/semantic.md`, `docs/planning/sprints/2026-05-mcp-alpha/README.md`, `vision.md`

---

## 2026-05-05 — Folder-Per-Skill Directory Convention

**Decision:** Skills live as `applycling/skills/<name>/SKILL.md` (one directory per skill) rather than flat `applycling/skills/<name>.md` files.

**Reasoning:**
- The sprint explicitly plans learning loops with `LEARNED.md` per skill, injected as `{learned_patterns}` into renders. Once that ships, each skill directory will have at minimum two files (`SKILL.md` + `LEARNED.md`).
- The folder-per-skill convention follows the agentskills.io standard the loader already expects — `load_skill(name)` resolves to `skills/<name>/SKILL.md`.
- It provides a clear home for per-skill supporting files (`references/`, `templates/`, `scripts/`) without naming-convention gymnastics or later migration pain.
- The overhead of 16 directories vs 16 files is a one-time setup cost that pays off the moment any skill grows beyond a single file.

**Rejected alternatives:**
- Flat `skills/<name>.md` files: simpler to browse today, but creates a migration when `LEARNED.md` or supporting files arrive. Naming conventions like `answer_questions.learned.md` pollute the namespace and break the loader's existing resolution logic.
- Hybrid (flat for single-file skills, folders for multi-file): inconsistent, harder for the loader to resolve, and requires prediction of which skills will grow.

**Affects:** `applycling/skills/`, `applycling/skills/loader.py`
