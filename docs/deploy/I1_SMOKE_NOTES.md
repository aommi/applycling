# I1 Smoke Test — Phase 1 Bridge Validation

**Status:** Pending manual verification
**Date:** 2026-04-29
**Prerequisites:** PRs 1-6 merged and deployed to VPS, local Hermes forwarding configured

## Smoke Test Checklist

Run these steps after deploying Phase 1 (local Hermes → hosted applycling).

### 1. Liveness

- [ ] `curl https://applycling.yourdomain.com/healthz` returns `{"status":"ok","db":"reachable"}`
- [ ] Workbench UI is reachable at `https://applycling.yourdomain.com`
- [ ] Job board loads with no errors

### 2. Auth Gate

- [ ] Workbench requires Basic Auth (browser prompts for credentials)
- [ ] `/healthz` is accessible without auth
- [ ] Wrong credentials are rejected with 401
- [ ] Correct credentials allow access

### 3. Local SQLite Still Works

- [ ] `APPLYCLING_DB_BACKEND=sqlite` local CLI works (e.g., `python -m applycling.cli list`)
- [ ] Local workbench at `http://127.0.0.1:8080` works without auth

### 4. Telegram → Hosted Intake

- [ ] Send a real job URL to the Telegram bot
- [ ] Hermes forwards to hosted intake (check Hermes logs)
- [ ] Job row exists in hosted Postgres: `docker compose -f docker-compose.prod.yml exec postgres psql -U applycling -c "SELECT id, title, status, source_url FROM jobs ORDER BY created_at DESC LIMIT 5;"`
- [ ] Job appears in the workbench at the public URL
- [ ] Status shows "generating" initially, then "reviewing" (or "failed")

### 5. Intake Returns Promptly

- [ ] `curl -X POST https://applycling.yourdomain.com/api/intake -H "Content-Type: application/json" -H "X-Intake-Secret: <secret>" -d '{"job_url":"https://example.com/jobs/test"}'` returns within 2 seconds
- [ ] Response contains `{"job_id":"...","status":"generating"}`

### 6. Active-Run Guard

- [ ] While a generation is running, send another job URL through Telegram
- [ ] Hermes receives HTTP 409 "Another generation is already running"
- [ ] Telegram user sees clear message (not silent failure)
- [ ] No extra job is created in Postgres

### 7. Artifacts

- [ ] Generated artifacts appear in the workbench after pipeline completes
- [ ] Resume PDF and cover letter PDF are viewable/downloadable
- [ ] Artifacts survive `docker compose -f docker-compose.prod.yml restart applycling`

### 8. Mobile UI

- [ ] Workbench is usable on a mobile viewport for status checks
- [ ] Meta-refresh works — status updates automatically every 10s during generation

### 9. Desktop Web UI

- [ ] Artifact review works (PDF preview, markdown view)
- [ ] Status actions work (archive, apply, etc.)
- [ ] Regenerate button works and shows guard rejection if a run is active

### 10. Failure Visibility

- [ ] If a generation fails, the job status shows "failed"
- [ ] Status reason is visible in the workbench
- [ ] Hermes/Telegram reports the failure

## Issues Found

<!-- Fill in any issues discovered during smoke testing -->

### Issue 1

- **Symptom:**
- **Root cause:**
- **Fix:**
- **Status:**

## Sign-off

- [ ] All checklist items pass
- [ ] Any issues are documented above with fixes
- [ ] Ready for Phase 2 (hosted Hermes)
