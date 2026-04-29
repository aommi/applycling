# Working Memory — applycling

## Current Focus

PR #20 (local web workbench + canonical state machine) merged into main. Workbench running at http://127.0.0.1:8080 with FastAPI + Jinja2. Postgres PR #21 pending merge.

## In Progress

- Memory system updates post-merge: semantic.md, DECISIONS.md, vision.md, project.yaml, sprint doc. Regenerating agent files after.
- Postgres branch (`feat/postgres-support`) has same code — merge when ready.

## Blocked

(none)

## Post-Merge Follow-ups (from Opus review, deferred)

- #5: Long pipeline blocks HTTP request — no progress/cancel, browser timeout possible. Fix: fire-and-forget + status polling.
- #6: `_INFER_KIND` references kinds not in `_ARTIFACT_KINDS` — widen or trim.
- #7: `failed → archived` transition missing — no clean exit for permanently broken jobs.
- Minor: duplicate `import json` in jobs_service.py, `reviewing → applied` skip, `_NullNotifier` to module scope, `archived → new` reachability comment.

## Next Steps

- Decide whether to merge Postgres PR #21 now or later.
- Address deferred follow-ups (tracked in docs/planning/LOCAL_WORKBENCH_SPRINT.md).
