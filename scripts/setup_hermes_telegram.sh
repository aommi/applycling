#!/usr/bin/env bash
# setup_hermes_telegram.sh — Provision the Hermes applycling Telegram gateway profile.
#
# Idempotent. Run from the applycling repo root.
# Requires: hermes CLI on PATH, data/telegram.json exists.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== applycling Hermes Telegram Gateway Setup ==="

# ── Prerequisites ────────────────────────────────────────────────────
if ! command -v hermes &>/dev/null; then
  echo "ERROR: hermes CLI not found. Install it first:"
  echo "  curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash"
  exit 1
fi

TELEGRAM_JSON="$REPO_ROOT/data/telegram.json"
if [ ! -f "$TELEGRAM_JSON" ]; then
  echo "ERROR: $TELEGRAM_JSON not found. Run: python3 -m applycling.cli telegram setup"
  exit 1
fi

# Extract values from applycling's telegram config
BOT_TOKEN=$(python3 -c "import json; print(json.load(open('$TELEGRAM_JSON'))['bot_token'])")
CHAT_ID=$(python3 -c "import json; print(json.load(open('$TELEGRAM_JSON'))['chat_id'])")

echo "Bot token:  (${#BOT_TOKEN} chars, not shown)"
echo "Chat ID:    $CHAT_ID"

# ── Create profile (idempotent) ─────────────────────────────────────
PROFILE="applycling"
if hermes profile list 2>/dev/null | grep -qE "(^|[[:space:]])$PROFILE($|[[:space:]])"; then
  echo "Profile '$PROFILE' already exists — skipping creation."
else
  echo "Creating Hermes profile '$PROFILE'..."
  hermes profile create "$PROFILE"
fi

# Resolve a dedicated wrapper alias. `hermes --profile applycling` may work on
# some installs, but the wrapper is shorter and avoids profile-mixup bugs.
HERMES_ALIAS="applycling-hermes"
HERMES_WRAPPER="$HOME/.local/bin/$HERMES_ALIAS"
if [ ! -x "$HERMES_WRAPPER" ]; then
  echo "Creating Hermes wrapper alias '$HERMES_ALIAS'..."
  hermes profile alias "$PROFILE" --name "$HERMES_ALIAS"
fi
if [ ! -x "$HERMES_WRAPPER" ]; then
  echo "ERROR: expected Hermes wrapper at $HERMES_WRAPPER"
  echo "Try running: hermes profile alias $PROFILE --name $HERMES_ALIAS"
  exit 1
fi

echo "Using: $HERMES_WRAPPER"

# ── Configure Telegram platform ──────────────────────────────────────
echo "Configuring Telegram platform..."
"$HERMES_WRAPPER" config set gateway.platforms.telegram.enabled true

# Write .env with Telegram secrets (only if missing or changed)
ENV_FILE="$HOME/.hermes/profiles/$PROFILE/.env"
NEEDS_ENV=false
if [ ! -f "$ENV_FILE" ]; then
  NEEDS_ENV=true
else
  CURRENT_TOKEN=$(grep TELEGRAM_BOT_TOKEN "$ENV_FILE" 2>/dev/null | cut -d= -f2 || true)
  if [ "$CURRENT_TOKEN" != "$BOT_TOKEN" ]; then
    NEEDS_ENV=true
  fi
fi

if $NEEDS_ENV; then
  echo "Writing $ENV_FILE..."
  cat > "$ENV_FILE" <<EOF
TELEGRAM_BOT_TOKEN=$BOT_TOKEN
TELEGRAM_ALLOWED_USERS=$CHAT_ID
EOF
  chmod 600 "$ENV_FILE"
else
  echo ".env already up to date — skipping."
fi

# ── Set model / provider (idempotent) ────────────────────────────────
echo "Configuring model..."
"$HERMES_WRAPPER" config set model.default deepseek-v4-pro
"$HERMES_WRAPPER" config set model.provider deepseek

# ── Copy parent env keys (API keys, etc.) ────────────────────────────
PARENT_ENV="$HOME/.hermes/.env"
if [ -f "$PARENT_ENV" ] && [ -f "$ENV_FILE" ]; then
  echo "Merging missing keys from parent .env..."
  python3 -c "
import os
env_file = os.path.expanduser('$ENV_FILE')
parent = os.path.expanduser('$PARENT_ENV')
target = {}
with open(env_file) as f:
    for line in f:
        line = line.strip()
        if line and '=' in line:
            k, v = line.split('=', 1)
            target[k] = v
with open(parent) as f:
    for line in f:
        line = line.strip()
        if line and '=' in line:
            k, v = line.split('=', 1)
            if k not in target:
                target[k] = v
                print(f'  + {k}')
with open(env_file, 'w') as f:
    for k, v in target.items():
        f.write(f'{k}={v}\n')
import os as _os
_os.chmod(env_file, 0o600)
"
fi

# ── Validate provider key exists ──────────────────────────────────────
PROVIDER=$("$HERMES_WRAPPER" config 2>/dev/null | grep -A1 'model:' | grep 'provider:' | awk '{print $2}' || echo "deepseek")
PROVIDER_KEY="$(echo "$PROVIDER" | tr '[:lower:]' '[:upper:]')_API_KEY"
if ! grep -q "^${PROVIDER_KEY}=" "$ENV_FILE" 2>/dev/null; then
  echo "WARNING: Provider '$PROVIDER' is configured but $PROVIDER_KEY is not set in $ENV_FILE"
  echo "  The gateway will fail on first message. Add it or switch providers."
fi

# ── Write SOUL.md ────────────────────────────────────────────────────
SOUL_FILE="$HOME/.hermes/profiles/$PROFILE/SOUL.md"
echo "Writing SOUL.md..."
cat > "$SOUL_FILE" <<'SOUL_EOF'
You are the applycling bot. Your only job: when you receive a message containing a job posting URL, run the applycling pipeline and the results will be delivered automatically.

When you see a job URL (something starting with https:// that looks like a job posting), do exactly this:

1. Run the pipeline:
   cd ~/Documents/dev/applycling && .venv/bin/python -m applycling.cli telegram _run <URL>

2. The applycling pipeline sends its own progress messages and PDFs to the user via Telegram. You don't need to report results — the pipeline's outbound notifier handles all delivery.

3. If the pipeline fails, you'll see the error in the terminal output. Report the failure to the user.

For any message that does NOT contain a job URL, reply with:
"Send me a job posting URL and I'll generate your application package — tailored resume, cover letter, and more."

Do not chat, do not make small talk, do not offer help with anything else. You are a single-purpose bot for job application generation.
SOUL_EOF

# ── Restrict toolsets to terminal only ────────────────────────────────
echo "Locking down toolsets (terminal only)..."
"$HERMES_WRAPPER" tools enable terminal
for ts in web browser vision file code_execution image_gen skills memory delegation cronjob clarify messaging session_search todo; do
  "$HERMES_WRAPPER" tools disable "$ts" 2>/dev/null || true
done

# ── Install and start gateway service ────────────────────────────────
echo "Installing gateway service..."
"$HERMES_WRAPPER" gateway install

echo ""
echo "=== Done ==="
echo ""
echo "Both gateways are running:"
hermes profile list
echo ""
echo "Test it: send a job URL to your applycling bot on Telegram."
echo "View logs: tail -f ~/.hermes/profiles/applycling/logs/gateway.log"
echo "Gateway status: $HERMES_WRAPPER gateway status"
