# Hermes Forwarding — Phase 1 Bridge

## Overview

Phase 1 keeps the local Hermes Telegram gateway but forwards job URLs to the
hosted applycling workbench. The local machine still needs to be running for
Telegram intake, but package generation and job state move to the hosted
environment.

```
Telegram → local Hermes → POST /api/intake → hosted applycling → Postgres + artifacts
```

Phase 2 moves Hermes itself to the hosted environment (see `HOSTED_HERMES.md`).

## Prerequisites

1. Hosted applycling is deployed and reachable (see `docs/deploy/DEPLOY.md`)
2. `APPLYCLING_INTAKE_SECRET` is set on the server in `/opt/applycling/.env`
3. Local Hermes Telegram profile is set up (see `scripts/setup_hermes_telegram.sh`)

## Setup

### 1. Get the intake secret

```bash
# From the VPS
cat /opt/applycling/.env | grep APPLYCLING_INTAKE_SECRET
```

### 2. Update local Hermes SOUL.md

Copy the template from `docs/deploy/hermes_forwarding_template.md` to your local
Hermes profile:

```bash
cp docs/deploy/hermes_forwarding_template.md ~/.hermes/profiles/applycling/SOUL.md
```

Set the required environment variables in `~/.hermes/.env` (local Hermes) or
`/opt/applycling/.env` (hosted Hermes container):

```bash
APPLYCLING_INTAKE_URL=https://applycling.yourdomain.com/api/intake
APPLYCLING_INTAKE_SECRET=<value from VPS /opt/applycling/.env>
```

Verify the env vars are set before restarting:

```bash
grep -E 'APPLYCLING_(INTAKE_URL|INTAKE_SECRET)' ~/.hermes/.env
```

### 3. Restart Hermes

```bash
# Stop any running Hermes gateway
pkill -f "hermes gateway"

# Restart
applycling-hermes gateway install
```

## Verification

1. Send a job URL to your Telegram bot
2. Local Hermes should forward it to the hosted intake endpoint
3. The job should appear in the hosted workbench UI at `https://applycling.yourdomain.com`
4. Package generation runs on the VPS, not locally

## Rollback to Local Generation

To revert to local generation:

1. Restore the original SOUL.md that runs `python -m applycling.cli telegram _run`
2. Restart Hermes

```bash
# The original SOUL.md is at (if you backed it up):
cp ~/.hermes/profiles/applycling/SOUL.md.backup ~/.hermes/profiles/applycling/SOUL.md

# Or recreate from the setup script:
scripts/setup_hermes_telegram.sh
```

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| "Invalid intake secret" (401) | SOUL.md has wrong secret | Check `INTAKE_SECRET` in SOUL.md matches `/opt/applycling/.env` |
| "Another generation is already running" (409) | Active run in progress | Wait for current run to complete, then retry |
| Connection refused | applycling not running on VPS | `docker compose -f docker-compose.prod.yml ps` |
| Hermes can't reach VPS | DNS or firewall | Verify `curl https://applycling.yourdomain.com/healthz` works from local machine |
