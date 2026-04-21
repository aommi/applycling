#!/bin/bash
# stop.sh — fires after each response
# Goal: remind agent to inspect diff and propose memory updates if significant
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo .)"
CHANGED_FILES="$(git -C "$REPO_ROOT" diff HEAD --name-only 2>/dev/null || true)"

if [ -n "$CHANGED_FILES" ]; then
  echo "Memory check — inspect diff and propose updates if significant:"
  echo "- working.md: update current state (no approval needed)"
  echo "- semantic.md / DECISIONS.md: PROPOSE first, write only on approval"
  echo "- If intent unclear from diff, ask before proposing"
fi
