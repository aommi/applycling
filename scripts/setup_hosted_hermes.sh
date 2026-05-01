#!/bin/bash
# Phase 2: Hosted Hermes — one-command setup
# Run on the VPS after applycling is deployed.
#
# Prerequisites (one-time):
#   Add these to /opt/applycling/.env on the VPS:
#     TELEGRAM_BOT_TOKEN=<from laptop: grep TELEGRAM_BOT_TOKEN ~/.hermes/profiles/applycling/.env>
#     TELEGRAM_ALLOWED_USERS=26605267
#     DEEPSEEK_API_KEY=<from laptop: grep DEEPSEEK_API_KEY ~/.hermes/.env>
#
# Then run: bash scripts/setup_hosted_hermes.sh

set -e

HERMES_PROFILE="$HOME/.hermes/profiles/applycling"
APPLYCLING_ENV="/opt/applycling/.env"

echo "=== Hosted Hermes setup ==="

if [ ! -f "$APPLYCLING_ENV" ]; then
    echo "ERROR: $APPLYCLING_ENV not found. Deploy applycling first."
    exit 1
fi

# Check required vars
for var in TELEGRAM_BOT_TOKEN DEEPSEEK_API_KEY APPLYCLING_INTAKE_SECRET; do
    if ! grep -q "^${var}=" "$APPLYCLING_ENV"; then
        echo "ERROR: ${var} not in $APPLYCLING_ENV"
        echo "Add it from your laptop:"
        echo "  grep ${var} ~/.hermes/profiles/applycling/.env   # or ~/.hermes/.env"
        exit 1
    fi
done

echo "All required secrets found in $APPLYCLING_ENV"

# Source secrets
source <(grep -E '^(APPLYCLING_INTAKE_SECRET|TELEGRAM_BOT_TOKEN|DEEPSEEK_API_KEY|TELEGRAM_ALLOWED_USERS)=' "$APPLYCLING_ENV")

# Create profile
mkdir -p "$HERMES_PROFILE/sessions"

# .env
cat > "$HERMES_PROFILE/.env" << EOF
TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
TELEGRAM_ALLOWED_USERS=${TELEGRAM_ALLOWED_USERS:-26605267}
DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}
APPLYCLING_INTAKE_URL=http://127.0.0.1:8080/api/intake
APPLYCLING_INTAKE_SECRET=${APPLYCLING_INTAKE_SECRET}
HERMES_GATEWAY_TOKEN=$(openssl rand -hex 16)
EOF

# config.yaml
cat > "$HERMES_PROFILE/config.yaml" << 'YAML'
model:
  default: deepseek-chat
  provider: deepseek
toolsets:
  - hermes-cli
agent:
  max_turns: 90
YAML

# SOUL.md
cp /opt/applycling/app/docs/deploy/hermes_forwarding_template.md "$HERMES_PROFILE/SOUL.md"

# Install and start
hermes --profile applycling gateway install --force
hermes --profile applycling gateway start

echo ""
echo "=== Done ==="
echo "Now on your laptop: launchctl bootout gui/\$(id -u)/ai.hermes.gateway-applycling"
