# Hosted Hermes — Phase 2

## Overview

Phase 2 moves the Hermes Telegram gateway from the local machine into the hosted
environment. After this, Telegram intake works without the local laptop running.

```
Telegram → hosted Hermes → POST http://applycling:8080/api/intake → pipeline → Postgres + artifacts
```

## Prerequisites

- Phase 1 (local Hermes forwarding) is verified and working
- VPS has Docker and git installed

## Setup

### 1. Build the hermes-agent image

Clone and build hermes-agent on the VPS:

```bash
cd /opt
git clone https://github.com/nous/hermes-agent.git
cd hermes-agent
docker build -t hermes-agent:latest .
```

The build takes a few minutes. The resulting image is ~2 GB.

### 2. Create the applycling profile

Create the profile directory structure:

```bash
mkdir -p /opt/hermes-profile/profiles/applycling/sessions
```

#### config.yaml

Copy the local applycling profile config:

```bash
scp ~/.hermes/profiles/applycling/config.yaml root@vps:/opt/hermes-profile/profiles/applycling/
```

Or create a minimal one:

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

Create `/opt/hermes-profile/profiles/applycling/.env`:

```bash
# Telegram
TELEGRAM_BOT_TOKEN=<same as local applycling bot>
TELEGRAM_ALLOWED_USERS=26605267

# Routing LLM (DeepSeek — separate from pipeline's Anthropic key)
DEEPSEEK_API_KEY=<your deepseek key>

# Intake — internal Docker network, not the public URL
APPLYCLING_INTAKE_URL=http://applycling:8080/api/intake
APPLYCLING_INTAKE_SECRET=<same as /opt/applycling/.env>

# Gateway token (generate with: openssl rand -hex 16)
HERMES_GATEWAY_TOKEN=<generate new>
```

Important: `APPLYCLING_INTAKE_URL` uses the internal Docker hostname
`applycling:8080`, not `https://app.applycling.com/api/intake`. The Hermes
container is on the same Docker network and reaches applycling directly.

#### SOUL.md

Copy the forwarding template:

```bash
cp docs/deploy/hermes_forwarding_template.md /opt/hermes-profile/profiles/applycling/SOUL.md
```

### 3. Start Hermes

```bash
cd /opt/applycling/app
docker compose -f docker-compose.prod.yml up -d hermes
```

### 4. Stop local Hermes

On your laptop, stop the local Hermes gateway so it doesn't compete for the
Telegram bot token:

```bash
launchctl bootout gui/$(id -u)/ai.hermes.gateway-applycling
```

### 5. Verify

Send a job URL through Telegram. The hosted Hermes should pick it up and forward
to the intake endpoint.

```bash
# Check Hermes logs
docker compose -f docker-compose.prod.yml logs -f hermes
```

## Rollback to Phase 1

If something goes wrong, revert to local Hermes:

```bash
# On VPS: stop the hosted Hermes
docker compose -f docker-compose.prod.yml stop hermes

# On laptop: restart local Hermes
launchctl bootstrap gui/$(id -u)/ai.hermes.gateway-applycling
```

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| Hermes container exits immediately | Missing profile files | Check `/opt/hermes-profile/profiles/applycling/` has config.yaml, .env, SOUL.md |
| Telegram not responding | Old local Hermes still running | `launchctl bootout` on laptop |
| "Connection refused" to intake | Wrong INTAKE_URL | Must be `http://applycling:8080/api/intake` (internal) |
| "Invalid intake secret" (401) | Secret mismatch | Check APPLYCLING_INTAKE_SECRET matches `/opt/applycling/.env` |
| DEEPSEEK_API_KEY missing | Profile .env incomplete | Hermes needs a routing LLM even for simple forwarding |

## Limitations

- `/healthz` on the workbench covers applycling + Postgres, not Hermes liveness.
  If Hermes stops polling Telegram, check: `docker compose -f docker-compose.prod.yml ps hermes`
- Hermes sessions are stored in the hermes-profile mount and persist across
  container restarts.
- The hermes-agent image must be rebuilt when hermes-agent is updated upstream.
