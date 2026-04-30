# Working Memory — applycling

## Current State — Host Dogfooding Sprint

**Sprint:** Host Dogfooding (docs/planning/HOST_DOGFOODING_SPRINT.md)
**Date:** 2026-04-29
**Test suite:** 227 passed, 12 skipped

### Merged (Gates 1-5, verified locally)

| Gate | PRs | What | Verified |
|---|---|---|---|
| 1 | #26 | Deploy config (compose, Caddyfile, DEPLOY.md) | Compose YAML valid, services listed |
| 2 | #28 | Active-run guard (pipeline_runs, atomic INSERT) | Migration, partial index, concurrent insert test, guard block |
| 3 | #27, #29 | Artifact docs, healthz, async submit | Healthz 200, submit form, guard rejection 409 |
| 4 | #30 | Basic Auth, fail-fast validators | 401/200/exempt/bypass, NO_AUTH blocked in Postgres |
| 5 | #31 | /api/intake, Pydantic HttpUrl | 401/422/200/409, per-request secret |

### Pending (Gates 6-8, need VPS)

| Gate | PRs | What |
|---|---|---|
| 6 | I1 smoke | Deploy to VPS, walk smoke checklist, real Telegram URL |
| 7 | #32 | Merge hosted Hermes, verify container + profile |
| 8 | #33 | Merge docs, verify runbook commands on VPS |

### Open Issues

- `test_concurrent_inserts_only_one_succeeds` FK fix committed to main (973fd99)
- Server startup in Postgres mode requires all auth/secrets vars or fails fast
- `register_startup_sweep()` captures store at import time — needs DATABASE_URL even to import in Postgres mode
