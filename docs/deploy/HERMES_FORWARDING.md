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
2. `APPLYCLING_INTAKE_SECRET` and `APPLYCLING_INTAKE_URL` are set on the VPS
3. Local Hermes Telegram profile is set up (see `scripts/setup_hermes_telegram.sh`)

## Setup

### 1. Set environment variables

Add the intake URL and secret to the applycling profile's `.env`:

```bash
echo "APPLYCLING_INTAKE_URL=https://app.applycling.com/api/intake" >> ~/.hermes/profiles/applycling/.env
echo "APPLYCLING_INTAKE_SECRET=<secret from /opt/applycling/.env>" >> ~/.hermes/profiles/applycling/.env
```

Important: the applycling profile has its own `.env` at
`~/.hermes/profiles/applycling/.env`. Do NOT use the global `~/.hermes/.env` —
the profile gateway only reads from the profile directory.

### 2. Install the forwarding SOUL.md

Copy the template to the profile directory:

```bash
cp docs/deploy/hermes_forwarding_template.md ~/.hermes/profiles/applycling/SOUL.md
```

The template references `$APPLYCLING_INTAKE_URL` and `$APPLYCLING_INTAKE_SECRET`
as environment variables — no manual editing needed. Set the values in step 1.

### 3. Restart Hermes

If the applycling Hermes gateway is already running, restart it to pick up the
new SOUL.md and env vars:

```bash
# If using launchd
launchctl bootout gui/$(id -u)/ai.hermes.gateway-applycling
sleep 1
launchctl bootstrap gui/$(id -u)/ai.hermes.gateway-applycling
```

Or reinstall from scratch:

```bash
applycling-hermes gateway install --force
```

## Verification

1. Send a job URL to your Telegram bot
2. Local Hermes should forward it to the hosted intake endpoint
3. The job should appear in the hosted workbench UI
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
| "Invalid intake secret" (401) | Wrong secret in profile .env | Check `APPLYCLING_INTAKE_SECRET` in `~/.hermes/profiles/applycling/.env` |
| "Another generation is already running" (409) | Active run in progress | Wait for current run to complete, then retry |
| Connection refused | applycling not running on VPS | `docker compose -f docker-compose.prod.yml ps` |
| Hermes can't reach VPS | DNS or firewall | Verify `curl https://app.applycling.com/healthz` works from local machine |
| Gateway not receiving messages | Another gateway owns the bot token | Check for competing processes: `pgrep -fl openclaw` |
