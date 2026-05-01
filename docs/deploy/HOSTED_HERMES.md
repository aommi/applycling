# Hosted Hermes — Phase 2

## Overview

Phase 2 moves the Hermes Telegram gateway from the local machine into the hosted
environment. After this, Telegram intake works without the local laptop running.

Hermes runs directly on the VPS host (not in Docker) via the official install
script. It reaches applycling at `http://127.0.0.1:8080` through a localhost-only
port mapping in docker-compose.prod.yml.

```
Telegram → hosted Hermes → POST http://127.0.0.1:8080/api/intake → pipeline → Postgres + artifacts
```

## Prerequisites

- Phase 1 (local Hermes forwarding) is verified and working
- VPS has Docker and git installed
- `applycling` port 8080 is exposed on localhost (in docker-compose.prod.yml since PR #39)

## Setup

### 0. One-time: add Hermes secrets to applycling env

On your laptop, get the values:

```bash
grep TELEGRAM_BOT_TOKEN ~/.hermes/profiles/applycling/.env
grep DEEPSEEK_API_KEY ~/.hermes/.env
```

On the VPS, add them to `/opt/applycling/.env`:

```bash
echo 'TELEGRAM_BOT_TOKEN=<paste>' >> /opt/applycling/.env
echo 'TELEGRAM_ALLOWED_USERS=26605267' >> /opt/applycling/.env
echo 'DEEPSEEK_API_KEY=<paste>' >> /opt/applycling/.env
```

This is one-time. The setup script reads all secrets from `/opt/applycling/.env`.

### 1. Install Hermes on the VPS

```bash
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash
```

### 2. Run the setup script

```bash
cd /opt/applycling/app && git pull
bash scripts/setup_hosted_hermes.sh
```

This reads shared secrets from `/opt/applycling/.env` (Telegram bot token, DeepSeek
key, intake secret), creates the Hermes profile, and installs the gateway service.

### 3. Stop local Hermes

On your laptop:

```bash
launchctl bootout gui/$(id -u)/ai.hermes.gateway-applycling
```

### 4. Verify

Send a job URL through Telegram:

```bash
# Watch logs on VPS
hermes --profile applycling logs --follow
```

## Rollback

```bash
# On VPS: stop hosted Hermes
systemctl stop hermes-gateway-applycling

# On laptop: restart local Hermes
launchctl bootstrap gui/$(id -u)/ai.hermes.gateway-applycling
```

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| Hermes can't reach intake | Port 8080 not exposed | Check `docker-compose.prod.yml` has `127.0.0.1:8080:8080` |
| Telegram not responding | Local Hermes still running | `launchctl bootout` on laptop |
| "Invalid intake secret" (401) | Secret mismatch | Check APPLYCLING_INTAKE_SECRET matches `/opt/applycling/.env` |
| DEEPSEEK_API_KEY missing | Profile .env incomplete | Hermes needs a routing LLM even for simple forwarding |

## Limitations

- `/healthz` covers applycling + Postgres, not Hermes. Check: `systemctl status hermes-gateway-applycling`
- Hermes sessions stored at `~/.hermes/profiles/applycling/sessions/`
- Updates: re-run the install script to update hermes-agent

## Future: Containerization

The long-term plan is to add Hermes as a Docker Compose service alongside
applycling, removing the need for a separate host install. This requires
either a published hermes-agent Docker image or building from source on the VPS.

Current blocker: hermes-agent has a Dockerfile but no public image on GHCR/Docker
Hub. Once available, add to `docker-compose.prod.yml` and delete this doc.
