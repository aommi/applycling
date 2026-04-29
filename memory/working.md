# Working Memory — applycling

## Current Focus

Reviewed and patched `docs/planning/HOST_DOGFOODING_EXECUTION_PLAN.md` V3.9 against `docs/planning/HOST_DOGFOODING_SPRINT.md`; current plan targets Kamatera VPS + Docker Compose + Caddy.

P2 cleanup committed on main at `bf3b1be`; 187 tests pass. Completed items listed by user: #2 test isolation, #4 env.py URL normalization, #5 migration downgrade CASCADE, #6 docker-compose tty flag removal, #11 status drift guardrail.

## In Progress

- Host dogfooding execution-plan review patches applied: deploy order now provisions `.env`/data first, waits for real Postgres readiness before migrations, documents root-owned artifacts, clarifies PR3 intake-secret startup validation, marks PR2 restart-sweep verification as post-PR3, makes H2 Hermes command a validation item, and incorporates Opus cleanup on conflict map, helper contract, secret separation/rotation, runbook caveats, and CLI smoke.
- Clarify P2 scoreboard mismatch: user reported `6/11 done, 5 deferred`, but the listed completed items are 5 and listed deferred items are 6.

## Blocked

(none)

## Next Steps

- Remaining P2 deferred items listed by user: #1 connection pooling, #3 Dockerfile `|| true`, #7 raw psycopg in test, #8 `PLAYWRIGHT_CHROMIUM_EXECUTABLE`, #9 alembic.ini creds, #10 `_COLUMNS` exclusions.
- MCP server — fully scoped plan at `docs/planning/MCP_SERVER_PLAN.md`
- Context-based resolvers (variant skills) — next vision capability
