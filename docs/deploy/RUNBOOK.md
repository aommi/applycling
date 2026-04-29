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

1. After restart, the startup stale-run sweep (PR 5) marks the run as "failed"
2. The job must be regenerated manually
3. To avoid this: wait for the current generation to complete before restarting

### Asymmetric restart (Hermes only)

Restarting only the Hermes container is always safe — it only forwards URLs.

```bash
docker compose -f docker-compose.prod.yml restart hermes
```

## Backup

### Quick Postgres dump

```bash
docker compose -f docker-compose.prod.yml exec postgres \
  pg_dump -U applycling applycling > /tmp/backup-$(date +%Y%m%d-%H%M).sql
```

Copy to your laptop:

```bash
scp user@vps:/tmp/backup-*.sql .
```

### Artifact backup

```bash
tar -czf /tmp/artifacts-$(date +%Y%m%d).tar.gz -C /opt/applycling output/
scp user@vps:/tmp/artifacts-*.tar.gz .
```

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
# (Check BotFather for token status)
```

### "Another generation is already running" persists

A crashed process may have left a stale `running` row if the startup sweep didn't
run. Clear it manually:

```bash
docker compose -f docker-compose.prod.yml exec postgres psql -U applycling -c \
  "UPDATE pipeline_runs SET status='failed', status_reason='Manual cleanup', finished_at=NOW() WHERE status='running';"
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
# Clean Docker build cache
docker builder prune

# Clean old Docker images (keep current)
docker image prune

# Check artifact folder size
du -sh /opt/applycling/output/*

# ⚠️ NEVER run: docker system prune --volumes
# (this deletes pgdata — all job data lost)
```

## Known Limitations

1. **No Hermes liveness check:** `/healthz` only covers the workbench. Monitor
   Hermes separately via `docker compose logs`.
2. **Asymmetric restart safety:** Restarting applycling during generation kills
   the task. Restarting only Hermes is always safe.
3. **Single disk, no replication:** If the VPS disk fails, all data is lost.
   Regular backups recommended.
4. **No automated backups:** Manual `pg_dump` + `scp` only.
5. **No log rotation for Docker:** `docker compose logs` includes all history.
   May grow large over months.

## Local CLI Smoke Test

After hosted changes, verify local CLI still works:

```bash
APPLYCLING_DB_BACKEND=sqlite python -m applycling.cli list
```

This exercises store resolution without running a paid LLM generation.
