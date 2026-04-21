# DECISIONS — applycling

Append-only architectural decisions log. To reverse a prior decision, append a new entry that explicitly supersedes it by date.

---

## 2026-04-21 — Memory System Implementation

**Decision:** Implement file-based memory system with hook enforcement per operational manual.

**Reasoning:**
- Solo developer workflow needs persistent context across sessions without token bloat
- Remote MCP calls for project knowledge are expensive and unnecessary — local markdown files are faster
- Hook-based enforcement ensures memory stays current without manual maintenance overhead
- Separation of concerns: `semantic.md` (long-lived knowledge, ≤500 tokens, approval-required updates), `working.md` (ephemeral state, ≤300 tokens, auto-updated), `DECISIONS.md` (append-only log)

**Impact:**
- CLAUDE.md updated with session-startup instruction to read `semantic.md`
- `hooks/preprompt.txt` injected before every user prompt — reads `working.md`, enforces "check local files before MCP" rule
- `hooks/stop.sh` fires after each response — inspects git diff, proposes memory updates for human approval
- `/dev/[task]/` structure for task-specific context (plan.md, context.md, tasks.md)
- Task-switching protocol: archive current `working.md` to `dev/[task]/context.md` before rewriting for new focus

**Rejected alternatives:**
- Notion-based memory (requires MCP call, slower than local file)
- Embedding-based retrieval (overkill for ≤500 token memory, adds infra dependency)
- No memory system (context lost every session, re-explanation tax)

**Affects:** CLAUDE.md, hooks/, memory/, dev/
