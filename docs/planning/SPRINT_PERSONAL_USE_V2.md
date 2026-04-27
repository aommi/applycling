# applycling — Telegram + Persistence Sprint Plan

**Status:** Updated after `docs/planning/DB_TECH_DESIGN.md` final review  
**Date:** 2026-04-27  
**Primary design reference:** `docs/planning/DB_TECH_DESIGN.md`

This sprint replaces the older Notion-centered personal-use plan. The current goal is to move applycling through the three approved implementation scopes:

1. **Local Telegram validation**
2. **Dockerized runtime + local Postgres + initial schema**
3. **Hosted SaaS persistence + private-beta gate**

Notion is deliberately out of the critical path. It may return later as optional sync/UI, but it is not part of this sprint.

---

## Sprint Goals

| Goal | Status |
|---|---|
| Prove real-phone Telegram URL → package → PDF delivery loop | Planned |
| Keep Phase 1 persistence validation-only with SQLite/local files | Planned |
| Add Docker/Compose for reproducible local + OSS setup | Planned |
| Add local Postgres + Alembic initial schema | Planned |
| Implement explicit DB backend selection | Planned |
| Implement initial `PostgresStore` for job tracking | Planned |
| Store hosted user profile/resume/stories/applicant profile in Postgres | Planned |
| Add SaaS/private-beta gates: tenant isolation, active-run guard, stale-run cleanup, rate limit, blocking, retry, PII inventory, restore drill | Planned |

---

## What Is Already Built

- `applycling/pipeline.py`
  - `PipelineContext`
  - `PipelineStep`
  - `PipelineRun`
  - `AddResult`
  - `run_add()`
  - `run_add_notify()`
  - `persist_add_result()`
- CLI commands:
  - `applycling add`
  - `applycling telegram setup`
  - `applycling telegram add`
  - `applycling telegram _run`
  - `applycling list`
  - `applycling status`
  - `applycling view`
  - `applycling refine`
- `applycling/tracker/`
  - `TrackerStore`
  - `SQLiteStore`
  - `NotionStore`
  - `get_store()`
- `applycling/telegram_notify.py`
- local `data/` and `output/` file conventions
- package generation pipeline and PDF rendering

Do not rebuild these. Patch gaps and route new persistence behind the existing abstractions.

---

## Architecture Commitments

- **Phase 1 is validation-only.** SQLite rows and local package paths may be discarded later.
- **Postgres is canonical for hosted/private beta.**
- **SQLite remains best-effort local/OSS fallback.**
- **Notion is not canonical and is not in this sprint.**
- **Backend selection is explicit:** `APPLYCLING_DB_BACKEND=sqlite|postgres`.
- **`DATABASE_URL` is only Postgres connection detail.**
- **No queueing in private beta.** One active `running` pipeline per user; reject additional runs.
- **Generated PDFs in Telegram are the user's durable private-beta copy until object storage exists.**

---

## End-of-Sprint User Stories

### Local Personal Use

From a laptop, the user can run:

```bash
applycling telegram add <job_url>
```

Then, from their phone, they receive:

- progress messages
- `resume.pdf`
- `cover_letter.pdf`
- a completion summary
- clear error messages if something fails

The package also exists locally under `output/` for inspection.

### Reproducible Developer Setup

A developer can clone the repo and run Docker Compose to get:

- app runtime
- local Postgres
- migrations
- Playwright/Chromium dependencies

Direct local Python usage still works without Docker.

### Private-Beta Persistence

Before external users are admitted:

- user/job/run data is stored in Postgres
- profile/resume/stories/applicant profile are stored in Postgres for hosted users
- users cannot read or mutate each other's jobs
- each user can have only one active run
- stale runs are cleaned up
- daily run limits and user blocking exist
- transient Postgres failures retry safely
- restore drill and PII inventory are complete

---

## Scope Order

```text
Scope 1: Local Telegram validation
  ├─ Ticket 1: Telegram E2E smoke harness
  └─ Ticket 2: Telegram gap fixes + completion contract

Scope 2: Dockerized runtime + local Postgres + initial schema
  ├─ Ticket 3: Docker/Compose + env docs
  ├─ Ticket 4: psycopg + Alembic + initial migration
  └─ Ticket 5: explicit backend selection + PostgresStore skeleton

Scope 3: Hosted SaaS persistence + private-beta gate
  ├─ Ticket 6: tenant-scoped store lifecycle + isolation tests
  ├─ Ticket 7: pipeline_runs operational controls
  ├─ Ticket 8: ArtifactStore local backend + contract test
  ├─ Ticket 9: reliability/privacy launch gates
  └─ Ticket 10: hosted/private-beta smoke and docs
```

---

## Sprint Acceptance Gate

Scope 1:

- [ ] Real phone can trigger a real job URL through the Hermes Telegram profile/gateway.
- [ ] Progress messages arrive.
- [ ] `resume.pdf` and `cover_letter.pdf` arrive in Telegram.
- [ ] Local package output exists.
- [ ] Failures are visible in logs or Telegram messages.

Scope 2:

- [ ] Docker Compose starts app + local Postgres.
- [ ] Direct Python CLI still works outside Docker.
- [ ] Alembic migration creates `users`, `user_contexts`, `jobs`, and `pipeline_runs`.
- [ ] `APPLYCLING_DB_BACKEND=postgres` + `DATABASE_URL` routes to Postgres.
- [ ] `PostgresStore` supports core `TrackerStore` operations for one user.
- [ ] Telegram path can run against local Postgres.

Scope 3:

- [ ] User A cannot read/update User B's jobs.
- [ ] A user cannot start multiple simultaneous hosted runs.
- [ ] Stale `running` runs are failed on startup/timeout.
- [ ] Daily count-based rate limit works.
- [ ] `is_blocked` prevents new runs.
- [ ] transient `OperationalError` retry behavior is implemented.
- [ ] local `ArtifactStore` contract test passes.
- [ ] PII inventory is documented.
- [ ] restore-from-backup drill is complete.
- [ ] private-beta onboarding says Telegram is the durable copy for PDFs until artifact storage is upgraded.

---

## Ticket 1 — Telegram E2E Smoke Harness

**Scope:** 1  
**Estimate:** 0.5 day  
**Files likely touched:** `applycling/cli.py`, `applycling/pipeline.py`, `applycling/telegram_notify.py`, docs/log notes as needed

### Goal

Run the Hermes-triggered Telegram path end-to-end against a real job URL and produce a precise gap list. Hermes owns inbound Telegram intake; applycling owns pipeline execution, outbound progress messages, and PDF delivery.

### Work

1. Configure/start the Hermes applycling Telegram profile/gateway.

   ```bash
   ./scripts/setup_hermes_telegram.sh
   applycling-hermes gateway status
   ```

   The script is idempotent and creates the `applycling-hermes` wrapper for `~/.hermes/profiles/applycling/`.
2. Send a real public job URL to the Hermes Telegram bot/profile.
3. Verify Hermes invokes applycling, using this command shape unless the local Hermes profile requires an equivalent wrapper:

   ```bash
   applycling telegram _run <real_job_url>
   ```

4. Tail `output/telegram_worker.log`.
5. Verify:
   - Hermes receives the Telegram URL
   - Hermes invokes applycling
   - worker starts
   - scraper succeeds
   - each pipeline status step emits a Telegram update
   - PDFs are generated
   - PDFs are below Telegram's file-size limit
   - documents are sent
   - local output folder exists
6. Document every observed failure in the ticket notes or a small sprint log.

### Acceptance

- There is a concrete pass/fail report for the Telegram path.
- Failures are specific enough to fix without rerunning discovery.
- `applycling telegram add <real_job_url>` remains usable as a terminal fallback/manual smoke path.

---

## Ticket 2 — Telegram Gap Fixes + Completion Contract

**Scope:** 1  
**Estimate:** 1 day  
**Depends on:** Ticket 1  
**Files likely touched:** `applycling/pipeline.py`, `applycling/cli.py`, `applycling/telegram_notify.py`

### Goal

Make the local Telegram validation loop reliable enough to use personally.

### Work

1. Fix failures discovered in Ticket 1.
2. Ensure completion message includes:
   - job title/company
   - job id
   - local package path
   - brief summary
   - note that local artifacts are validation/private-use storage
3. Ensure errors are visible:
   - scrape failure
   - LLM failure
   - package assembly failure
   - PDF send failure
4. Remove Notion expectations from the Telegram completion path for this sprint.

### Acceptance

- Real phone → real URL → progress messages → PDFs delivered.
- No Notion link required.
- Local output exists.
- Failures are understandable from Telegram/logs.

---

## Ticket 3 — Docker/Compose + Environment Docs

**Scope:** 2  
**Estimate:** 1 day  
**Files:** `Dockerfile`, `docker-compose.yml`, `.env.example`, `README.md` or docs

### Goal

Create reproducible local runtime for app + local Postgres while preserving direct Python CLI usage.

### Work

1. Add `Dockerfile` for the app runtime.
2. Include Playwright/Chromium/PDF rendering dependencies.
3. Add `docker-compose.yml` with:
   - app service
   - Postgres service
   - persistent Postgres volume
4. Update `.env.example` with:
   - `APPLYCLING_DB_BACKEND=sqlite|postgres`
   - `DATABASE_URL`
   - `APPLYCLING_ARTIFACT_BACKEND=local`
   - Telegram/model provider vars as applicable
5. Add quickstart docs for:
   - Docker path
   - direct local Python path

### Acceptance

- `docker compose up` starts Postgres and app runtime.
- `docker compose run app applycling --help` works.
- Direct local Python CLI still works without Docker.

---

## Ticket 4 — psycopg + Alembic + Initial Migration

**Scope:** 2  
**Estimate:** 1 day  
**Depends on:** Ticket 3  
**Files:** dependency config, `alembic.ini`, `migrations/`, migration env files

### Goal

Create the hosted/private-beta schema locally in Postgres.

### Work

1. Add `psycopg` v3 dependency.
2. Initialize Alembic.
3. Create initial migration:
   - `users`
   - `user_contexts`
   - `jobs`
   - `pipeline_runs`
4. Migration must include:
   - UUID primary keys
   - `telegram_id BIGINT UNIQUE NULL`
   - `email TEXT UNIQUE NULL`
   - `is_blocked BOOLEAN NOT NULL DEFAULT FALSE`
   - `user_contexts.profile_json JSONB`
   - `user_contexts.applicant_profile_json JSONB`
   - `user_contexts.resume_markdown TEXT`
   - `user_contexts.stories_markdown TEXT`
   - `deleted_at`
   - FK `ON DELETE RESTRICT` for user-owned data
   - `pipeline_runs.job_id ON DELETE SET NULL`
   - `pipeline_runs.status` CHECK constraint
   - `status_reason` length check
   - tenant-leading indexes
   - active-run unique partial index on `running`
   - `heartbeat_at`

### Acceptance

- Migration applies cleanly against Compose Postgres.
- Migration rolls back cleanly if rollback is supported for this first migration.
- Schema matches `DB_TECH_DESIGN.md`.

---

## Ticket 5 — Explicit Backend Selection + PostgresStore Skeleton

**Scope:** 2  
**Estimate:** 1 day  
**Depends on:** Ticket 4  
**Files:** `applycling/tracker/__init__.py`, new `applycling/tracker/postgres_store.py`, tests

### Goal

Route tracker operations to Postgres when explicitly configured.

### Work

1. Update `get_store()` selection:
   - unset `APPLYCLING_DB_BACKEND` → SQLite default
   - `APPLYCLING_DB_BACKEND=sqlite` → SQLite
   - `APPLYCLING_DB_BACKEND=postgres` → Postgres, requiring `DATABASE_URL`
2. Ensure Notion config does not override Postgres.
3. Implement `PostgresStore` skeleton:
   - constructor accepts `database_url` and user context
   - `save_job`
   - `load_jobs`
   - `load_job`
   - `update_job`
4. Use request/user-scoped construction even if Scope 2 tests only one user.
5. Add tests for backend selection and single-user CRUD.

### Acceptance

- SQLite remains default for direct local CLI.
- Postgres is used only when explicitly selected.
- Core tracker operations work against local Postgres.
- Telegram path can run with local Postgres when `APPLYCLING_DB_BACKEND=postgres` and `DATABASE_URL` are set.

---

## Ticket 6 — Tenant-Scoped Store Lifecycle + Isolation Tests

**Scope:** 3  
**Estimate:** 1 day  
**Depends on:** Ticket 5  
**Files:** `applycling/tracker/postgres_store.py`, Telegram/CLI entry paths, tests

### Goal

Make hosted persistence safe for multiple users.

### Work

1. Ensure hosted stores are user/request scoped.
2. Telegram path derives user identity from Telegram user/chat context.
3. Every Postgres query scopes by `user_id`.
4. Add hosted user-context load path:
   - hosted mode reads profile/resume/stories/applicant profile from `user_contexts`
   - local CLI keeps file-backed `storage.load_*()` behavior
5. Add minimal admin/CLI import path for private-beta user context.
6. Add integration test:
   - create User A
   - create User B
   - create job for User A
   - from User B scoped store, assert `load_job(a_job_id)` fails
   - from User B scoped store, assert `update_job(a_job_id)` fails

### Acceptance

- Tenant-isolation test passes.
- No process-global Postgres store carries user state.
- Hosted user context can be imported and loaded for a user.

---

## Ticket 7 — pipeline_runs Operational Controls

**Scope:** 3  
**Estimate:** 1.5 days  
**Depends on:** Ticket 6  
**Files:** new run persistence module or tracker extension, pipeline/Telegram entry path, tests

### Goal

Use `pipeline_runs` for audit, active-run guard, stale-run cleanup, daily rate limits, and blocking.

### Work

1. Create run persistence operations for:
   - create `running` run
   - mark generated/artifacts_persisted/delivered/failed
   - set `status_reason`
   - update `heartbeat_at`
2. Enforce active-run guard:
   - if user has active `running` run, reject new run with friendly Telegram message
3. Add startup stale-run cleanup:
   - orphaned `running` rows older than threshold → `failed`
   - `status_reason='orphaned_after_process_restart'`
4. Add daily count-based rate limit from `pipeline_runs`.
5. Honor `users.is_blocked`.

### Acceptance

- User cannot start two simultaneous hosted runs.
- Stale `running` runs are cleaned up.
- Daily rate limit prevents excess runs.
- Blocked user cannot start a run.
- Failed runs have useful `status_reason`.

---

## Ticket 8 — ArtifactStore Local Backend + Contract Test

**Scope:** 3  
**Estimate:** 1 day  
**Depends on:** Ticket 7 can run partially parallel after schema is stable
**Files:** new artifact module, pipeline persistence path, tests

### Goal

Introduce the artifact abstraction without implementing object storage yet.

### Work

1. Define `ArtifactStore` interface:
   - store
   - retrieve
   - list
   - delete
2. Implement local backend.
3. Wire package persistence through local backend where appropriate.
4. Store local package path on `pipeline_runs.package_path`.
5. Add contract test exercising store/retrieve/list/delete.

### Acceptance

- Local backend contract test passes.
- Existing local package output still works.
- No S3/GCS configs are advertised.

---

## Ticket 9 — Reliability + Privacy Launch Gates

**Scope:** 3  
**Estimate:** 1 day  
**Depends on:** Tickets 6–8  
**Files:** docs, store error handling, Telegram error handling, tests as needed

### Goal

Close private-beta operational gates.

### Work

1. Add transient `OperationalError` retry according to the retry-safety table.
2. Ensure `updated_at` is application-managed on inserts/updates.
3. Truncate/sanitize Telegram-facing failure messages.
4. Keep full failure details in Postgres within `status_reason` length limit.
5. Document PII inventory:
   - Telegram user id
   - resume
   - applicant profile
   - compensation expectations
   - work authorization
   - sponsorship status
   - generated artifacts
6. Document manual deletion request posture and backup retention assumptions.
7. Perform and document restore-from-backup drill against staging.

### Acceptance

- Retry behavior covered by tests or documented smoke.
- PII inventory exists in docs.
- Restore drill result is recorded.
- Telegram errors are readable and bounded.

---

## Ticket 10 — Hosted/Private-Beta Smoke + User Comms

**Scope:** 3  
**Estimate:** 0.5–1 day  
**Depends on:** Tickets 6–9  
**Files:** docs, Telegram completion/onboarding messages, deployment notes

### Goal

Validate the private-beta launch path and set user expectations.

### Work

1. Run hosted/private-beta smoke:
   - configured Postgres
   - real Telegram user
   - real job URL
   - full PDF delivery
   - run records created
2. Add onboarding/welcome wording:
   - generated PDFs are delivered in Telegram
   - Telegram is the durable private-beta copy until artifact storage is upgraded
   - old artifacts may not be redownloadable from the bot
3. Confirm cut-line items remain deferred:
   - Notion sync
   - object storage
   - web dashboard expansion
   - billing/tiered limits

### Acceptance

- Hosted/private-beta smoke passes.
- User-facing limitation around artifact durability is documented.
- Sprint is ready for external private-beta users.

---

## Out of Scope

- Notion sync or Notion schema migration
- bidirectional Notion state sync
- web dashboard implementation
- object storage/S3/GCS
- `artifacts` table
- queueing pipeline runs
- billing or tiered plans
- pretty per-user job display numbers
- one-time SQLite-to-Postgres personal data import
- `applycling answer` command
- onboarding UI implementation
- Hermes autonomous pipeline execution

---

## Notes for Implementing Agents

- Read `docs/planning/DB_TECH_DESIGN.md` before implementation.
- Keep Phase 1 changes narrow: prove Telegram delivery, do not build SaaS infrastructure early.
- Use `apply_patch` for code edits.
- Keep Notion out of the critical path.
- Preserve direct local Python workflow.
- Do not let `DATABASE_URL` alone select Postgres; use `APPLYCLING_DB_BACKEND`.
- Do not introduce `queued` status until a real queue worker exists.
- Do not advertise S3/GCS artifact backends until implemented.
- After every ticket, run the narrowest meaningful verification before moving on.
