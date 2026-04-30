# applycling — Host Dogfooding Sprint

**Status:** Phase 1 complete (15/20 gates verified). 5 pending: Phase 2 (hosted Hermes), workbench UI verification, mobile UI, desktop UI, failure visibility.

**Verification date:** 2026-04-30
**Date:** 2026-04-29
**Implementation plan:** `docs/planning/HOST_DOGFOODING_EXECUTION_PLAN.md`
**Review:** Multi-agent review completed (Claude Sonnet 4, Codex/GPT-5, anonymous review agent). See execution plan §10 for full review history.
**Baseline:** Local workbench + Postgres foundation is assumed merged. This sprint starts directly from that state.
**Supersedes active planning in:** `docs/planning/SPRINT_PERSONAL_USE_V2.md`  
**Builds on:** `docs/planning/LOCAL_WORKBENCH_SPRINT.md`, `docs/planning/DB_TECH_DESIGN.md`, `vision.md`, `memory/semantic.md`

This sprint moves applycling from a local workbench to a single-user hosted dogfood
deployment. The goal is to use applycling from Telegram, phone, and browser without
running the whole service locally, while avoiding the scope of a closed beta or
SaaS launch.

This is a bridge sprint: more realistic than localhost dogfooding, narrower than
private beta.

---

## Statement of the Ask

- **What problem this solves:** The local workbench makes job-search state visible, but the user still has to run the service locally. Hosted dogfooding validates the real intended loop: send a job URL through Telegram, generate a package in the hosted environment, check status from mobile, review artifacts/interview prep/questions on web, and continue applying without local server babysitting.
- **Expected outcome:** A single personal hosted deployment runs the workbench against Postgres, behind a simple auth gate, with durable-enough artifacts and a documented deploy/smoke path.
- **Hard constraints:** Single-user only. No signup, no billing, no public beta, no multi-user onboarding, no admin UI, no Notion sync, no generalized queue worker platform.
- **Baseline:** The local workbench and Postgres foundation are merged. Docker, Alembic, initial Postgres schema, explicit backend selection, and `PostgresStore` are available.

---

## Product Positioning

This sprint is **hosted dogfooding**, not SaaS.

The deployment may be cloud-hosted, but the product contract is still one known user:

- one owner
- one hosted Postgres database
- one workbench protected by simple auth
- one active package generation at a time
- artifacts stored on a persistent host volume or equivalent
- local SQLite mode remains available for development and OSS-style use
- hosted mode starts with a fresh Postgres database; local SQLite job history is not migrated
- hosted generation context still comes from private file-backed `data/` inputs unless `user_contexts` is explicitly pulled forward

The sprint should create useful prep for closed beta without pretending closed beta is
complete.

---

## Architecture Alignment

This sprint aligns with `vision.md`:

- The pipeline remains the public contract. Hosted workbench entry points call the same pipeline/service layer rather than forking generation.
- The runtime stays a thin orchestrator over fat markdown skills.
- Multi-source initiation remains the product shape: CLI, Telegram, and web are all callers of the same core capability. In this sprint, Telegram via Hermes, mobile UI, and desktop web are the highest-use dogfood paths, but other existing entry points should remain supported.
- Hosted persistence follows the documented phase: local SQLite/Notion fallback -> Docker/local Postgres -> hosted Postgres.

This sprint aligns with `DB_TECH_DESIGN.md` and the older personal-use sprint:

- Postgres is canonical for hosted mode.
- SQLite remains best-effort local fallback.
- Backend selection remains explicit: `APPLYCLING_DB_BACKEND=sqlite|postgres`.
- `DATABASE_URL` is only a Postgres connection detail; it must not implicitly select Postgres.
- Notion is not canonical in hosted mode.
- One active run per user is the intended hosted posture.
- Local artifact storage is acceptable for personal dogfood/private-beta validation if durability expectations are explicit.

This sprint intentionally does **not** satisfy the full closed-beta requirements:

- no external-user signup
- no multi-user UI
- no hosted `user_contexts` requirement unless pulled forward explicitly
- no full tenant-isolation acceptance gate
- no daily rate limit/blocking system unless naturally adjacent to active-run guard
- no formal backup/restore drill beyond documenting the host's current backup posture
- no custom Telegram polling/listener inside applycling; Hermes remains the hosted Telegram gateway

---

## Sprint Goals

| Goal | Status |
|---|---|
| Choose one hosting target and document deploy shape, cost ceiling, TLS, secrets, logs, and storage | Done |
| Run the workbench in a hosted environment behind simple auth | Done |
| Use hosted Postgres via explicit backend selection | Done |
| Run Alembic migrations in the hosted environment | Done |
| Provision required single-user `data/` files without baking private data into the image | Done |
| Persist generated artifacts across deploy/restart | Done |
| Add health/log visibility good enough for host restart/debugging | Done |
| Enforce one active generation run for the single dogfood user using `pipeline_runs` | Done |
| Phase 1: preserve existing local Hermes flow while forwarding generation to hosted applycling | Done |
| Phase 2: move Hermes itself into the hosted environment | Pending |
| Complete a real hosted smoke test across the highest-use paths: Telegram intake, mobile status check, and web review | Partial — Telegram done, mobile/web pending |
| Document the delta from hosted dogfood to closed beta | Done |

---

## Non-Goals

- SaaS/private-beta launch
- public registration or invite flow
- password reset/account lifecycle
- billing
- admin panel
- multi-tenant UI
- generalized queue worker fleet
- object storage unless the host's disk model makes it mandatory
- custom Telegram polling/listener inside applycling
- Notion sync
- MCP server
- user skill marketplace
- migration/sync from local SQLite to hosted Postgres

---

## Deployment Target Guidance

Use one target for implementation. Do not support multiple hosts in this sprint.

Chosen target for this sprint:

- **Railway** for first dogfood, unless a concrete feasibility blocker appears or actual monthly cost is likely to exceed the dogfood ceiling.

Acceptable alternatives:

- **Cheap VPS + Docker Compose:** lowest runtime complexity if comfortable with server ops; app, Postgres, and persistent disk can live on one box.
- **GCP Cloud Run + Cloud SQL:** production-shaped but higher setup complexity; not recommended for this sprint because long-running generation, request timeouts, and cold starts are a poor fit for personal dogfood.

Cost guidance for personal dogfood: target **under $25/month** for app runtime,
Postgres, and artifact storage, but do not force a mid-sprint host swap only because
Railway lands slightly above that. Treat sustained cost above roughly **$40/month**
as the trigger to revisit the host after dogfood validation.

The chosen target must explicitly document:

- TLS path: built-in platform HTTPS, Caddy/Traefik, or Cloudflare fronting
- secrets storage: platform secrets, server `.env`, or equivalent
- key rotation posture: what to rotate if a deployment secret leaks
- Hermes profile secrets, Telegram bot token, and Hermes routing LLM key (DeepSeek per current profile), separate from UI auth credentials
- persistent artifact path
- private single-user `data/` file path/provisioning method
- log access path
- restart/redeploy process

---

## Scope Order

```text
Phase 1: Host the single-user workbench
  ├─ Ticket B: Deployment target + runtime contract
  ├─ Ticket D: Hosted Postgres, data provisioning, and health
  └─ Ticket C: Simple personal auth gate

Phase 2: Make hosted generation safe enough for dogfood
  ├─ Ticket E: Durable artifact path
  └─ Ticket G: pipeline_runs active-run guard

Phase 3: Preserve real intake in two steps
  ├─ Ticket H1: Local Hermes forwarding to hosted applycling
  ├─ Ticket I1: Phase 1 hosted smoke
  ├─ Ticket H2: Hosted Hermes Telegram intake
  └─ Ticket I2: Phase 2 hosted smoke and closed-beta delta
```

---

## Acceptance Gate

The sprint is done when:

- [x] Local SQLite mode still works.
- [x] Local Postgres mode works with `APPLYCLING_DB_BACKEND=postgres`.
- [x] The hosted workbench is reachable over HTTPS.
- [x] The hosted workbench is protected by a personal auth gate.
- [x] Hosted env uses `APPLYCLING_DB_BACKEND=postgres` and `DATABASE_URL`.
- [x] Alembic migrations can be run repeatably against hosted Postgres.
- [x] Required single-user `data/` files are provisioned privately and are not baked into the container image.
- [x] A `/healthz` or equivalent liveness check exists.
- [x] A generated package survives app restart/redeploy.
- [x] Submitting/regenerating a job does not require holding an HTTP request open for the full pipeline duration.
- [x] A second generation attempt is rejected or clearly blocked while one run is active, then allowed again after a generated/failed terminal state.
- [x] Phase 1: a real job URL sent through local Hermes completes generation in the hosted environment.
- [ ] Phase 2 target: Telegram intake works without a local laptop/Hermes process. If Phase 2 slips, Phase 1 can still close as hosted-generation dogfood and Phase 2 becomes the immediate follow-up.
- [ ] Mobile UI can check job status.
- [ ] Desktop web UI can review generated artifacts and prep materials.
- [x] Existing CLI/local entry points remain supported unless explicitly documented otherwise.
- [ ] The workbench shows the resulting job, status, and artifacts.
- [x] No custom Telegram polling/listener is added to applycling.
- [ ] Failure state is visible from the workbench/logs without guessing.
- [x] The remaining closed-beta gaps are documented.

---

## Ticket B — Deployment Target + Runtime Contract

**Estimate:** 1-1.5 days  
**Depends on:** merged baseline  
**Files likely touched:** deployment docs, `.env.example` if new env vars are added

### Goal

Choose one host and define the exact hosted runtime shape.

### Work

1. Use Railway as the implementation target unless a concrete feasibility/cost blocker is found.
2. Document:
   - app start command
   - migration command
   - required env vars
   - TLS path
   - secrets storage and rotation posture
   - Hermes profile secrets, Telegram bot token, and Hermes routing LLM key
   - persistent artifact path
   - private `data/` file path/provisioning method
   - log access path
   - restart/redeploy process
   - expected monthly cost and whether it fits within the dogfood cost guidance
3. Ensure hosted mode explicitly sets:
   - `APPLYCLING_DB_BACKEND=postgres`
   - `DATABASE_URL`
   - model provider keys
   - artifact/output directory path if needed
4. Preserve direct local Python usage and SQLite default.

### Acceptance

- There is one documented deployment path.
- A future agent does not need to choose a cloud platform before implementing.
- The plan names the TLS, secrets, logs, artifact, private data, and cost posture for the chosen host.

---

## Ticket D — Hosted Postgres, Data Provisioning, and Health

**Estimate:** 0.5-1 day  
**Depends on:** Ticket B  
**Files likely touched:** docs/deploy notes, maybe Docker/start scripts, `applycling/ui/`

### Goal

Make schema setup, single-user generation context, and host health checks repeatable.

### Work

1. Run `alembic upgrade head` against hosted Postgres.
2. Confirm migration is idempotent when re-run at head.
3. Confirm `PostgresStore` can create/load/update jobs in hosted mode.
4. Document whether migrations are manual for dogfood or run during deploy.
5. Provision required private `data/` files through a mounted host/platform volume populated manually from the laptop on first deploy:
   - config/model selection
   - profile
   - resume
   - stories
   - applicant profile
6. Document the refresh path: manually re-upload when profile/resume/stories/applicant profile changes.
7. Note that in-repo `applycling/skills/*` ships with the image; only private `data/` files need out-of-band provisioning.
8. Do not bake private user data or API keys into the image.
9. Add a trivial `/healthz` endpoint or equivalent host liveness command. Keep it scoped to returning 200 when the app is alive and the database is reachable.
10. Use the host's native log viewer for dogfood logs. Do not add log dashboards, log shipping, or alerting in this sprint.

### Acceptance

- Hosted database schema can be created from source-controlled migrations.
- No manual SQL edits are required.
- Hosted generation has access to the same single-user context as local generation.
- Health/liveness can be checked by the host or manually during deploy.
- Logs are accessible through the host's native log viewer.

---

## Ticket C — Simple Personal Auth Gate

**Estimate:** 0.5-1 day  
**Depends on:** Tickets B-D  
**Files likely touched:** `applycling/ui/`, deployment config, docs

### Goal

Make the hosted workbench safe to expose on the internet for one personal user.

### Work

Implement one simple gate:

- platform/reverse-proxy auth if the host offers it, or
- app-level basic auth middleware with env vars

If app-level auth is used, prefer explicit env vars:

```bash
APPLYCLING_UI_AUTH_USER=...
APPLYCLING_UI_AUTH_PASSWORD=...
```

Rules:

- Local `127.0.0.1` development should remain easy.
- Hosted mode must not expose the workbench without auth.
- Secrets must come from env, not committed files.
- Do not build a login UI.

### Acceptance

- Hosted workbench requires authentication.
- Local development remains low-friction.

---

## Ticket E — Durable Artifact Path

**Estimate:** 0.5-1 day  
**Depends on:** Ticket B  
**Files likely touched:** deployment config, docs, possibly artifact path config

### Goal

Ensure generated packages survive app restart/redeploy.

### Work

1. Identify current package output path in hosted mode.
2. Ensure it is backed by a persistent volume, mounted disk, or equivalent.
3. Confirm the UI can serve artifacts from that path.
4. Document durability limits.

Object storage is optional and should be pulled in only if the chosen host cannot
provide durable enough filesystem storage.

### Acceptance

- A generated `resume.pdf` and `cover_letter.pdf` survive restart/redeploy.
- The limitation is documented: this is personal dogfood durability, not final SaaS storage.

---

## Ticket G — pipeline_runs Active-Run Guard

**Estimate:** 1 day  
**Depends on:** Ticket D  
**Files likely touched:** `applycling/jobs_service.py`, `applycling/tracker/postgres_store.py`, tests

### Goal

Prevent accidental overlapping hosted generations for the dogfood user.

### Work

1. Use `pipeline_runs` as the source of truth for active hosted generation.
2. Before starting generation, check whether a `running` run exists for the dogfood user.
3. If one is active, reject the new run with a clear UI message or status reason.
4. Create/update run records for generated and failed terminal states.
5. Ensure failed/completed runs release the guard.
6. Ensure regenerate for the same job is allowed after a failed/generated terminal state.
7. Add a startup stale-run sweep: mark old `running` rows as `failed` with a clear `status_reason` so a crash does not block future dogfood runs forever.
8. Keep this scoped to active-run safety only: no queueing, cancel, retry orchestration, pause/resume, or worker pool.
9. Add tests for the guard and stale-run release path.

### Acceptance

- Two simultaneous hosted generations cannot start for the same dogfood user.
- A failed run does not permanently block future regenerate/submit attempts.
- A stale `running` row from a crashed process does not permanently block future runs.
- The user sees a clear explanation.

---

## Ticket H1 — Local Hermes Forwarding to Hosted applycling

**Estimate:** 0.5-1 day  
**Depends on:** Tickets B-G  
**Files likely touched:** deployment docs, Hermes profile/config notes, protected intake endpoint, tests if endpoint logic is added

### Goal

Preserve the already-working local Hermes Telegram interface while moving generation, persistence, and artifacts to the hosted environment.

### Chosen Phase 1 Topology

Use the existing local Hermes profile as the Telegram gateway, but make it forward
job URLs to hosted applycling:

```text
Telegram -> local Hermes -> protected workbench HTTP intake endpoint -> jobs_service/pipeline -> hosted Postgres + artifact volume
```

This is a bridge step. Telegram intake still requires the local Hermes machine to
be running, but package generation and job state move to the hosted environment.

### Work

1. Keep Hermes as the Telegram gateway. Do not add custom Telegram polling/listening code to applycling.
2. Create a protected hosted HTTP intake endpoint on the workbench service for Hermes to submit job URLs.
3. Protect the intake endpoint with a shared secret distinct from UI auth credentials.
4. Update the local Hermes applycling profile/wrapper so it forwards job URLs to hosted intake instead of running local generation.
5. Ensure the local Hermes wrapper runs no generation logic.
6. Ensure a Telegram job URL creates/runs a job against hosted Postgres.
7. Ensure active-run guard rejection produces a Telegram-visible message rather than silent failure.
8. Ensure the hosted workbench shows the same job and artifacts.
9. Preserve useful Telegram progress/failure/completion signals where the existing flow supports them.
10. Document the local-Hermes-forwarding setup, hosted intake secret, and rollback path to local generation.

### Acceptance

- Sending a job URL through Telegram starts hosted generation.
- Hosted Postgres records the job/run.
- Local Hermes forwards to hosted intake and does not run generation locally.
- Workbench mobile/web views show the Telegram-created job.
- No bespoke Telegram polling code is added to applycling.
- Hermes remains the only Telegram gateway/interface layer.

---

## Ticket I1 — Phase 1 Hosted Smoke

**Estimate:** 0.5 day  
**Depends on:** Ticket H1  
**Files likely touched:** README/deploy docs, sprint doc

### Goal

Validate the bridge loop before moving Hermes itself to the hosted environment.

### Work

1. Send a real job URL through Telegram to local Hermes.
2. Verify:
   - local Hermes forwards the URL to hosted intake
   - job row exists in hosted Postgres
   - Telegram-created job appears in the workbench
   - status transitions are visible
   - hosted intake returns promptly and does not hold the full pipeline HTTP request open
   - existing UI is usable on a mobile viewport for status checks without a mobile redesign
   - desktop web UI supports artifact review and prep/interview-question workflow entry points that already exist
   - artifacts are generated
   - artifacts are viewable/downloadable from the workbench
   - Telegram progress/failure/completion signal is acceptable for dogfood
   - failure details are visible if something breaks

### Acceptance

- Phase 1 dogfood works with local Hermes forwarding and hosted generation/state.
- The hosted intake endpoint is ready for hosted Hermes in Phase 2.

---

## Ticket H2 — Hosted Hermes Telegram Intake

**Estimate:** 1-1.5 days  
**Depends on:** Ticket I1  
**Files likely touched:** deployment docs, Hermes profile/config notes, process/startup config

### Goal

Move the Hermes Telegram gateway from the local machine into the hosted environment.

### Chosen Phase 2 Topology

Use **two hosted services in the same Railway project/deployment group**:

- **Workbench service:** FastAPI workbench, generation execution, hosted Postgres access, artifact volume, protected web UI.
- **Hermes service:** hosted Hermes profile/gateway process that owns Telegram polling/routing and forwards job URLs to the workbench.

Invocation path:

```text
Telegram -> hosted Hermes service -> protected workbench HTTP intake endpoint -> jobs_service/pipeline -> hosted Postgres + artifact volume
```

This keeps Hermes responsible for Telegram and keeps generated artifacts in the same
service/volume the workbench serves. Do not merge Hermes into the workbench process
for this sprint unless Railway makes the two-service topology infeasible.

Railway volume ownership: the artifact volume belongs to the workbench service.
Hermes does not need the artifact volume because it only forwards URLs to the
protected intake endpoint.

### Work

1. Keep Hermes as the Telegram gateway. Do not add custom Telegram polling/listening code to applycling.
2. Run the applycling Hermes profile/process as a hosted service in the same Railway project/deployment group as the workbench.
3. Configure hosted Hermes to call the protected intake endpoint created in H1.
4. Ensure hosted Hermes uses environment-managed secrets/profile config and does not bake bot tokens, DeepSeek/Hermes routing keys, or provider keys into the image.
5. Treat `scripts/setup_hermes_telegram.sh` and the local `applycling-hermes` wrapper as implementation references, not as-is hosted startup commands, unless they are made host-path-safe.
6. Ensure a Telegram job URL creates/runs a job against hosted Postgres without the local Hermes process running.
7. Ensure active-run guard rejection produces a Telegram-visible message rather than silent failure.
8. Ensure the hosted workbench shows the same job and artifacts.
9. Preserve useful Telegram progress/failure/completion signals where the existing flow supports them.
10. Document hosted Hermes startup, restart, logs, profile path, secrets, and failure recovery.

### Acceptance

- Sending a job URL through Telegram starts hosted generation.
- Hosted Postgres records the job/run.
- Telegram intake works without the local laptop/Hermes process running.
- Hosted Hermes runs as its own hosted service/process in the deployment group.
- Hermes invokes the workbench through a protected HTTP intake endpoint.
- The intake endpoint uses a secret distinct from UI auth credentials.
- Active-run guard rejections are visible in Telegram.
- Workbench mobile/web views show the Telegram-created job.
- No bespoke Telegram polling code is added to applycling.
- Hermes remains the only Telegram gateway/interface layer.

---

## Ticket I2 — Phase 2 Hosted Telegram/Mobile/Web Smoke, Docs, and Closed-Beta Delta

**Estimate:** 0.5-1 day  
**Depends on:** Ticket H2  
**Files likely touched:** README/deploy docs, sprint doc

### Goal

Prove the real hosted dogfood loop across Telegram intake, mobile status checks, and web review/prep.

### Work

1. Stop or ignore the local Hermes process.
2. Send a real job URL through Telegram to hosted Hermes.
3. Verify:
   - job row exists in hosted Postgres
   - Telegram-created job appears in the workbench
   - status transitions are visible
   - existing UI is usable on a mobile viewport for status checks without a mobile redesign
   - desktop web UI supports artifact review and prep/interview-question workflow entry points that already exist
   - submit/regenerate returns promptly and does not hold the full pipeline HTTP request open
   - artifacts are generated
   - artifacts are viewable/downloadable from the workbench
   - Telegram progress/failure/completion signal is acceptable for dogfood
   - hosted Hermes logs are accessible through the host's native log viewer
   - restarting/redeploying only the hosted Hermes service does not break the workbench and does not leave a permanently blocked active run
   - restart/redeploy does not lose the package
   - failure details are visible if something breaks
4. Add a short hosted dogfood runbook.
5. Add a closed-beta delta section.
6. Document dogfood limitation: `/healthz` covers the workbench app/database, not Hermes polling liveness. If hosted Hermes stops polling, use the host's native service/log view to diagnose.

### Acceptance

- Hosted dogfood smoke passes across Telegram intake, mobile status check, and desktop web review.
- The next sprint boundary is clear.

---

## Closed-Beta Delta

After this sprint, the remaining work before external closed beta should include:

- `user_contexts` table and hosted profile/resume/stories/applicant profile import path
- request-scoped user identity rather than a single local default user
- tenant isolation tests: User A cannot read/update User B jobs
- broader `pipeline_runs` operational controls if this sprint only implements the active-run guard
- stale-run cleanup
- daily rate limit and `users.is_blocked`
- transient Postgres retry behavior
- PII inventory and deletion posture
- backup/restore drill
- beta onboarding copy that explains artifact durability
- decision on object storage vs persistent volume for beta
- hosted Telegram intake hardening beyond the personal Hermes gateway path, if needed for closed beta

---

## Resolved Planning Decisions

1. **Host recommendation:** Railway first. Target under $25/month, but do not swap hosts mid-sprint unless costs are likely to stay above roughly $40/month.
2. **Auth:** Use platform/reverse-proxy auth if available; otherwise app-level basic auth middleware. Do not build a login UI.
3. **Dogfood usage:** The highest-use paths are Telegram via Hermes for generation, mobile UI for status checks, and desktop web for review, interview prep, questions, and actual application preparation. Other existing entry points should continue to work.
4. **Active-run guard:** Use `pipeline_runs` because the merged Postgres schema includes it.
5. **Artifact durability:** Persistent volume is enough for dogfood. Object storage belongs to closed-beta delta unless the chosen host requires it.
6. **Telegram gateway:** Preserve Hermes. Do not build custom Telegram polling inside applycling.
7. **Hermes migration path:** Phase 1 uses local Hermes forwarding to hosted applycling. Phase 2 moves Hermes into the hosted environment.
8. **Hermes invocation path:** Both phases use the same protected workbench HTTP intake endpoint. Hermes does not run generation locally, and applycling does not implement Telegram polling.

---

## Planning Decisions (Post-Review)

Decisions made during multi-agent review of the execution plan. Supersedes #1 (host recommendation) above.

1. **Hosting target:** Kamatera VPS (1 vCPU / 2 GB / 20 GB, $6/mo flat) + Docker Compose + Caddy TLS. Railway Hobby was $5/mo subscription but resources billed on top (est. $10-25/mo variable). Kamatera won on predictable cost. Same Docker images are trivially portable to Railway or any other host in the future.
2. **Compose separation:** `docker-compose.yml` stays local dev (unchanged). `docker-compose.prod.yml` adds Caddy, hosted env vars, and bind mounts.
3. **PR ordering:** PR5 (active-run guard) merges before PR2 (async refactor). Async fire-and-forget is unsafe without the guard.
4. **Guard mechanism:** PostgreSQL atomic INSERT ON CONFLICT with partial unique index on `(user_id) WHERE status = 'running'`. DB-enforced, no check-then-create window. SQLite/local mode is no-op.
5. **Startup sweep:** Unconditional (all `running` → `failed`) at app startup via FastAPI startup event. Periodic stale-check via heartbeat_at + 120-min timeout.
6. **Async model:** `asyncio.create_task(asyncio.to_thread(...))` with error-surfacing wrapper + `add_done_callback`. In-process, no worker queue. CLI retains sync+steering mode.
7. **Auth:** App-level Basic Auth (no platform auth available on VPS). Local dev via `APPLYCLING_NO_AUTH=true`. Only `/healthz` and `/api/intake` exempt.
8. **UI:** 10-second meta-refresh on job detail while generating. Sync pre-check on submit (rejects before creating job — no dead rows).
9. **Artifacts:** Bind-mounted `/opt/applycling/output/` → `/app/output`. Root-owned on host (Dockerfile has no USER directive).
10. **Migrations:** Manual one-off `alembic upgrade head` before app start during deploy.

---
