# Data Provisioning — Hosted Deployment

## Overview

applycling's pipeline needs private single-user data to generate tailored application
packages. These files contain resume text, profile information, stories, and model
configuration. **They must NOT be baked into the container image.**

Instead, they are provisioned once to the host filesystem and bind-mounted into
the container.

## Required Files

| File | Purpose | Format |
|---|---|---|
| `data/config.json` | Model selection, output directory | JSON |
| `data/profile.json` | Applicant profile (name, skills, experience) | JSON |
| `data/resume.md` | Base resume text | Markdown |
| `data/stories.md` | Behavioral stories / STAR examples | Markdown |
| `data/applicant_profile.json` | Extended applicant details | JSON |

All in-repo skill templates (`applycling/skills/*`) ship with the Docker image
automatically. Only private `data/` files need out-of-band provisioning.

## Provisioning (First Deploy)

Copy your local `data/` directory to the VPS:

```bash
# From your laptop
scp data/config.json user@vps:/opt/applycling/data/
scp data/profile.json user@vps:/opt/applycling/data/
scp data/resume.md user@vps:/opt/applycling/data/
scp data/stories.md user@vps:/opt/applycling/data/
scp data/applicant_profile.json user@vps:/opt/applycling/data/
```

The files are bind-mounted in `docker-compose.prod.yml`:

```yaml
volumes:
  - /opt/applycling/data:/app/data
```

The container sees them at `/app/data/`. No runtime upload step is needed.

## Config Note

Ensure `data/config.json` has the correct output directory for container use:

```json
{
  "output_dir": "/app/output",
  ...
}
```

If `output_dir` is omitted or set to `"./output"`, it resolves to `/app/output`
inside the container (the working directory is `/app`).

## Refreshing Data Files

When your resume, profile, or stories change:

```bash
# Upload the new version
scp data/new_resume.md user@vps:/opt/applycling/data/resume.md

# Restart the applycling container to pick up changes
docker compose -f docker-compose.prod.yml restart applycling
```

## Security

- Files are root-owned on the host (container runs as root).
- Files are never committed to the repository.
- Files are on the host filesystem, not inside any Docker volume — they survive
  `docker compose down` but NOT `rm -rf /opt/applycling/data/`.
- Backup critical files with your other personal data.

## Migration Path

This manual `scp` flow is acceptable for single-user dogfood. For closed beta or
SaaS, consider:

- A protected file upload UI in the workbench
- Secrets management service (Vault, Doppler, etc.)
- User-specific data stored in Postgres rather than filesystem files
