#!/bin/bash

# stop.sh — fires after each response
# Goal: remind agent to inspect diff and propose memory updates if significant

CHANGED_FILES=$(git diff --name-only 2>/dev/null)

if [ -n "$CHANGED_FILES" ]; then
  echo "Memory check — inspect diff and propose updates if significant:"
  echo "- working.md: update current state (no approval needed)"
  echo "- semantic.md / DECISIONS.md: PROPOSE first, write only on approval"
  echo "- If intent unclear from diff, ask before proposing"
fi
