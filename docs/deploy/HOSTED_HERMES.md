# Hosted Hermes — Phase 2 Telegram Gateway

## Overview

Phase 2 moves the Hermes Telegram gateway from the local machine to the hosted
environment. Two services run on the same VPS:

```
┌─────────────────────────────────────────────────────────┐
│  Kamatera VPS                                            │
│                                                          │
│  ┌──────────┐  ┌───────────────┐  ┌──────────────────┐  │
│  │  Hermes  │  │  applycling   │  │  postgres:16      │  │
│  │  gateway │→│  :8080 (int)   │──│  :5432 (internal) │  │
│  │          │  │               │  │                    │  │
│  └──────────┘  └───────────────┘  └──────────────────┘  │
│       │                                                 │
│  Telegram Bot API                                       │
└─────────────────────────────────────────────────────────┘
```

Hermes polls Telegram, receives job URLs, and forwards them to the applycling
intake endpoint (`POST /api/intake`). It does NOT mount the artifact volume —
only the workbench serves and stores generated packages.

## Prerequisites

1. Hosted applycling is deployed (see `docs/deploy/DEPLOY.md`)
2. Phase 1 intake endpoint is operational (PR 6)
3. Telegram bot token is registered with BotFather

## Files

### Dockerfile.hermes

A minimal container that installs Hermes Agent and starts the gateway:

```dockerfile
FROM python:3.12-slim
RUN pip install hermes-agent
CMD ["hermes", "gateway", "start", "--profile", "applycling"]
```

### Hermes Profile (`/opt/applycling/hermes_profile/SOUL.md`)

The SOUL.md template reads ``$APPLYCLING_INTAKE_URL`` and
``$APPLYCLING_INTAKE_SECRET`` from environment variables — no manual
editing needed. Copy it directly from the repo:

```bash
cp docs/deploy/hermes_forwarding_template.md \
   /opt/applycling/hermes_profile/SOUL.md
```

Set the env vars in `/opt/applycling/.env` — see below.

### Env Vars (in `/opt/applycling/.env`)

Add these to the existing `.env` file:

```bash
# Hermes container env vars
APPLYCLING_INTAKE_URL=http://applycling:8080/api/intake
APPLYCLING_INTAKE_SECRET=<generated-secret>
TELEGRAM_BOT_TOKEN=<bot-token-from-botfather>
DEEPSEEK_API_KEY=<deepseek-api-key>
```

## Deployment

```bash
# 1. Create Hermes profile on host
mkdir -p /opt/applycling/hermes_profile

# 2. Copy SOUL.md template
cp docs/deploy/hermes_forwarding_template.md \
   /opt/applycling/hermes_profile/SOUL.md

# 3. Set env vars in /opt/applycling/.env (see Env Vars section above)

# 4. Build and start Hermes container
docker compose -f docker-compose.prod.yml up -d --build hermes
```

## Verification

1. Send a job URL to the Telegram bot
2. Hermes should forward it to `http://applycling:8080/api/intake`
3. Job should appear in the workbench at the public HTTPS URL
4. Package generation runs on the VPS

```bash
# Check Hermes logs
docker compose -f docker-compose.prod.yml logs -f hermes

# Check applycling logs (for intake endpoint)
docker compose -f docker-compose.prod.yml logs -f applycling
```

## Limitations

- **Hermes liveness is NOT covered by `/healthz`** — that endpoint only checks
  the applycling workbench. Monitor Hermes separately with `docker compose logs`.
- **Asymmetric restart safety:** restarting the Hermes container is safe (it only
  forwards URLs). Restarting applycling during an active generation kills the
  in-process background task — the job must be regenerated after the startup
  stale-run sweep marks it as failed.
- **Single VPS:** Both services share CPU and RAM (1 vCPU, 2 GB). Hermes uses
  minimal resources (~100 MB RAM).

## Rollback to Phase 1

To revert to local Hermes forwarding:

1. Stop the hosted Hermes: `docker compose -f docker-compose.prod.yml stop hermes`
2. Restart local Hermes on your laptop with Phase 1 forwarding config
3. Both modes use the same intake endpoint — no server-side changes needed
