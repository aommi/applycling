# Artifact Durability — Hosted Deployment

## What's in Scope

Generated applycling packages (resumes, cover letters, positioning briefs, etc.)
are stored on the host's filesystem so they survive container restarts and redeploys.

This is **personal dogfood durability** — one VPS, one disk. This is NOT final
SaaS-grade storage with replication or backups.

## Artifact Path

| Layer | Path |
|---|---|
| Host filesystem | `/opt/applycling/output/` |
| Container (bind mount) | `/app/output` |
| Config (`data/config.json`) | `output_dir` defaults to `./output`, which resolves to `/app/output` in the container |

The bind mount is defined in `docker-compose.prod.yml`:

```yaml
volumes:
  - /opt/applycling/output:/app/output
```

Generated artifacts are written to subdirectories under `/app/output/<job-id>/`.
Each job gets its own folder with `resume.pdf`, `cover_letter.pdf`, `job.json`, etc.

## Survival Guarantees

| Event | Artifacts Survive? |
|---|---|
| Container restart (`docker compose restart applycling`) | Yes — bind mount preserves files on host |
| Container rebuild (`docker compose up -d --build`) | Yes — same reason |
| System reboot | Yes — host filesystem persists |
| Docker volume prune | **No** — `docker system prune --volumes` would delete named volumes (pgdata) but NOT bind mounts. See also `docs/deploy/DEPLOY.md` § Operational Notes. |
| Host disk failure | **No** — single disk, no replication |

## Limitations

- **Single disk:** If the VPS disk dies, artifacts are gone. No off-box replication.
- **Root-owned files:** The container runs as root (no `USER` directive in Dockerfile),
  so generated artifacts are root-owned on the host. Manual cleanup or editing via
  SSH may require `sudo`.
- **No object storage:** Artifacts are on local disk only. Object storage (S3, R2)
  is out of scope for this dogfood sprint.
- **No lifecycle management:** Artifacts accumulate indefinitely. Manual cleanup
  may be needed if the 20 GB SSD fills up.

## Verification

After generating a job:

```bash
# 1. Confirm artifacts exist on host
ls -la /opt/applycling/output/

# 2. Restart the applycling container
docker compose -f docker-compose.prod.yml restart applycling

# 3. Confirm artifacts are still visible through the workbench UI
# Replace credentials with your APPLYCLING_UI_AUTH_USER:PASSWORD values.
curl -u user:pass https://your-domain.com/jobs/<id>
```

## Future (Closed Beta / SaaS)

For closed beta and beyond, consider:

- Object storage (S3, Cloudflare R2) for artifacts
- Separate artifact service with signed URLs
- Artifact lifecycle policies (auto-cleanup after N days)
- Regular off-box backups (S3 sync or `pg_dump` + artifact tarball)
