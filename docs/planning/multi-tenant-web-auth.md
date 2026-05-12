# Plan: Multi-Tenant Web Auth for Alpha

**Status:** Plan
**Created:** 2026-05-12
**Author:** Hermes Agent (deepseek-v4-pro)

## Goal

Alpha users can log into the web workbench and see only their own jobs, profiles, and artifacts. No shared view. Replaces the single-password Basic Auth gate with per-user sessions.

## Why Now

The web workbench currently uses shared Basic Auth (`APPLYCLING_UI_AUTH_USER` / `APPLYCLING_UI_AUTH_PASSWORD`). Anyone with those credentials sees everything. Telegram onboarding already resolves users by `telegram_id` and scopes pipeline runs — the web path needs the same isolation before alpha sharing.

## Proposed Work

### T1. Add password hash to users table

Add `password_hash TEXT` column via Alembic migration.

- Users created via Telegram onboarding get `password_hash = NULL` (Telegram-only, no web access).
- Web users get a password hash set during invite or registration.
- Existing users migrate with `NULL` — no password, no web access until explicitly invited.

### T2. Password hashing + session token helpers

New module: `applycling/auth.py`. Zero new dependencies.

```python
import hashlib, hmac, os

def hash_password(plaintext: str) -> str:
    """PBKDF2-SHA256 with 16-byte salt."""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", plaintext.encode(), salt, 100_000)
    return salt.hex() + ":" + dk.hex()

def verify_password(plaintext: str, stored: str) -> bool:
    salt_hex, dk_hex = stored.split(":")
    dk = hashlib.pbkdf2_hmac("sha256", plaintext.encode(), bytes.fromhex(salt_hex), 100_000)
    return hmac.compare_digest(dk.hex(), dk_hex)

def create_session_token(user_id: str, secret: str) -> str:
    """HMAC-SHA256 signed user_id, same pattern as onboarding tokens."""
    sig = hmac.new(secret.encode(), user_id.encode(), hashlib.sha256).hexdigest()
    return user_id + "." + sig

def verify_session_token(token: str, secret: str) -> str | None:
    """Return user_id if valid, None if tampered."""
    try:
        user_id, sig = token.split(".", 1)
    except ValueError:
        return None
    expected = hmac.new(secret.encode(), user_id.encode(), hashlib.sha256).hexdigest()
    if hmac.compare_digest(sig, expected):
        return user_id
    return None
```

`APPLYCLING_SESSION_SECRET` env var provides the signing key. Generate with `openssl rand -hex 32`.

### T3. Login page + endpoint

`GET /login` — styled login form. Single email + password fields, error state, redirect to job board on success. Reuses existing onboarding CSS variables (card, button, input styles).

`POST /login`:
1. Look up user by email in `users` table → reject if not found or `password_hash IS NULL`.
2. `verify_password(candidate, stored_hash)` → reject on mismatch.
3. `create_session_token(user_id, secret)` → set `applycling_session` cookie (HttpOnly, Secure, SameSite=Lax, path=/).
4. Redirect to `/`.

Unauthenticated users hitting any protected route get redirected to `/login` with a `?next=` param.

### T4. Session middleware

Replace `BasicAuthMiddleware` with `SessionMiddleware` (`applycling/ui/middleware.py`):

- Skip auth for `_UNAUTH_ROUTES`: `/healthz`, `/api/intake`, `/api/forward`, `/login`, `/static/*`, `/onboarding/submit-resume`.
- Extract `applycling_session` cookie → `verify_session_token()`.
- Valid → inject `request.state.user_id`, continue.
- Invalid/missing → redirect to `/login?next=<original_path>`.
- `APPLYCLING_NO_AUTH=true` bypasses everything (local dev).

The old `BasicAuthMiddleware` and `APPLYCLING_UI_AUTH_USER`/`APPLYCLING_UI_AUTH_PASSWORD` env vars are removed. Admin access is via user_id, not a shared password.

### T5. Scope all web routes to user_id

Every route reads `request.state.user_id` instead of using a shared default context:

- `/` job board: `jobs_service.list_jobs(user_id=request.state.user_id)`
- `/jobs/{id}` detail: verify `job.user_id == request.state.user_id` → 403 on mismatch
- `/jobs/{id}/artifacts/*`: verify ownership
- `/jobs/{id}/regenerate`: verify ownership
- `/onboarding/confirm`: session already scoped via user_id from token
- `/onboarding/submit-resume`: creates user row + sets session cookie automatically for the new user
- Submit new job: `PipelineContext.from_user_id(request.state.user_id, url)`

Telegram intake (`/api/forward`, `/api/intake`) is unchanged — it resolves by `telegram_id` and doesn't use sessions.

### T6. Admin invite flow

`POST /admin/invite` — gated to `APPLYCLING_ADMIN_USER_ID`:
1. Create user row with `email`, `password_hash`, `onboarding_state = 'active'`.
2. Return invite link: `https://app.applycling.com/login?email=...`.

Admin page at `/admin` shows user list + invite form. Gated by `request.state.user_id == APPLYCLING_ADMIN_USER_ID`.

First-alpha user flow: you invite manually via the admin page, they set a password on first login (optional: force password change via `password_change_required` flag).

### T7. Deployment

Add to `docker-compose.prod.yml`:

```yaml
services:
  applycling:
    environment:
      - APPLYCLING_SESSION_SECRET=${APPLYCLING_SESSION_SECRET}
```

Add to `/opt/applycling/.env` on the VPS:

```bash
APPLYCLING_SESSION_SECRET=<openssl rand -hex 32>
APPLYCLING_ADMIN_USER_ID=<your user UUID>
```

Remove `APPLYCLING_UI_AUTH_USER` and `APPLYCLING_UI_AUTH_PASSWORD` from env.

Run `alembic upgrade head` to apply the password_hash migration.

## Implementation Order

```
T1 → T2 → T3 → T4 → T6 → T5 → T7
```

- T1+T2: foundation, can land in one PR
- T3+T4: login flow + session enforcement, ships together
- T6: admin invite page so you can create alpha accounts
- T5: scope routes — last because routes are unusable until sessions exist
- T7: deploy

T5 is the largest but purely mechanical — every route gets the same `user_id` injection pattern.

## What This Doesn't Do

- No email verification, no password reset, no rate limiting on login
- No Google OAuth — that's post-alpha
- No Telegram account linking to web accounts — separate task
- No changing the Telegram intake path — it stays identity-via-telegram_id
- No multi-session management, no logout (cookie expiration handles it)

## Files Touched

```
migrations/versions/006_add_password_hash.py  — new
applycling/auth.py                             — new
applycling/ui/middleware.py                    — new
applycling/ui/routes.py                        — login routes + scope existing routes
applycling/ui/templates/login.html             — new
applycling/ui/__init__.py                      — swap middleware, update _UNAUTH_ROUTES
docker-compose.prod.yml                        — add env var
```

## Non-Goals

- OAuth / social login
- Email verification flows
- Password reset flow
- Role-based access (admin is just a user_id check)
- WebSocket or real-time session invalidation
