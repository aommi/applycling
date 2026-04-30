# Working Memory — applycling

## Current State — Host Dogfooding Sprint

**Sprint:** Host Dogfooding (docs/planning/HOST_DOGFOODING_SPRINT.md)
**Date:** 2026-04-30
**Test suite:** 227 passed, 12 skipped

### Merged (Gates 1-5, verified locally)

| Gate | PRs | What | Verified |
|---|---|---|---|
| 1 | #26 | Deploy config (compose, Caddyfile, DEPLOY.md) | Compose YAML valid, services listed |
| 2 | #28 | Active-run guard (pipeline_runs, atomic INSERT) | Migration, partial index, concurrent insert test, guard block |
| 3 | #27, #29 | Artifact docs, healthz, async submit | Healthz 200, submit form, guard rejection 409 |
| 4 | #30 | Basic Auth, fail-fast validators | 401/200/exempt/bypass, NO_AUTH blocked in Postgres |
| 5 | #31 | /api/intake, Pydantic HttpUrl | 401/422/200/409, per-request secret |

### Verified (Gate 6 — I1 Smoke)

| What | Result |
|---|---|
| Telegram → local Hermes → hosted intake → generation | 200 OK, job created (3fc23920) |
| Active-run guard in hosted mode | 409 on concurrent submit |
| Bind mount artifact survival | TEST_SURVIVAL.txt survived restart |
| Generated artifacts (17 files) | resume.pdf, cover_letter.pdf, etc. |
| Hermes SOUL.md uses env vars for forwarding | POSTs to $APPLYCLING_INTAKE_URL |
| Openclaw bootout to give Hermes the bot | launchctl bootout ai.openclaw.gateway |

### Pending

| Gate | PRs | What |
|---|---|---|
| 7 | #32 | Merge hosted Hermes profile docs + forwarding template |
| 8 | #33 | Merge docs fixes, VPS deploy checklist, runbook |

### Open Issues

- `test_concurrent_inserts_only_one_succeeds` FK fix committed to main (973fd99)
- Server startup in Postgres mode requires all auth/secrets vars or fails fast
- `register_startup_sweep()` captures store at import time — needs DATABASE_URL even to import in Postgres mode

### Bugs Found (Gate 6 Smoke)

- **Config output_dir:** VPS `config.json` had laptop path `/Users/amirali/Documents/ApplyCling-Output` instead of `/app/output`. Fixed manually on VPS. Need deploy checklist item in DEPLOY.md.

## 2026-04-29/30 — Hermes Forwarding Gateway Setup

- Hermes applycling profile at `~/.hermes/profiles/applycling/`
- SOUL.md: forwarding agent POSTs job URLs to `$APPLYCLING_INTAKE_URL`
- Env vars in profile `.env` (NOT global `~/.hermes/.env` — profiles have independent dotenv)
- Gateway running via launchd (`ai.hermes.gateway-applycling.plist`, KeepAlive)
- Intake endpoint verified: POST to `app.applycling.com/api/intake` → 200 OK
- End-to-end: Telegram URL → Hermes → intake → generation (job 3fc23920)
- Profile knowledge saved to Hermes memory and applycling semantic.md
