# Working Memory — applycling

## Current Focus

Reviewing host dogfooding PR stack #26-#33 before merge. User wants step-by-step manual testing before each merge point.

## In Progress

- Preliminary PR review findings:
  - #26 deploy config likely needs Postgres password wiring fixed: `postgres` service does not read `/opt/applycling/.env`, while docs put `DATABASE_URL` there with `<POSTGRES_PASSWORD>`.
  - #28/#29 active-run + async race: UI/intake create a job and set `generating` before background `run_pipeline()` gets the atomic run; if `create_run()` loses the race, it returns an error without moving the job out of `generating`.
  - #28 startup sweep mismatch: comments/docs say startup marks all running rows failed, but implementation calls stale heartbeat sweep only, so a fresh crashed row can block until timeout.
  - #32 hosted Hermes profile mount is likely wrong: Dockerfile sets only `HOME=/hermes`, so Hermes default profile root is `/hermes/.hermes/profiles`, but compose mounts `/opt/applycling/hermes_profile` to `/hermes/profiles/applycling`.
  - #33/I1 smoke notes claim failure reason is visible in workbench, but current `job_detail.html` does not render stored status reasons.

## Blocked

(none)

## Next Steps

- Send review summary with merge/test recommendation.
- If user approves, post GitHub review comments or patch follow-up PRs.
