# Working Memory — applycling

## Current State — Host Dogfooding Sprint

**Sprint:** Host Dogfooding (docs/planning/HOST_DOGFOODING_SPRINT.md)
**Date:** 2026-05-01
**Test suite:** 227 passed, 12 skipped
**Gates:** 20/20 — SPRINT COMPLETE

### All Gates Merged

| Gate | PRs | What |
|---|---|---|
| 1 | #26 | Deploy config (compose, Caddyfile, DEPLOY.md) |
| 2 | #28 | Active-run guard (pipeline_runs, atomic INSERT) |
| 3 | #27, #29 | Artifact docs, healthz, async submit |
| 4 | #30 | Basic Auth, fail-fast validators |
| 5 | #31 | /api/intake, Pydantic HttpUrl |
| 6 (I1 smoke) | - | Full smoke: Telegram → intake → generation → artifacts → UI |
| 7 (H1 docs) | #35 | Hermes forwarding template (env vars), SOUL.md |
| 7 (gate checklist) | #37, #38 | Sprint acceptance gate tracking (19/20 → 20/20) |
| 8 (docs fixes) | #36 | Deploy checklist fix (output_dir allowlist) |
| Phase 2 | #39, #40, #41 | Hosted Hermes: compose, docs, setup script |

### Phase 2 — Hosted Hermes (Deployed)

- Hermes installed on VPS via official install script (not Docker)
- Profile at `~/.hermes/profiles/applycling/` on VPS
- Reaches applycling at `http://127.0.0.1:8080/api/intake` (localhost port mapping)
- `scripts/setup_hosted_hermes.sh`: one-command setup after one-time env vars
- Setup reads shared secrets from `/opt/applycling/.env` (single source of truth)
- Model: `deepseek-chat` (DeepSeek) — routing only, ~$0.25/mo

### Full Path (Verified)

```
Telegram → hosted Hermes (VPS) → POST 127.0.0.1:8080/api/intake
  → applycling (Docker) → pipeline → Postgres + /opt/applycling/output/
```

### Open Issues

- `test_concurrent_inserts_only_one_succeeds` FK fix committed to main (973fd99)
- Server startup in Postgres mode requires all auth/secrets vars or fails fast
- Config output_dir bug: fixed + deploy checklist added (#36)
- hermes-agent has no public Docker image — future: containerize when available
- One-time setup pain: TELEGRAM_BOT_TOKEN + DEEPSEEK_API_KEY must be in /opt/applycling/.env
