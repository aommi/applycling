#!/usr/bin/env bash
set -euo pipefail

# ── applycling MCP Setup ──────────────────────────────────────────────
# One command: zero → MCP tools in Claude Desktop.
#
#   curl -sSL https://raw.githubusercontent.com/aommi/applycling/main/scripts/setup_mcp.sh | bash
#
# What this does:
#   1. Installs Python 3.12 (homebrew) if missing
#   2. Clones applycling
#   3. pip installs applycling + MCP deps into a venv
#   4. Writes Claude Desktop config (with PYTHONPATH fallback)
#   5. Runs applycling setup (profile, resume, LLM config)
# ──────────────────────────────────────────────────────────────────────

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}→${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC}  $*"; }
err()  { echo -e "${RED}✗${NC}  $*"; exit 1; }

# ── Step 1: Ensure Python 3.12 ────────────────────────────────────────
PYTHON=""
if command -v python3.12 &>/dev/null; then
    PYTHON="$(command -v python3.12)"
elif command -v /opt/homebrew/bin/python3.12 &>/dev/null; then
    PYTHON="/opt/homebrew/bin/python3.12"
elif command -v brew &>/dev/null; then
    log "Installing Python 3.12 via Homebrew..."
    brew install python@3.12
    PYTHON="$(command -v python3.12)"
else
    err "Python 3.12 required. Install from https://www.python.org/downloads/"
fi
log "Python: $PYTHON ($($PYTHON --version))"

# ── Step 2: Get the repo ──────────────────────────────────────────────
REPO_DIR="$HOME/applycling"
if [ -d "$REPO_DIR/.git" ]; then
    log "Updating existing repo at $REPO_DIR..."
    cd "$REPO_DIR" && git pull --ff-only
else
    log "Cloning applycling to $REPO_DIR..."
    git clone https://github.com/aommi/applycling.git "$REPO_DIR"
fi
cd "$REPO_DIR"

# ── Step 3: Create venv + install ─────────────────────────────────────
log "Installing applycling + MCP dependencies..."
"$PYTHON" -m venv .venv
.venv/bin/python3.12 -m pip install --quiet --upgrade pip
.venv/bin/python3.12 -m pip install --quiet -e ".[mcp]"

# Verify
.venv/bin/python3.12 -c "import applycling" 2>/dev/null || {
    warn "Editable import failed — will use PYTHONPATH fallback in Claude config."
}
log "Installation complete."

# ── Step 4: Write Claude Desktop config ───────────────────────────────
CLAUDE_CONFIG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
mkdir -p "$(dirname "$CLAUDE_CONFIG")"

# Merge into existing config, or create new one
python3.12 - "$CLAUDE_CONFIG" "$REPO_DIR" << 'PYEOF'
import json, sys, os
config_path = sys.argv[1]
repo_dir = sys.argv[2]
venv_python = os.path.join(repo_dir, ".venv/bin/python3.12")

config = {}
if os.path.exists(config_path):
    with open(config_path) as f:
        try: config = json.load(f)
        except json.JSONDecodeError: config = {}

config.setdefault("mcpServers", {})["applycling"] = {
    "command": venv_python,
    "args": ["-m", "applycling.cli", "mcp", "serve"],
    "env": {"PYTHONPATH": repo_dir},
    "cwd": repo_dir
}

with open(config_path, "w") as f:
    json.dump(config, f, indent=2)
    f.write("\n")
PYEOF

log "Claude Desktop config written to: $CLAUDE_CONFIG"

# ── Step 5: First-time setup ──────────────────────────────────────────
echo ""
log "Setting up your profile... (name, resume, LLM provider, API key)"
echo ""
.venv/bin/python3.12 -m applycling.cli setup

# ── Done ──────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}✓ applycling MCP is ready!${NC}"
echo ""
echo "  Restart Claude Desktop (Cmd+Q, reopen)"
echo "  Look for the 🔨 icon, then try:"
echo "    • Show my recent tracked job applications"
echo "    • Generate an application for https://..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
