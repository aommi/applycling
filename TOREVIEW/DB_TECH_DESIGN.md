# applycling — Database and Hosted Persistence Tech Design

**Date:** 2026-04-27  
**Status:** Finalized for user review; implementation may begin after final user approval  
**Authors / reviewers:** design evolved through Claude Opus 4.7 review, GPT-5.5 review, and user decisions  
**Supersedes:** `/Users/amirali/Documents/dev/files/DB selection.md` (April 26, 2026; SQLite + WAL recommendation)

---

## 1. Executive Decision

applycling will use a phased persistence strategy:

1. **Phase 1 — Local + Telegram validation**
   - Validate the highest-risk product loop first:

     ```text
     Telegram job URL -> applycling pipeline -> generated package -> PDFs delivered back in Telegram
     ```

   - Use SQLite and local files.
   - Treat Phase 1 persistence as validation-only. SQLite job rows and local package paths are not guaranteed to migrate into the SaaS database.
   - Notion is not required.

2. **Phase 2 — Dockerized reproducible runtime**
   - Add Docker and Docker Compose for reproducible OSS/local/cloud setup.
   - Keep direct local Python CLI use available.
   - Compose should run the app and local Postgres so hosted persistence can be tested before launch.

3. **Phase 3 — SaaS persistence before external users**
   - Use PostgreSQL as the canonical hosted database.
   - Use UUID primary keys for `users` and `jobs`.
   - Add `pipeline_runs` in the first hosted migration.
   - Use Alembic with raw SQL migrations and `psycopg` v3.
   - Keep SQLite as best-effort local/personal/OSS fallback only.
   - Defer Notion in hosted mode until after public beta.
   - Use local artifact storage for private beta, behind an `ArtifactStore` abstraction that can later switch to S3/GCS/object storage.

The old SQLite + WAL recommendation remains valid only for a single-machine personal/local deployment. It is not the SaaS/cloud design.

---

## 2. Product Context

applycling is a Telegram-first AI pipeline that turns a job URL into a complete application package:

- tailored resume
- cover letter
- positioning brief
- email/InMail
- fit summary
- package delivery back to the user

Today, applycling is a local CLI-oriented tool with:

- file-backed user profile/resume/config
- SQLite tracker fallback
- optional Notion tracker integration
- generated package files written under `output/`
- Telegram delivery path via `run_add_notify()`

The product is being extended toward:

- short-term Telegram validation for personal/private use
- a private SaaS beta in roughly one month
- future lightweight web dashboard
- optional future Notion sync/UI layer

---

## 3. Confirmed Assumptions

These assumptions are now confirmed for this design.

| ID | Assumption | Status | Impact |
|---|---|---|---|
| A1 | SaaS/private beta is planned in roughly one month. | Confirmed | Design for Postgres before external users, but validate Telegram loop first. |
| A2 | Phase 1 does not need durable SaaS-grade persistence. | Confirmed | SQLite/local files are acceptable for Telegram validation. |
| A3 | Phase 1 persistence may be discarded. | Confirmed | Do not overbuild migrations from Phase 1 SQLite rows into hosted Postgres. |
| A4 | Losing old generated artifacts during private beta is acceptable if users already received PDFs in Telegram. | Confirmed by user | Local Railway volume is acceptable at private beta; object storage can wait. |
| A5 | Notion must not be canonical storage. | Confirmed | Notion is deferred in hosted mode and later returns only as optional sync/UI. |
| A6 | SQLite should remain useful for OSS/personal local use. | Confirmed | Keep SQLite as best-effort fallback, not as full SaaS parity backend. |
| A7 | Docker is worth adding early. | Confirmed | Use Docker/Compose for reproducible OSS/local/cloud runtime, but keep direct Python workflow. |
| A8 | One active pipeline run per user is the intended SaaS behavior. | Confirmed as a design requirement | Phase 3 must enforce an active-run guard, not only daily rate limits. |

---

## 4. Current Architecture

Relevant code today:

- `applycling/pipeline.py`
  - `PipelineContext`
  - `PipelineRun`
  - `AddResult`
  - `run_add()`
  - `run_add_notify()`
  - `persist_add_result()`
- `applycling/tracker/`
  - `TrackerStore` abstraction
  - `SQLiteStore`
  - `NotionStore`
  - `get_store()`
- `applycling/telegram_notify.py`
  - Telegram message/document delivery
- `data/`
  - local config/profile/resume/stories/tracker files
- `output/`
  - generated application packages

Current limitations:

- no `user_id` concept in tracker schema
- `jobs.id` is local sequential text in SQLite
- Notion can currently replace SQLite as the selected tracker backend
- package artifacts are local filesystem paths
- no hosted migration framework
- no run ledger suitable for rate limits, retries, failure audit, or SaaS operations

---

## 5. Functional Requirements

### Phase 1 — Telegram Validation

FR1. A user can submit a job URL through the Telegram path.

FR2. applycling runs the existing package-generation pipeline from that URL.

FR3. applycling sends progress updates to Telegram.

FR4. applycling sends generated PDFs back to Telegram.

FR5. applycling writes local output artifacts for inspection/debugging.

FR6. SQLite may record a local job row, but that row is validation-only and may be discarded later.

FR7. Phase 1 does not require Postgres, Alembic, object storage, web dashboard, Notion, tenant isolation, or billing.

### Phase 2 — Docker Runtime

FR8. The repository provides a `Dockerfile` for the app runtime.

FR9. The repository provides `docker-compose.yml` for local reproducible setup.

FR10. Compose includes local Postgres for Phase 3 development.

FR11. `.env.example` documents required environment variables.

FR12. Direct local Python CLI usage remains supported for fast personal use.

### Phase 3 — SaaS Persistence

FR13. Hosted mode uses PostgreSQL as canonical storage.

FR14. Hosted mode stores users in a `users` table with UUID primary keys.

FR15. Hosted mode stores jobs in a `jobs` table with UUID primary keys and tenant ownership.

FR16. Hosted mode stores pipeline attempts in `pipeline_runs`.

FR17. Hosted mode enforces tenant isolation on every user-owned query.

FR18. Hosted mode enforces one active pipeline run per user.

FR19. Hosted mode supports a simple count-based daily rate limit.

FR20. Hosted mode supports blocking abusive users.

FR21. Hosted mode records failed runs with enough detail to debug without grepping local logs.

FR22. Hosted mode uses Alembic migrations.

FR23. Hosted mode uses `psycopg` v3, not `psycopg2`.

FR24. Hosted mode does not use Notion as a backend.

FR25. Hosted mode uses local artifact storage for private beta, behind an `ArtifactStore` interface.

---

## 6. Non-Functional Requirements

NFR1. **Security / tenant isolation:** User A must not be able to read, update, or infer User B's jobs or pipeline runs.

NFR2. **Privacy:** The system stores sensitive personal data, including Telegram user id, resume content, job application content, applicant profile, compensation expectations, work authorization, sponsorship status, and generated application materials.

NFR3. **Reliability:** Postgres transient connection failures should retry at least once after reconnecting.

NFR4. **Auditability:** Public/private beta runs must be inspectable through `pipeline_runs`.

NFR5. **Cost control:** Daily run limits and user blocking must exist before external users are admitted.

NFR6. **Recoverability:** Before external users are admitted, perform a restore-from-backup drill against staging.

NFR7. **Portability:** Dockerized app runtime should be deployable across Railway, GCP, AWS, Fly.io, Render, or similar container hosts.

NFR8. **OSS usability:** SQLite remains available for local/personal CLI use without requiring Postgres.

NFR9. **Simplicity:** Avoid SQLAlchemy unless SQLite parity is upgraded to a product requirement. Current decision is direct `psycopg` + raw SQL migrations.

NFR10. **Explicit degradation:** SQLite fallback may lag SaaS features and is not a supported multi-user backend.

---

## 7. Database Backend Decision

### Hosted SaaS

Use PostgreSQL.

Reasons:

- works across containerized services
- supports concurrent multi-user access
- fits Railway/GCP/AWS managed database offerings
- mature operational tooling
- supports tenant-leading indexes, UUIDs, transactions, and migrations cleanly

### Local / OSS / Personal CLI

Keep SQLite as best-effort fallback.

Contract:

- supports core local CLI tracking
- may retain simple sequential local ids
- no Alembic parity guarantee
- no SaaS tenant-isolation guarantee
- no guaranteed support for every Postgres-only feature
- no Notion-as-canonical behavior

### Notion

Notion is not a database backend for SaaS.

Decision:

- defer Notion entirely in hosted mode until after public beta
- later reintroduce it only as optional sync/UI fed from canonical storage
- do not let `data/notion.json` override Postgres in hosted mode

---

## 8. Runtime and Deployment Decision

Docker is part of the implementation plan.

Required:

- `Dockerfile`
- `docker-compose.yml`
- `.env.example`
- direct Python CLI path remains available

Benefits:

- faster OSS onboarding
- repeatable local setup
- local Postgres without manual installation
- captured Playwright/Chromium PDF dependencies
- easier cloud migration because the app runtime is a container image

Docker does not make SQLite safe as a shared database across multiple services. Shared SQLite remains rejected for cloud/SaaS.

---

## 9. Schema Direction

### `users`

Use UUID primary keys.

Required fields:

```sql
id UUID PRIMARY KEY
telegram_id BIGINT UNIQUE NULL
email TEXT UNIQUE NULL
is_blocked BOOLEAN NOT NULL DEFAULT FALSE
created_at TIMESTAMPTZ NOT NULL
updated_at TIMESTAMPTZ NOT NULL
deleted_at TIMESTAMPTZ NULL
```

Notes:

- `telegram_id` is an auth binding, not the primary key.
- nullable `email` keeps future web auth possible.
- `deleted_at` supports future deletion workflows.
- Deletion is soft-delete by default. Physical user deletion is an admin/data-retention operation, not an application flow in private beta.

### `jobs`

Use UUID primary keys and tenant ownership.

Required fields:

```sql
id UUID PRIMARY KEY
user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT
title TEXT NOT NULL
company TEXT NOT NULL
status TEXT NOT NULL
source_url TEXT NULL
application_url TEXT NULL
fit_summary TEXT NULL
package_folder TEXT NULL
created_at TIMESTAMPTZ NOT NULL
updated_at TIMESTAMPTZ NOT NULL
deleted_at TIMESTAMPTZ NULL
```

Recommended indexes:

```sql
CREATE INDEX jobs_user_created_idx ON jobs(user_id, created_at DESC)
WHERE deleted_at IS NULL;

CREATE INDEX jobs_user_status_idx ON jobs(user_id, status)
WHERE deleted_at IS NULL;
```

Duplicate URL handling:

- Do not add hard `UNIQUE (user_id, source_url)` unless duplicate applications should be impossible.
- Prefer soft duplicate detection first, because reapplying to the same URL may be legitimate.

### `pipeline_runs`

Ship in the first hosted migration.

Required fields:

```sql
id UUID PRIMARY KEY
user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT
job_id UUID NULL REFERENCES jobs(id) ON DELETE SET NULL
status TEXT NOT NULL CHECK (status IN (
    'queued',
    'running',
    'generated',
    'artifacts_persisted',
    'delivered',
    'failed'
))
status_reason TEXT NULL
source_url TEXT NULL
package_path TEXT NULL
model TEXT NULL
provider TEXT NULL
heartbeat_at TIMESTAMPTZ NULL
started_at TIMESTAMPTZ NOT NULL
finished_at TIMESTAMPTZ NULL
created_at TIMESTAMPTZ NOT NULL
updated_at TIMESTAMPTZ NOT NULL
```

Status values:

```text
queued
running
generated
artifacts_persisted
delivered
failed
```

Uses:

- run audit
- failed-run debugging
- daily rate limit counting
- active-run guard
- stale-run cleanup after crashes
- future retry/resume behavior

Recommended indexes:

```sql
CREATE INDEX pipeline_runs_user_started_idx
ON pipeline_runs(user_id, started_at DESC);

CREATE INDEX pipeline_runs_user_status_idx
ON pipeline_runs(user_id, status);

CREATE UNIQUE INDEX pipeline_runs_one_active_per_user_idx
ON pipeline_runs(user_id)
WHERE status IN ('queued', 'running');
```

Active-run guard:

- Before starting a new hosted run, check for a `queued` or `running` run for the user.
- Either reject with a friendly message or queue behind the active run.
- Initial private beta can reject; queueing can come later.
- Queueing later is a separate design decision, not a flag flip. It requires a worker/queue mechanism such as a queue table, Redis, or Postgres LISTEN/NOTIFY.

Stale-run cleanup:

- On hosted app startup, mark orphaned active runs as `failed` if `status IN ('queued', 'running')` and the latest of `heartbeat_at`, `started_at`, or `created_at` is older than 2x the expected max pipeline duration.
- Set `status_reason = 'orphaned_after_process_restart'`.
- This prevents a crashed process from permanently locking a user out through the active-run unique index.

### `artifacts`

Do not ship in the initial migration unless artifact versioning/querying is needed immediately.

Initial private beta:

- store local artifact path on `pipeline_runs.package_path`
- users already receive PDFs in Telegram
- artifact loss from volume failure is acceptable for private beta

Future:

- add `artifacts` table when object storage or artifact versioning becomes necessary
- store object keys/URLs, MIME type, size, checksum, and artifact role

---

## 10. Artifact Storage Decision

Private beta uses local filesystem storage.

Confirmed stance:

- Old generated artifacts may be lost if the local volume fails.
- This is acceptable for private beta because the generated PDFs are delivered to users through Telegram.
- Postgres backup restore does not restore local artifacts.
- The system must not claim durable artifact history until object storage exists.
- Private-beta onboarding should say that Telegram is the user's durable copy for generated PDFs until artifact storage is upgraded.

Implementation requirement:

- define an `ArtifactStore` interface early
- ship only `local` backend initially
- do not advertise `s3` or `gcs` configs until implemented

Future triggers for object storage:

- web dashboard runs as a separate service
- artifacts need durable history
- volume storage approaches provider limits
- data export/deletion requirements become stricter
- users need to redownload old packages reliably

Phase 1 to Phase 3 migration intent:

- No guaranteed migration exists from Phase 1 SQLite rows or local package paths into hosted Postgres.
- If the developer wants to preserve personal local history at Phase 3, build a one-time import script as a separate non-blocking task.
- Private beta launch must not depend on that import script.

---

## 11. Configuration

Hosted backend selection should be explicit and minimal.

Recommended:

```text
DATABASE_URL=postgres://...
APPLYCLING_ARTIFACT_BACKEND=local
```

Rules:

- If `DATABASE_URL` is present in hosted mode, Postgres is canonical.
- Do not use `APPLYCLING_DB_BACKEND` unless there is a concrete need for manual override.
- Notion config must not override Postgres.
- `APPLYCLING_ARTIFACT_BACKEND` defaults to `local`.
- Only document artifact backends that exist.

---

## 12. Phase Plan

### Phase 1 — Local + Telegram Validation

Goal: prove Telegram delivery.

Scope:

- use existing SQLite/local-file path
- run end-to-end Telegram smoke test with real job URL
- send progress messages
- send `resume.pdf` and `cover_letter.pdf`
- inspect worker logs and generated output

Out of scope:

- Postgres
- Alembic
- tenant isolation
- daily rate limits
- web dashboard
- object storage
- Notion

Exit criteria:

- a real phone can trigger `applycling telegram add <url>`
- PDFs arrive in Telegram
- run output exists locally
- failures are visible in logs or Telegram messages

### Phase 2 — Docker / Compose

Goal: make runtime reproducible.

Scope:

- Dockerfile
- docker-compose with app + Postgres
- env example
- Playwright/Chromium dependencies inside image
- README quickstart for Docker and non-Docker paths

Exit criteria:

- new user can run the app from GitHub with documented Docker setup
- local Postgres is reachable from the app container
- direct Python CLI still works outside Docker

### Phase 3 — SaaS Persistence

Goal: admit external users safely.

Scope:

- Postgres canonical store
- Alembic initial migration
- `users`, `jobs`, `pipeline_runs`
- UUID identities
- tenant-scoped store lifecycle
- active-run guard
- daily count-based rate limit
- user blocking
- transient Postgres reconnect/retry
- PII inventory documented
- restore-from-backup drill against staging
- tenant-isolation integration test
- local `ArtifactStore` backend
- stale-run startup cleanup
- private-beta onboarding note about artifact durability

Exit criteria:

- User A cannot read or mutate User B's data through store/API paths
- User cannot start multiple simultaneous hosted runs
- stale active runs are automatically failed after process restart/timeout
- user can be rate-limited or blocked
- failed run records include `status_reason`
- restore drill has been performed
- private-beta artifact durability limitations are documented

---

## 13. Implementation Notes

### Store Lifecycle

Hosted stores must be request/user scoped.

Do not create a process-global `PostgresStore` that silently carries the wrong user context.

Telegram handlers should construct user context from Telegram identity, then build user-scoped persistence dependencies.

Future FastAPI handlers should use request dependencies that resolve the authenticated user and create scoped stores for that user.

### Connection Handling

Use `psycopg` v3.

Do not hold a database connection open during the full 10-minute pipeline run.

Acceptable options:

- short-lived connections per operation
- small `psycopg_pool` pool

Required:

- retry once on transient `OperationalError` after reconnecting
- do not retry non-idempotent writes blindly unless the operation is transactionally safe

Retry safety by operation:

- `users` upsert with `ON CONFLICT DO NOTHING` is idempotent and safe to retry.
- `pipeline_runs` insert/update should be transactionally guarded by caller-supplied UUID ids and the active-run unique index.
- `jobs` insert is not blindly retry-safe unless the caller supplies the UUID and the transaction outcome is known, or a deduplication rule is applied intentionally.
- Telegram-facing error messages should truncate/sanitize long `status_reason` text before sending; keep full failure details in Postgres.

### Timestamp Maintenance

Use application-managed timestamps for initial implementation:

- set `created_at` and `updated_at` on insert
- update `updated_at` on every update
- use UTC timestamps

Postgres triggers may be introduced later if timestamp drift becomes a problem, but they are not required for private beta.

### Tenant Isolation Test

Before external users:

1. Create User A.
2. Create User B.
3. Create a job for User A.
4. From User B's scoped store, attempt to load/update User A's job.
5. Assert `TrackerError` / not found.

This test proves the tenant-isolation requirement.

### Rate Limiting

Initial private beta only needs simple daily count-based limits.

Use `pipeline_runs` as the counting source.

Do not build tier-based limits or billing UI before private beta unless product scope changes.

### PII Inventory

The system stores PII and sensitive application data:

- Telegram user id
- optional email if future auth lands
- resume content
- applicant profile
- compensation expectations
- work authorization
- sponsorship status
- job application history
- generated resumes/cover letters/briefs
- fit summaries and model outputs

Before external users, document:

- where this data is stored
- how deletion requests will be handled manually
- who has operational access
- backup retention assumptions

---

## 14. Cut Lines

If Phase 3 slips, keep:

- tenant isolation
- `pipeline_runs`
- simple daily rate limit
- user blocking
- active-run guard
- stale-run cleanup
- restore drill
- transient DB retry

Drop/defer:

- Notion sync
- artifact versioning
- `artifacts` table
- object storage
- tier-based limits
- billing UI
- web dashboard expansion
- pretty per-user job display numbers

Reasoning:

- retained items protect user data, operational visibility, and LLM cost exposure
- deferred items improve UX or durability but are not required for a small private beta

---

## 15. What Is Not Locked In

The following are intentionally deferred:

- object storage provider: S3-compatible storage vs Google Cloud Storage
- web dashboard scope/timeline
- pretty job display IDs
- exact daily rate-limit threshold
- Notion sync design
- artifact versioning model
- billing and plan tiers

---

## 16. Final Review Checklist

Before Phase 1:

- [ ] Telegram round-trip test command identified
- [ ] worker logs visible
- [ ] local output folder confirmed
- [ ] Telegram PDF size under platform limit

Before Phase 2:

- [ ] Dockerfile design agreed
- [ ] Compose services agreed
- [ ] `.env.example` updated
- [ ] direct Python CLI path preserved

Before Phase 3:

- [ ] Alembic initialized
- [ ] `users`, `jobs`, `pipeline_runs` migration written
- [ ] foreign-key `ON DELETE` behavior encoded in migration
- [ ] `pipeline_runs.status` CHECK constraint encoded in migration
- [ ] `psycopg` v3 dependency added
- [ ] request/user-scoped store design implemented
- [ ] active-run guard implemented
- [ ] stale-run startup cleanup implemented
- [ ] daily rate limit implemented
- [ ] user blocking implemented
- [ ] transient DB retry implemented
- [ ] timestamp maintenance convention implemented
- [ ] PII inventory documented
- [ ] restore-from-backup drill completed
- [ ] tenant-isolation integration test passing
- [ ] private-beta artifact durability limitation documented

---

## 17. Review History

This document was reviewed and refined through multiple back-and-forth passes between GPT-5.5, Claude Opus 4.7, and user input.

Key changes from those reviews:

- original SQLite + WAL recommendation was superseded for hosted SaaS
- PostgreSQL was selected as canonical hosted storage
- SQLite was retained as best-effort local/OSS fallback
- Notion was removed from the hosted critical path
- Docker/Compose was added early for reproducibility
- Phase 1 was scoped to Telegram validation, not durable architecture
- `users`, `jobs`, and `pipeline_runs` were locked into the first hosted migration
- UUID identities, tenant isolation, active-run guard, rate limiting, PII inventory, restore drill, and tenant-isolation tests were added as Phase 3 requirements
- private beta artifact loss was accepted if PDFs have already been delivered through Telegram

---

## 18. Final Review Stamp

**Final review date:** 2026-04-27  
**Reviewed by:** GPT-5.5 after Claude Opus 4.7 final review  
**Decision:** Stamped for implementation planning

The final Opus review found no architectural disagreement. Its remaining Phase 3 spec gaps have been incorporated into the canonical design:

- stale active-run cleanup
- removal of `cancelled` from the initial status set
- explicit foreign-key deletion behavior
- `pipeline_runs.status` CHECK constraint
- application-managed `updated_at` convention
- per-operation retry-safety notes
- Telegram truncation/sanitization note for long failure text
- explicit Phase 1 to Phase 3 migration stance
- private-beta artifact durability user-communication requirement
- queueing-later complexity note

No further clarification is needed before breaking the work down into tickets.

Next planning scope:

1. **Local Telegram validation**
2. **Tracking jobs with a database**
