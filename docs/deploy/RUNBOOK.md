# applycling — Hosted Dogfood Runbook

## Quick Reference

| Task | Command |
|---|---|
| Status | `docker compose -f docker-compose.prod.yml ps` |
| Logs | `docker compose -f docker-compose.prod.yml logs -f --tail 100` |
| Restart all | `docker compose -f docker-compose.prod.yml restart` |
| Rebuild + restart | `cd /opt/applycling/app && git pull && docker compose -f docker-compose.prod.yml up -d --build` |
| Restart applycling only | `docker compose -f docker-compose.prod.yml restart applycling` |
| Restart Hermes only | `docker compose -f docker-compose.prod.yml restart hermes` |
| Health check | `curl https://your-domain.com/healthz` |
| DB connect | `docker compose -f docker-compose.prod.yml exec postgres psql -U applycling` |

## Daily Operations

### Check if everything is running

```bash
docker compose -f docker-compose.prod.yml ps
```

All services should show `Up` status: postgres, applycling, caddy, hermes.

### View recent logs

```bash
# All services
docker compose -f docker-compose.prod.yml logs --tail 50

# Specific service
docker compose -f docker-compose.prod.yml logs --tail 50 applycling
docker compose -f docker-compose.prod.yml logs --tail 50 hermes
```

### Check disk usage

```bash
df -h /opt
du -sh /opt/applycling/output/
```

20 GB SSD should last months for single-user dogfood. Generated packages are
~1-5 MB each.

### Check RAM usage

```bash
docker stats --no-stream
```

2 GB RAM is the floor. If swap usage grows or OOM kills appear in logs, upgrade
to 4 GB VPS.

## Restart Procedures

### Safe restart (no active generation)

1. Verify no generation is running: check workbench for "generating" jobs
2. `docker compose -f docker-compose.prod.yml restart`

### Restart during active generation

**⚠️ Restarting applycling mid-generation kills the in-process background task.**

1. After restart, the startup crash recovery sweep marks the pipeline run as "failed"
   in `pipeline_runs`, but the **job status in the workbench will still read
   "generating"** — the sweep does not update jobs. This is a known limitation.
   The guard is cleared (next generation can start), but the stalled job must be
   regenerated manually.
2. To avoid this: wait for the current generation to complete before restarting.

### Asymmetric restart (Hermes only)

Restarting only the Hermes container is always safe — it only forwards URLs.

```bash
docker compose -f docker-compose.prod.yml restart hermes
```

## Backup

Create the backup directory once:

```bash
mkdir -p /opt/applycling/backups
```

### Quick Postgres dump

```bash
docker compose -f docker-compose.prod.yml exec postgres \
  pg_dump -U applycling applycling > /opt/applycling/backups/backup-$(date +%Y%m%d-%H%M).sql
```

Copy to your laptop:

```bash
scp user@vps:/opt/applycling/backups/backup-*.sql .
```

Recommended cadence: weekly pg_dump + artifact tarball. Keep last 4 backups.

### Artifact backup

```bash
tar -czf /opt/applycling/backups/artifacts-$(date +%Y%m%d).tar.gz -C /opt/applycling output/
scp user@vps:/opt/applycling/backups/artifacts-*.tar.gz .

## Troubleshooting

### Workbench returns 502 / not reachable

```bash
# Check if applycling crashed
docker compose -f docker-compose.prod.yml logs applycling --tail 50

# Check if Caddy can reach applycling
docker compose -f docker-compose.prod.yml exec caddy wget -qO- http://applycling:8080/healthz

# Restart applycling
docker compose -f docker-compose.prod.yml restart applycling
```

### Telegram bot not responding

```bash
# Check Hermes logs
docker compose -f docker-compose.prod.yml logs hermes --tail 50

# Check if Hermes can reach intake endpoint
docker compose -f docker-compose.prod.yml exec hermes \
  curl -s http://applycling:8080/healthz

# Verify Telegram bot token is still valid
curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getMe" | grep -q '"ok":true' \
  && echo "Token valid" || echo "Token invalid — regenerate via BotFather"
```

### "Another generation is already running" persists

A crashed process may have left a stale `running` row if the startup sweep didn't
run. Clear it manually — this also resets any orphaned "generating" jobs so the
workbench shows consistent state:

```bash
docker compose -f docker-compose.prod.yml exec postgres psql -U applycling <<'SQL'
UPDATE pipeline_runs SET status='failed', status_reason='Manual cleanup', finished_at=NOW()
  WHERE status='running';
UPDATE jobs SET status='failed', updated_at=NOW()
  WHERE status='generating';
SQL
```

### "Database unreachable" in /healthz

```bash
# Check Postgres status
docker compose -f docker-compose.prod.yml ps postgres
docker compose -f docker-compose.prod.yml logs postgres --tail 20

# Restart Postgres if needed
docker compose -f docker-compose.prod.yml restart postgres
```

### Disk full

```bash
# Clean Docker build cache (add -f for non-interactive)
docker builder prune -f

# Clean unused images (add -a to remove all unused, not just dangling)
docker image prune -a -f

# Check artifact folder size
du -sh /opt/applycling/output/*

# ⚠️ NEVER run: docker system prune --volumes
# (this deletes pgdata — all job data lost)
```

## Known Limitations

1. **No Hermes liveness check:** `/healthz` only covers the workbench. Monitor
   Hermes separately via `docker compose logs`.
2. **Asymmetric restart safety:** Restarting applycling during generation kills
   the task and leaves the job showing "generating" in the UI (the sweep clears
   the guard but does not update job status). See "Restart during active
   generation" above.
3. **Failure reasons not rendered in UI:** status_reason is stored in the
   database but not displayed in the workbench web UI. Read via:
   `docker compose -f docker-compose.prod.yml exec postgres psql -U applycling -c "SELECT id, status, status_reason, updated_at FROM pipeline_runs ORDER BY updated_at DESC LIMIT 5;"`
4. **Single disk, no replication:** If the VPS disk fails, all data is lost.
   Regular backups recommended.
5. **No automated backups:** Manual `pg_dump` + `scp` only.
6. **No log rotation for Docker:** `docker compose logs` includes all history.
   May grow large over months.

### Convenience alias

On the VPS, add to `~/.bashrc`:

```bash
alias dcp='docker compose -f /opt/applycling/app/docker-compose.prod.yml'
```

Then use `dcp ps`, `dcp logs -f`, `dcp restart applycling`, etc.

## Local CLI Smoke Test

After hosted changes, verify local CLI still works:

```bash
APPLYCLING_DB_BACKEND=sqlite python -m applycling.cli list
```

This exercises store resolution without running a paid LLM generation.
