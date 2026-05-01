# Working Memory — applycling

## Current State — Host Dogfooding Sprint

**Sprint:** Host Dogfooding (docs/planning/HOST_DOGFOODING_SPRINT.md)
**Date:** 2026-04-30
**Test suite:** 227 passed, 12 skipped
**Gates:** 19/20 verified — only Phase 2 (hosted Hermes) remains

### All Gates Merged

| Gate | PRs | What |
|---|---|---|
| 1 | #26 | Deploy config (compose, Caddyfile, DEPLOY.md) |
| 2 | #28 | Active-run guard (pipeline_runs, atomic INSERT) |
| 3 | #27, #29 | Artifact docs, healthz, async submit |
| 4 | #30 | Basic Auth, fail-fast validators |
| 5 | #31 | /api/intake, Pydantic HttpUrl |
| 6 (smoke) | - | Telegram → intake → generation, bind mount, 409 guard |
| 7 (docs) | #35, #37 | Hermes forwarding profile, sprint gate checklist |
| 8 (docs) | #36 | Deploy checklist fix (output_dir), smoke results |

### Gate 6 Smoke Results

- Telegram → local Hermes → intake → generation: 200 OK (job 3fc23920)
- Active-run guard: 409 on concurrent submit
- Bind mount survival: verified with TEST_SURVIVAL.txt
- Workbench UI: job board, status, artifacts — all verified
- Mobile UI: usable
- 19/20 acceptance gates checked off

### Phase 2 Prep (Ready for Deploy)

- `docker-compose.prod.yml`: hermes service added
- `docs/deploy/HOSTED_HERMES.md`: full setup guide
- Profile structure: `/opt/hermes-profile/profiles/applycling/`
- Intake URL: `http://applycling:8080/api/intake` (internal Docker network)
- Image: `hermes-agent:latest` (built from repo on VPS)

### Phase 2 Deploy Steps (to do on VPS)

1. Clone hermes-agent: `git clone https://github.com/nous/hermes-agent.git /opt/hermes-agent`
2. Build image: `cd /opt/hermes-agent && docker build -t hermes-agent:latest .`
3. Create profile: `mkdir -p /opt/hermes-profile/profiles/applycling/sessions`
4. Provision config.yaml, .env, SOUL.md from laptop
5. Start: `docker compose -f docker-compose.prod.yml up -d hermes`
6. Stop local: `launchctl bootout gui/$(id -u)/ai.hermes.gateway-applycling`

### Open Issues

- `test_concurrent_inserts_only_one_succeeds` FK fix committed to main (973fd99)
- Server startup in Postgres mode requires all auth/secrets vars or fails fast
- Config output_dir bug: VPS config.json had laptop path — fixed, deploy checklist added (#36)
