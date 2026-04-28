# Working Memory — applycling

## Current Focus

Product direction discussion: next step after local Telegram validation. User confirmed Telegram loop works, but lack of visual job/apply status makes the tool feel like a one-off prompt rather than a default job-search workflow. User is weighing SQLite vs Postgres and wants to use limited discounted agent time on parallel/token-heavy work.

## In Progress

- Created `docs/planning/LOCAL_WORKBENCH_SPRINT.md` with local single-user workbench tickets and agent handoff prompts.
- User archived `docs/planning/SPRINT_1_LOCAL_TELEGRAM_VALIDATION.md` because the Telegram validation sprint is complete; rely on memory/semantic.md for retained Telegram context.
- Reviewed `docs/planning/STATUS_STATE_MACHINE_MANIFEST.md` and appended a Codex review. Main feedback: centralize UI action metadata in `applycling/statuses.py`, resolve the `new -> archived`/transition-count inconsistency, preserve `status_reason`, and handle the submit/run pipeline double-transition path.
- Re-reviewed the updated status manifest and appended "Codex Review — 2026-04-28" under `## Reviews`. Findings: transition-count inconsistency around `applied -> accepted`, missing migration for active workbench statuses, `archived` outcome collapse, missing `waiting -> offered`, DB CHECK means not truly one-file, and missing test/package scope.
- User reported Hermes revised final manifest to 11 states/23 transitions. Incremental review found remaining risks: `new` lacks a `generating` action despite retry flow depending on it, unconditional `archived -> reviewing` mishandles jobs archived from `new` or post-apply stages, and `status_reason=None` requires tracker/schema support not currently in plan.

## Blocked

(none)

## Next Steps

- Revised recommendation: prioritize a minimal local UI/workbench for job pipeline visibility. Either SQLite-first through TrackerStore or local Postgres without auth can work; avoid hosted/SaaS scope until the UI proves the workflow.
