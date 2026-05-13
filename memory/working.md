# Working Memory

## Current Focus

Alpha onboarding/admin hardening shipped through PRs #60, #61, #62, #63, #64,
and fix/resume-preflight-guard on 2026-05-13. Next: deploy latest `main` to
the VPS, run Alembic to head `007_add_telegram_link_code`, then run the
end-to-end web + Telegram onboarding/admin playbook with a real alpha user.

## In Progress

- Multi-tenant sprint `2026-05-multi-tenant` closed 2026-05-11.
  8 tickets shipped, all 4 PRs merged to main (`0b04259`), deployed to VPS.
  Full close review at `docs/planning/sprints/2026-05-multi-tenant/SPRINT-CLOSE.md`.
- Per-user onboarding playbook at `docs/planning/sprints/2026-05-alpha-learning/ALPHA_ONBOARDING.md`.
  8 repeatable steps: telegram ID → users add → Hermes profile → bot → gateway → resume → test → feedback.
- MCP sprint `2026-05-mcp-alpha` closed 2026-05-10.
- Deferred items tracked in respective SPRINT-CLOSE.md files.
- 4 multi-tenant trade-offs documented in DECISIONS.md §2026-05-11.
- 2026-05 onboarding flow shipped: `/api/forward` localhost relay,
  `users.onboarding_state` migration (`005_add_onboarding_state`), web
  onboarding pages with signed HMAC tokens, Hermes SOUL template hardened,
  `APPLYCLING_FORWARD_ALLOWED_SOURCES` Docker-gateway allowlist. Decisions
  in DECISIONS.md §2026-05-12 (3 entries: single-bot isolation, Docker
  gateway allowlist, signed-token web onboarding).
- Deployment model: applycling/Postgres/Caddy run in Docker Compose on the
  VPS under `/opt/applycling/app`; Hermes runs on the VPS host outside
  Docker and calls `http://127.0.0.1:8080/api/forward`. The Compose bridge
  is pinned to `172.30.0.0/24` (gateway `172.30.0.1`) so Hermes traffic
  passes `verify_localhost()` via the allowlist.
- 2026-05-12 direct-main web auth commit (`d3583ea`) shipped session-cookie
  login, `/admin` invites, and migration `006_add_password_hash`. Fix-forward
  patch keeps hosted workbench operations scoped to `request.state.user_id`
  through active-run checks, status updates, artifact lookup, and background
  pipeline execution; removes unauthenticated `/onboarding/submit-resume`;
  rejects external login `next=` redirects; and updates onboarding token
  fallback to `APPLYCLING_SESSION_SECRET`.
- 2026-05-13 PR #60 fixed hosted Telegram pipeline dispatch/scoping, chat_id=0
  handling, Telegram-only email collisions, and short-text resume rejection.
- 2026-05-13 PR #61 made web profile/resume canonical on the authenticated
  user row, added PDF/DOCX/Markdown/text resume upload conversion, added admin
  Telegram link-code and duplicate-user merge tools, and added migration
  `007_add_telegram_link_code`.
- 2026-05-13 PR #62 added `/profile` onboarding progress, first-login redirect
  for incomplete profiles, self-serve Telegram link-code generation from the
  web Profile page, and Telegram resume email matching that prompts linking
  before storing resume/profile data on a newly-created Telegram row.
- 2026-05-13 PR #63 added drag-and-drop resume upload on `/profile`.
- 2026-05-13 PR #64 added the `/admin` user roster with onboarding/progress,
  Telegram state, latest-run diagnostics, per-row Link Code generation, and
  per-row Reset PW via `user_admin.reset_password()`. Review fixes included
  removing inline-JS reset confirmation XSS risk and making `chat_id_zero`
  win over `linked` via `_telegram_state()`.
- Branch `fix/resume-preflight-guard` (merged 2026-05-13) adds a generation
  guard: Telegram active URL, Telegram new URL, web submit/regenerate, and
  /api/intake all refuse to schedule pipeline work when the scoped user row
  has no stored resume text. URL-before-resume is now a relay message, not a
  skip-onboarding path.

## Blocked

(none)

## Deferred

- Alpha learning — now active, resumed after multi-tenant unblocked intake
- Web UI auth Phase 2 shipped as session-cookie auth; remaining hardening:
  session token expiry/rotation and admin invite UX.
- MCP multi-tenant (Phase 3)
- BYOK — future feature
- Error-pattern structural guard for MCP tools (from MCP sprint)
- **Onboarding token secret: require dedicated env var.**
  `applycling/ui/routes.py:_onboarding_token_secret()` falls back through
  `APPLYCLING_ONBOARDING_TOKEN_SECRET` → `APPLYCLING_SESSION_SECRET` →
  `APPLYCLING_INTAKE_SECRET`. Using a human-typed UI password as an HMAC
  key is no longer possible, but reusing the session or intake secret crosses
  purpose boundaries. For GA: drop the fallbacks, require the dedicated
  env var, document it in `docs/deploy/DEPLOY.md`. Currently acceptable
  because the whole web onboarding sits behind session auth.
- **Onboarding token expiry.** Signed tokens from `_sign_onboarding_user_id()`
  never expire. A leaked `/onboarding/confirm?token=...` URL is valid until
  the user transitions out of the `confirming` state. Add `iat` + max-age
  (e.g. 24h) check in `_verify_onboarding_token()`. Low priority — flow
  completes in minutes and sits behind session auth.
- **Confirm screen pre-fill UX — RESOLVED by PR #62.** `onboarding_confirm()` now
  pre-fills fields from the stored user profile.

## Next Steps — VPS deploy + alpha onboarding/web-auth test

Order matters. The container must be running the new migration before the
Hermes profile relies on new link-code behavior, otherwise Telegram/web linking
will hit a schema that doesn't have `telegram_link_code_hash`.

1. **Pre-deploy on VPS (`/opt/applycling`):**
   - `git pull` latest `main` (contains PRs #60, #61, #62, #63, #64).
   - Append to `/opt/applycling/.env`:
     - `APPLYCLING_FORWARD_ALLOWED_SOURCES=172.30.0.1`
     - `APPLYCLING_SESSION_SECRET=<generate via `openssl rand -hex 32`>`
     - `APPLYCLING_ADMIN_USER_ID=<your users.id UUID>`
     - `APPLYCLING_ONBOARDING_TOKEN_SECRET=<generate via `openssl rand -hex 32`>`
       (recommended; otherwise it falls back to session secret).
   - Remove `APPLYCLING_UI_AUTH_USER` and `APPLYCLING_UI_AUTH_PASSWORD`.
   - Confirm `DATABASE_URL`, `APPLYCLING_INTAKE_SECRET`,
     `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USERS` are still set.

2. **Bring up new image:**
   - `docker compose -f docker-compose.prod.yml build applycling`
   - `docker compose -f docker-compose.prod.yml up -d` — Compose will recreate
     the bridge network with the pinned `172.30.0.0/24` subnet.
   - Verify the new gateway: `docker network inspect <network> | grep Gateway`
     should show `172.30.0.1`. If not, take down + recreate the network.

3. **Run the Alembic migration:**
   - `docker compose exec applycling python -m alembic upgrade head`
   - Expect head = `007_add_telegram_link_code`.

4. **Smoke test the container in isolation:**
   - `curl -s http://127.0.0.1:8080/healthz` → 200.
   - From the **host** (not the container):
     `curl -s -X POST http://127.0.0.1:8080/api/forward -H 'Content-Type: application/json' -d '{"telegram_id":99999999,"chat_id":99999999,"first_name":"Smoke","message_text":"hello"}'`
     → 200 with a `relay_message` (not 403). 403 here means the gateway
     allowlist is wrong.
   - Clean up: `DELETE FROM users WHERE telegram_id = 99999999;`

5. **Update Hermes SOUL on the VPS host (do NOT create a second profile/bot):**
   - `cp /opt/applycling/app/docs/deploy/hermes_forwarding_template.md \
       ~/.hermes/profiles/applycling/SOUL.md`
   - Verify the SOUL POSTs to `http://127.0.0.1:8080/api/forward` only,
     references no secrets/env vars.
   - Before restarting the gateway, confirm no pipeline run is active:
     `SELECT id, user_id, started_at FROM pipeline_runs WHERE status='running';`
     should return 0 rows. Restarting mid-generation can orphan the run
     (startup `sweep_all_running()` will recover it on next boot, but the
     user gets a confusing partial reply).
   - Restart the Hermes gateway (launchctl unload/load the plist, or
     `systemctl --user restart hermes-gateway-applycling`, whichever the VPS
     uses).
   - Sanity-check `~/.hermes/profiles/applycling/.env` contains only
     `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USERS`, `DEEPSEEK_API_KEY`,
     `HERMES_GATEWAY_TOKEN` — no `APPLYCLING_INTAKE_SECRET`, no
     `DATABASE_URL`.

6. **End-to-end onboarding test (use your own Telegram account):**
   - New-user resume path: send a multi-line resume → expect
     "Reading your resume now…" relay; DB row has
     `onboarding_state='confirming'`, `resume` populated.
   - Approval: send `looks good` → relay "You're all set!";
     `onboarding_state='active'`.
   - Active job: send a real job URL → relay "On it…"; package generates,
     PDF arrives via Telegram, `pipeline_runs` row finishes `succeeded`.
   - URL-before-resume path (separate test account, or reset): send a URL as
     first message → expect a resume-required relay message (200) and no
     pipeline run / daily-cap charge.
   - Daily-cap path: hit 10 generations in a day → 11th returns 429 with
     "Daily generation limit reached".

7. **Web onboarding sanity:**
   - Invite a test user from `/admin`, log in with the generated password,
     and confirm first login redirects to `/profile` while profile/resume is
     incomplete.
   - Upload a PDF/DOCX/Markdown/text resume from `/profile`; confirm it is
     converted into stored text in `users.resume` on the authenticated row.
   - Generate a Telegram link code from `/profile`, send `link CODE` to the
     Telegram bot, and confirm Telegram attaches to the same user row.
   - Try `https://<vps>/onboarding/confirm` with no token / a tampered token
     → 403 for the legacy confirm route.
   - Visit `/admin` as `APPLYCLING_ADMIN_USER_ID`, invite a test user, log in
     with the generated password, submit a job, and confirm the job reaches
     `generating` instead of failing due to default-user scoping.
   - From `/admin`, confirm the user roster renders against real Postgres,
     Link Code shows a `link XXXXXXXX` banner, and Reset PW shows a one-time
     password that invalidates the old password and logs in with the new one.

8. **Update memory after dogfood:** if anything broke or behaved
   unexpectedly, append findings to this file under "In Progress" and
   either fix-forward or open a follow-up ticket. When the sprint closes,
   write `docs/planning/sprints/2026-05-alpha-learning/SPRINT-CLOSE.md` and
   move the shipped capability mention out of "Current Focus".
