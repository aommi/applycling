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

### 1. Install Hermes on the VPS

```bash
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash
```

This installs the `hermes` CLI and dependencies.

### 2. Create the applycling profile

Create the profile directory:

```bash
mkdir -p ~/.hermes/profiles/applycling/sessions
```

#### config.yaml

Create `~/.hermes/profiles/applycling/config.yaml`:

```yaml
model:
  default: deepseek-v4-pro
  provider: deepseek
toolsets:
  - hermes-cli
agent:
  max_turns: 90
```

#### .env

Create `~/.hermes/profiles/applycling/.env`:

```bash
# Telegram (same bot token as local applycling profile)
TELEGRAM_BOT_TOKEN=<your bot token>
TELEGRAM_ALLOWED_USERS=26605267

# Routing LLM (DeepSeek — minimal tokens for URL routing)
DEEPSEEK_API_KEY=<your deepseek key>

# Intake — localhost since Hermes runs on the host
APPLYCLING_INTAKE_URL=http://127.0.0.1:8080/api/intake
APPLYCLING_INTAKE_SECRET=<same as /opt/applycling/.env>

# Gateway token
HERMES_GATEWAY_TOKEN=<openssl rand -hex 16>
```

#### SOUL.md

From your laptop:

```bash
scp ~/.hermes/profiles/applycling/SOUL.md root@applycling:~/.hermes/profiles/applycling/
```

Or copy the template from the repo:

```bash
cp /opt/applycling/app/docs/deploy/hermes_forwarding_template.md ~/.hermes/profiles/applycling/SOUL.md
```

### 3. Install and start the gateway service

```bash
hermes --profile applycling gateway install --force
```

This creates a systemd service that runs `hermes --profile applycling gateway run`.

Check status:

```bash
systemctl status hermes-gateway-applycling
hermes --profile applycling gateway status
```

### 4. Stop local Hermes

On your laptop:

```bash
launchctl bootout gui/$(id -u)/ai.hermes.gateway-applycling
```

### 5. Verify

Send a job URL through Telegram. The hosted Hermes should pick it up.

```bash
# Watch logs
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
