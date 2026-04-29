# applycling — Hosted Deployment Guide

**Target:** Kamatera VPS (1 vCPU, 2 GB RAM, 20 GB SSD, Ubuntu 24.04)
**Cost:** $6/month flat — no metering, no surprises
**Scope:** Single-user dogfood deployment behind app-level Basic Auth

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Kamatera VPS (Ubuntu 24.04, 1 vCPU, 2 GB RAM, 20 GB SSD) │
│                                                             │
│  docker compose -f docker-compose.prod.yml                  │
│  ┌──────────┐  ┌───────────────┐  ┌──────────────────────┐ │
│  │  Caddy   │  │  applycling   │  │  postgres:16         │ │
│  │  :80/443 │──│  :8080 (int)  │──│  :5432 (internal)    │ │
│  │  (TLS)   │  │  CLI serve    │  │  pgdata volume        │ │
│  └──────────┘  └───────┬───────┘  └──────────────────────┘ │
│                        │                                     │
│           ┌────────────┼────────────┐                       │
│     /opt/applycling/   │   /opt/applycling/                  │
│        data/ (read)    │      output/ (write)                │
│                        │                                     │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Hermes (Phase 2 — not yet deployed)                 │   │
│  │  separate container, forwards to applycling intake    │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Separation from Local Dev

| File | Purpose |
|---|---|
| `docker-compose.yml` | Local dev (Postgres + applycling, no TLS) |
| `docker-compose.prod.yml` | Hosted deploy (adds Caddy TLS, bind mounts, env vars) |

The local dev compose is unchanged. The prod compose is additive and independent.

## Prerequisites

### DNS

Point an A (and optionally AAAA) record at your VPS IP address before deploying.
Caddy requires a valid DNS record to issue Let's Encrypt certificates.

Example: `applycling.yourdomain.com → <VPS_IP>`

### Firewall (UFW)

```bash
sudo ufw allow 22    # SSH
sudo ufw allow 80    # HTTP (Let's Encrypt validation)
sudo ufw allow 443   # HTTPS
sudo ufw enable
```

### System

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y docker.io docker-compose-v2 unattended-upgrades
sudo systemctl enable --now docker
sudo usermod -aG docker $USER   # log out and back in
sudo dpkg-reconfigure unattended-upgrades   # enable security updates
```

---

## Server Layout

```
/opt/applycling/
├── .env                  # ALL secrets (gitignored, never committed)
├── data/                 # Private user files (bind-mounted → /app/data)
│   ├── config.json
│   ├── profile.json
│   ├── resume.md
│   ├── stories.md
│   └── applicant_profile.json
├── output/               # Generated artifacts (bind-mounted → /app/output)
└── app/                  # Git clone of applycling repo
```

---

## Environment Variables (`/opt/applycling/.env`)

Create this file BEFORE any `docker compose` command. All values here are secrets —
never commit them.

```bash
# ── Database ───────────────────────────────────────────
APPLYCLING_DB_BACKEND=postgres
DATABASE_URL=postgresql://applycling:<POSTGRES_PASSWORD>@postgres:5432/applycling

# ── Pipeline provider keys ─────────────────────────────
ANTHROPIC_API_KEY=***
OPENAI_API_KEY=***
GOOGLE_API_KEY=***

# ── UI Auth (PR3) ──────────────────────────────────────
APPLYCLING_UI_AUTH_USER=<your-username>
APPLYCLING_UI_AUTH_PASSWORD=<generated-password>

# ── Intake (PR6) ───────────────────────────────────────
APPLYCLING_INTAKE_SECRET=<generated-secret>

# ── Active-run guard ───────────────────────────────────
APPLYCLING_STALE_RUN_TIMEOUT_MINUTES=120
```

### Secret Independence

Each secret must be independently generated. Do **not** reuse or derive one from another:

| Secret | Purpose | Rotation Impact |
|---|---|---|
| `APPLYCLING_UI_AUTH_PASSWORD` | Workbench web UI access | Restart applycling container |
| `APPLYCLING_INTAKE_SECRET` | Hermes → workbench API auth | Update Hermes config + restart both containers |
| `TELEGRAM_BOT_TOKEN` | Telegram bot identity | Regenerate via BotFather, update env, restart Hermes |
| `DEEPSEEK_API_KEY` | Hermes routing LLM (DeepSeek) | Rotate on DeepSeek dashboard, update env, restart Hermes |
| `ANTHROPIC_API_KEY` | Pipeline generation | Rotate on Anthropic console, update env, restart applycling |

---

## Data Provisioning

Private user files live in `/opt/applycling/data/` on the host, bind-mounted to
`/app/data` inside the container. Provision them once via `scp`:

```bash
scp data/config.json data/profile.json data/resume.md data/stories.json \
    user@vps:/opt/applycling/data/
```

The app runs as root (Dockerfile has no `USER` directive — acceptable for
single-user dogfood). No `chown` needed.

To update a file (e.g., new resume), `scp` the new version and restart applycling:

```bash
scp data/new_resume.md user@vps:/opt/applycling/data/resume.md
docker compose -f docker-compose.prod.yml restart applycling
```

---

## Deployment

### First Deploy

```bash
# 1. Clone the repo
cd /opt/applycling
git clone https://github.com/<user>/applycling.git app
cd app

# 2. Create directories
mkdir -p /opt/applycling/{data,output}

# 3. Create .env file (see Environment Variables section above)
#    Edit /opt/applycling/.env with all required secrets

# 4. Provision private data files (see Data Provisioning section above)
#    scp data/* to /opt/applycling/data/

# 5. Start Postgres only
docker compose -f docker-compose.prod.yml up -d postgres

# 6. Wait for Postgres readiness (not sleep — actual health check)
until docker compose -f docker-compose.prod.yml exec postgres pg_isready -U applycling; do
  echo "Waiting for Postgres..."
  sleep 2
done

# 7. Run migrations
docker compose -f docker-compose.prod.yml run --rm applycling alembic upgrade head

# 8. Start all services
docker compose -f docker-compose.prod.yml up -d --build
```

### Redeploy (update code)

```bash
cd /opt/applycling/app
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

---

## Logs

```bash
# All services
docker compose -f docker-compose.prod.yml logs

# Specific service, follow mode
docker compose -f docker-compose.prod.yml logs -f applycling
docker compose -f docker-compose.prod.yml logs -f caddy

# Last 100 lines
docker compose -f docker-compose.prod.yml logs --tail 100
```

---

## Postgres Backup

Simple off-box backup for dogfood. Not a full backup drill — just enough to
recover from catastrophic failure.

```bash
docker compose -f docker-compose.prod.yml exec postgres \
  pg_dump -U applycling applycling > backup-$(date +%Y%m%d).sql
```

Copy `backup-*.sql` to your laptop or another safe location.

---

## TLS (Caddy)

Caddy in the `docker-compose.prod.yml` handles:

- Automatic Let's Encrypt certificate issuance
- Automatic renewal (Caddy manages this internally)
- HTTP → HTTPS redirect
- Reverse proxy to `applycling:8080`

Caddy's data (certificates, OCSP staples) is stored in a Docker volume (`caddy_data`)
so it survives container restarts.

### Custom Domain

Edit the `Caddyfile` at repo root and set your domain:

```
your-domain.com {
    reverse_proxy applycling:8080
}
```

Then redeploy: `docker compose -f docker-compose.prod.yml up -d --build caddy`

---

## Operational Notes

- **Do not run `docker system prune --volumes`** — this will delete the Postgres
  data volume (`pgdata`) and you'll lose all job data.
- **Do not redeploy mid-generation** — the in-process background task will be killed.
  The startup stale-run sweep will mark it as failed on next start.
- `unattended-upgrades` is configured for security patches. Check periodically with
  `sudo unattended-upgrades --dry-run`.
- Monitor disk: `df -h /opt`. 20 GB SSD is ample for Docker images, Postgres data,
  and generated PDFs for a single user.
- Monitor RAM: `docker stats`. Chromium PDF rendering peaks at ~500 MB. If you see
  OOM kills, upgrade to 4 GB VPS.

---

## Future Portability

The Docker images built by this setup are not coupled to Kamatera. The same images
can be deployed on:

- **Railway** — swap `docker-compose.prod.yml` for a `railway.json` service definition
- **Fly.io** — use `fly.toml` with the same Docker image
- **Mac Mini / home server** — same compose file, just update the domain in `Caddyfile`
- **Any VPS** — the compose file and Caddy config are provider-agnostic

Only the `.env` file and DNS record are host-specific.

---

## What's NOT Covered (by design — future sprints)

- Multi-user auth or isolation
- Object storage (local disk suffices for single-user dogfood)
- Log aggregation or alerting
- Automated backups
- CI/CD pipeline
- Zero-downtime deploys
- Health check alerting
