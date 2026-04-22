# Memory System

Persistent, file-based memory + Claude Code hooks. Long-form reference lives in `OPERATIONAL_MANUAL.md`; this file is the in-repo crib.

## Setup (first time)

1. Hooks are already registered in `.claude/settings.json` (`UserPromptSubmit` → `hooks/preprompt.txt`, `Stop` → `hooks/stop.sh`).
2. Ensure `hooks/stop.sh` is executable: `chmod +x hooks/stop.sh`.
3. Start a new Claude Code session in the repo. The preprompt text should appear before the first response; after any response with a non-empty `git diff HEAD`, the stop reminder should print.
4. To temporarily disable the hooks for debugging, rename `.claude/settings.json` to `.claude/settings.json.off` (or remove the `hooks` block).

## Daily use — 6 bullets

- **Session start:** agent reads `memory/semantic.md` once (via `CLAUDE.md`) and `memory/working.md` on your first message (via `hooks/preprompt.txt`). You do nothing.
- **During work:** agent prefers local files (`semantic.md`, `dev/[task]/context.md`) over MCP calls for project knowledge.
- **After each response:** `hooks/stop.sh` reminds the agent to inspect the diff and propose memory updates. `working.md` auto-updates; `semantic.md` and `DECISIONS.md` require your approval.
- **Task switch:** if your message doesn't match current `working.md` focus, the agent asks to archive current state into `dev/[task]/context.md` first.
- **Context drift:** if the agent's reasoning feels off, say "re-read semantic.md" — or the agent self-heals per the preprompt rule.
- **Session end:** no ceremony. Skim `working.md`; if stale, say "rewrite working.md from current state."

## Example workflow

```
Mon 9am  — "Add Stripe webhooks." → [plan mode → approve] → "Create dev/stripe-webhooks/ with plan/context/tasks and update working.md."
Mon 11am — [stop.sh fires after a code change] Agent: "Intent behind tokens.ts change isn't clear — refactor or bugfix?" You: "Security fix." Agent proposes semantic.md + DECISIONS.md entries. You approve.
Mon 3pm  — "Fix login timeout bug." Agent: "Different task — archive current state first?" You: "Yes." [agent archives working.md into stripe-webhooks/context.md, creates dev/login-timeout/, rewrites working.md]
Tue 9am  — [agent reads semantic.md + working.md] Agent: "You were on phase 2 of stripe-webhooks. Continue?" You: "Yes."
Tue 2pm  — "Done. Archive dev/stripe-webhooks/ to dev/archive/. Propose any final memory updates."
```
