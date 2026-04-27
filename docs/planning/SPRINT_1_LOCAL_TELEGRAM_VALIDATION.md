# applycling — Sprint 1: Local Telegram Validation

**Status:** Ready for implementation  
**Date:** 2026-04-27  
**Primary design reference:** `docs/planning/DB_TECH_DESIGN.md`  
**Parent roadmap:** `docs/planning/SPRINT_PERSONAL_USE_V2.md`

---

## Sprint Goal

Prove the local Telegram path end-to-end:

```text
Hermes Telegram gateway/profile receives job URL
  -> user sends job URL to Telegram bot
  -> Hermes invokes applycling telegram _run <job_url>
  -> applycling worker starts
  -> pipeline runs locally
  -> package is generated under output/
  -> progress updates arrive in Telegram
  -> resume.pdf and cover_letter.pdf arrive in Telegram
```

This sprint is validation-only. It should make the current local personal workflow reliable enough to use, without pulling in Docker, Postgres, hosted persistence, Notion, rate limits, or SaaS infrastructure.

---

## Why This Sprint Exists

The highest-risk user loop is not the database yet. It is whether a real job URL sent through the Telegram path produces a useful package and delivers PDFs back to the user with understandable progress/failure messages.

Scope 1 validates that loop before investing in hosted persistence.

---

## Current Architecture Context

Already built:

- `applycling/pipeline.py`
  - `run_add()`
  - `run_add_notify()`
  - `persist_add_result()`
  - `PipelineContext`
  - `AddResult`
- Telegram CLI path:
  - `applycling telegram setup`
  - `applycling telegram add <url>`
  - `applycling telegram _run <url>`
- Hermes gateway/profile path:
  - Hermes owns inbound Telegram polling/routing/session handling.
  - applycling remains the pipeline/outbound delivery tool Hermes invokes.
- `applycling/telegram_notify.py`
  - sends Telegram messages and documents
- local persistence:
  - SQLite tracker
  - local `data/`
  - local `output/`
- package rendering:
  - markdown/html/pdf artifacts

Do not rebuild these systems. Exercise them, find gaps, and patch only what blocks local Telegram validation.

---

## Explicit Non-Goals

Do not implement:

- Docker or Docker Compose
- Postgres
- Alembic
- `APPLYCLING_DB_BACKEND`
- `PostgresStore`
- `users`, `user_contexts`, `jobs`, or `pipeline_runs`
- hosted user context storage
- tenant isolation
- active-run guard
- rate limits
- user blocking
- `ArtifactStore`
- object storage
- Notion schema migration or Notion completion requirements
- web dashboard
- `applycling answer`
- onboarding UI
- custom Telegram inbound polling/listener inside applycling

Notion must not be on the critical path for this sprint. If Notion happens to work locally, fine; if it fails, Telegram delivery should still be validated without it.

---

## Assumptions

- The user has already configured or can help configure Telegram credentials via `applycling telegram setup`.
- Hermes is available as the local Telegram gateway for this validation sprint.
- The user can provide a real job URL for end-to-end validation.
- The local environment has working model/provider credentials for the pipeline.
- Phase 1 persistence is disposable. SQLite rows and local package paths do not need to migrate to hosted Postgres later.
- Generated PDFs delivered in Telegram are the important user-facing output for this sprint.

If any credential or real-world input is missing, ask the user directly instead of mocking the full end-to-end test.

---

## Sprint Acceptance Criteria

- [ ] A real phone can trigger a real job URL by sending it to the Hermes Telegram bot/profile configured for applycling.
- [ ] Hermes invokes `applycling telegram _run <url>` or an equivalent terminal command without applycling owning inbound Telegram polling.
- [ ] `applycling telegram add <url>` remains available as a terminal fallback/manual smoke path.
- [ ] The background worker starts and logs to `output/telegram_worker.log`.
- [ ] Progress messages arrive in Telegram for meaningful pipeline steps.
- [ ] `resume.pdf` arrives in Telegram.
- [ ] `cover_letter.pdf` arrives in Telegram.
- [ ] A local package folder exists under `output/`.
- [ ] Failures are visible in either Telegram or worker logs.
- [ ] The completion message does not require a Notion link.
- [ ] Any remaining limitations are documented in this sprint file or a linked implementation note.

---

## Handoff Instructions For Agent

Start with Ticket 1. Do not edit unrelated persistence architecture. Do not start Scope 2 work early. Use Hermes for inbound Telegram intake; do not add or maintain a bespoke `applycling telegram listen` polling loop.

Before changing code:

1. Read this sprint file.
2. Read `docs/planning/DB_TECH_DESIGN.md` sections:
   - `1. Executive Decision`
   - `12. Phase Plan`
   - `18. Final Review Stamp`
   - Scope 1 under `18`
3. Inspect the current Telegram path:
   - `applycling/cli.py`
   - `applycling/pipeline.py`
   - `applycling/telegram_notify.py`
   - `applycling/storage.py`
4. Inspect or configure the Hermes applycling profile/gateway enough to route a Telegram job URL to the applycling terminal command.

When blocked by credentials, ask the user for help. The user is available to help with Telegram, model keys, real job URLs, and manual phone verification.

---

## Ticket 1 — Telegram E2E Smoke Harness

**Status:** Ready  
**Estimate:** 0.5 day  
**Type:** Discovery + narrow fixes only if trivial  
**Likely files:** `applycling/cli.py`, `applycling/pipeline.py`, `applycling/telegram_notify.py`, `output/telegram_worker.log`

### Goal

Run the existing Telegram path against a real job URL and produce a precise pass/fail report. The output of this ticket should make Ticket 2 unambiguous.

### Steps

1. Confirm Telegram config exists.

   ```bash
   applycling telegram setup
   ```

   If already configured, do not overwrite unless the user asks.

2. Start/configure the Hermes applycling profile or gateway.

   ```bash
   ./scripts/setup_hermes_telegram.sh
   applycling-hermes gateway status
   ```

   The setup script is idempotent and creates the `applycling-hermes` wrapper for the `~/.hermes/profiles/applycling/` profile. If the local Hermes command differs, record the exact command used in the smoke report.

3. Send a real public job URL to the Hermes Telegram bot/profile.

4. Watch the worker log.

   ```bash
   tail -f output/telegram_worker.log
   ```

5. Verify the run path:
   - Hermes receives the Telegram message.
   - Hermes invokes applycling for the URL.
   - Worker process starts.
   - Job URL scraping succeeds.
   - Pipeline begins.
   - Telegram status messages arrive.
   - Local package folder is created.
   - `resume.pdf` is generated.
   - `cover_letter.pdf` is generated.
   - Generated PDFs are below Telegram file limits.
   - PDFs are sent to Telegram.
   - Completion message arrives.

6. Record observed results in a short implementation note under this file or a nearby sprint log section.

### Pass/Fail Report Template

```markdown
## Ticket 1 Smoke Result

Date:
Job URL:
Command:

Result:
- Hermes profile/gateway running:
- Telegram URL received:
- applycling invoked:
- Worker spawned:
- Log path:
- Scrape:
- Pipeline:
- Status messages:
- resume.pdf generated:
- cover_letter.pdf generated:
- resume.pdf sent:
- cover_letter.pdf sent:
- Completion message:

Failures:
1.
2.

Notes:
```

### Acceptance

- A real run was attempted.
- Every failure is specific enough to fix without rediscovery.
- If the run passes completely, Ticket 2 becomes polish/contract cleanup rather than gap fixing.

### Ask User If

- Telegram bot token/chat ID is missing or invalid.
- A real job URL is needed.
- Model/provider credentials fail.
- Manual phone confirmation is needed.

---

## Ticket 2 — Telegram Gap Fixes + Completion Contract

**Status:** Ready after Ticket 1  
**Estimate:** 1 day  
**Depends on:** Ticket 1  
**Type:** Implementation  
**Likely files:** `applycling/pipeline.py`, `applycling/cli.py`, `applycling/telegram_notify.py`, maybe docs

### Goal

Make the local Telegram validation loop reliable enough for personal use:

```text
real phone -> real job URL -> progress messages -> PDFs delivered -> understandable completion/failure state
```

### Required Behavior

Progress messages should cover the meaningful stages already exposed by `run_add_notify()`:

- queued/starting
- scraping job description
- fetched job title/company
- role analysis / resume tailoring / profile summary / formatting / cover letter / email / fit summary, as available
- package assembly
- document delivery
- completion or failure

The completion message should include:

- job title and company
- job id
- local package path
- short fit summary or run summary when available
- a note that local artifacts are validation/private-use storage
- no required Notion link

Failure messages should be understandable for:

- Telegram config failure
- scrape failure
- LLM/provider failure
- package assembly/rendering failure
- PDF missing
- Telegram `sendDocument` failure

### Work

1. Fix failures found in Ticket 1.
2. Remove Notion expectations from the Telegram completion path for this sprint.
3. Ensure Telegram message text does not imply durable hosted storage.
4. Ensure PDF send failures do not silently disappear. The user should see a warning if a generated PDF could not be sent.
5. Ensure worker log remains useful for debugging.
6. Keep SQLite/local files as-is. Do not change tracker architecture except for narrow bug fixes required by the Telegram run.

### Acceptance

- Hermes-triggered `applycling telegram _run <real_job_url>` succeeds end-to-end on a real job.
- `applycling telegram add <real_job_url>` still succeeds as a terminal fallback/manual smoke path.
- Progress messages arrive in Telegram.
- `resume.pdf` and `cover_letter.pdf` arrive in Telegram.
- Local package folder exists.
- Completion message is accurate and does not require Notion.
- Known failure modes produce visible Telegram/log feedback.

### Regression Checks

Run the narrowest relevant checks after changes:

```bash
python3 -m pytest tests/test_telegram_notify_contract.py tests/test_regression_guard.py -q
```

If those tests are not applicable or fail due to unrelated existing issues, record exactly what was run and what failed.

Also run one real Hermes-triggered Telegram smoke after fixes. Hermes should invoke:

```bash
python3 -m applycling.cli telegram _run <real_job_url>
```

Use `applycling telegram add <real_job_url>` only as the terminal fallback/manual smoke path.

### Ask User If

- A user-facing message needs wording approval.
- A failure requires changing provider/model credentials.
- A real Telegram phone confirmation is needed.
- The implementation reveals a larger architecture issue that belongs to Scope 2 or Scope 3.

---

## Out Of Scope For Implementing Agent

If you encounter these, document them but do not implement them in this sprint:

- Need for Docker/Postgres
- Need for tenant isolation
- Need for hosted user profile storage
- Need for Notion sync
- Need for object storage
- Need for queueing/concurrency controls
- Need for web onboarding

These belong to later sprint docs.

---

## Final Sprint Exit

The sprint is done when:

1. Ticket 1 smoke report is complete.
2. Ticket 2 fixes are implemented.
3. A final real Telegram run succeeds or has only explicitly accepted limitations.
4. The user can send a job URL from their phone to the Hermes Telegram bot/profile and receive the generated PDFs in Telegram.

---

## Implementation Log

### 2026-04-27 — Phase 1 Start

Implemented narrow Telegram validation fixes before live smoke:

- `applycling telegram add` now waits briefly after spawning the detached worker and reports immediate startup failure instead of always printing `Queued`.
- `run_add_notify()` completion is local-validation oriented and no longer appends a Notion link.
- Telegram delivery now sends a "sending PDFs" status, warns when `resume.pdf` or `cover_letter.pdf` is missing, warns when a PDF exceeds Telegram's 50 MB document limit, and keeps long Telegram messages bounded with a pointer to the worker log/local package.
- Added `tests/test_telegram_notify_contract.py` to guard local-only completion text and missing-PDF warnings without requiring live Telegram credentials.

Checks run:

```bash
python3 -m pytest tests/test_telegram_notify_contract.py tests/test_regression_guard.py -q
```

Result: `10 passed`.

Live smoke status:

- `data/config.json`: present
- `data/resume.md`: present
- `data/telegram.json`: missing
- `python3 -m applycling.cli telegram add https://example.com/job`: correctly fails with `Telegram not configured. Run: applycling telegram setup`

Current blocker: run `applycling telegram setup` with real Telegram bot token/chat ID, then provide a real job URL and phone confirmation for the Ticket 1 end-to-end smoke.

### 2026-04-27 — Inbound Telegram Trigger Superseded By Hermes

User expectation clarified: sending a job URL to the Telegram bot itself must trigger the local pipeline. The earlier implementation only supported Telegram as an outbound notification channel plus CLI-triggered `telegram add`.

Initial implementation, now removed after Hermes architecture review:

- Added `TelegramNotifier.get_updates()` for Telegram long polling.
- Added `applycling telegram listen`, a local long-running listener. While it is running, messages from the configured chat are scanned for the first HTTP(S) URL and then handed to the same detached worker path used by `applycling telegram add`.
- Kept the implementation Phase 1/local-only: no webhook, hosted service, Docker, Postgres, or new persistence.
- Added URL extraction and polling wrapper regression coverage in `tests/test_telegram_listener_contract.py`.

Resolution:

- Use Hermes for inbound Telegram gateway duties during Phase 1 validation.
- Keep applycling responsible for `telegram _run`, `telegram add` fallback, pipeline execution, outbound progress messages, and PDF delivery.
- Remove/deprecate the custom listener/polling code path because it duplicates Hermes and does not survive the SaaS transition.

Historical checks that passed before the listener was removed:

```bash
python3 -m pytest tests/test_telegram_listener_contract.py tests/test_telegram_notify_contract.py tests/test_regression_guard.py -q
```

Result at the time: `12 passed`.

```bash
python3 -m applycling.cli telegram listen --help
```

Result at the time: command was available with `--interval`, `--model`, and `--provider`. This command has since been removed in favor of Hermes.

```bash
PYTHONPYCACHEPREFIX=/tmp/applycling_pycache python3 -m py_compile applycling/cli.py applycling/telegram_notify.py
```

Result: passed.

Full-suite note:

```bash
python3 -m pytest -q
```

Result: collection fails before Telegram tests on Python 3.9.6 due to existing `.agent/adapters/_mk.py` runtime use of `dict | None`.

### 2026-04-27 — Response To Hermes Inbound Review

Accepted DeepSeek/Hermes review direction.

Plan changes:

- Hermes profile/gateway is now the primary inbound Telegram trigger for Sprint 1.
- applycling will not own custom Telegram polling/listening in this sprint.
- `applycling telegram add <url>` remains a terminal fallback and smoke-test helper.
- `applycling telegram _run <url>` remains the command Hermes should invoke for the real phone-triggered path.

Code changes:

- Removed `applycling telegram listen`.
- Removed `TelegramNotifier.get_updates()` and `TelegramNotifier.poll()`.
- Removed `tests/test_telegram_listener_contract.py`.
- Kept `TelegramNotifier.notify()` and `send_document()`.
- Kept the Telegram worker startup health check.
- Kept `_clean_chat_id()` and password-masked bot token prompt.

Checks after removal:

```bash
python3 -m applycling.cli telegram --help
```

Result: only `add` and `setup` are exposed under `telegram`; no `listen` command.

```bash
python3 -m pytest tests/test_telegram_notify_contract.py tests/test_regression_guard.py -q
```

Result: `10 passed`.

```bash
PYTHONPYCACHEPREFIX=/tmp/applycling_pycache python3 -m py_compile applycling/cli.py applycling/telegram_notify.py
```

Result: passed.

Full-suite note remains unchanged:

```bash
python3 -m pytest -q
```

Result: collection fails before Telegram tests on Python 3.9.6 due to existing `.agent/adapters/_mk.py` runtime use of `dict | None`.

Hermes local command check:

```bash
hermes profile list
hermes profile create --help
hermes gateway --help
```

Result: Hermes is installed locally. At the time of this check, profiles showed only `default`; no `applycling` profile was present yet. The setup script now creates an `applycling-hermes` wrapper alias for profile-scoped commands; use that wrapper as the canonical path even if `hermes --profile applycling` also works locally.

### 2026-04-27 — Live Smoke (E2E Telegram Validation)

Full end-to-end test of the Hermes gateway → applycling pipeline loop:

- Sent a real public job URL to the applycling Telegram bot.
- Hermes received the URL, invoked `.venv/bin/python -m applycling.cli telegram _run <url>`.
- Progress messages arrived in Telegram: scraping, role analysis, resume tailoring, cover letter, fit summary, PDF delivery.
- `resume.pdf` and `cover_letter.pdf` delivered in Telegram.
- Local package folder created under `output/` (default: `/Users/amirali/Documents/ApplyCling-Output/`).
- Worker log at `output/telegram_worker.log` captured the full run.
- No errors in gateway log.

**Result: PASS.** Sprint 1 acceptance criteria met. The Hermes profile + applycling pipeline loop works end-to-end on a real job URL.

---

## Review (Hermes Agent)

**Reviewer:** deepseek-reasoner (via Hermes Agent)

**Date:** 2026-04-27

**Verdict:** Clean, well-scoped sprint plan. The non-goals list is thorough and correctly disciplined about not pulling in Scope 2/3 work prematurely. Below are observations and refinements.

### Observations

1. **Ticket 1 and Ticket 2 are better merged than split.**
   T1 is a 0.5-day smoke test that records failures. T2 fixes them. In practice, the same agent executes both sequentially (T2 depends on T1, and the sprint says "Start with Ticket 1"). Splitting discovery from remediation forces a handoff document (the pass/fail report) that the agent writes in T1 and re-consumes in T2. That handoff adds overhead without much value — the agent running T1 will see the failures immediately and could fix them without context-switching. Consider folding T1 into T2 as "step 0: run smoke test, document what breaks, fix, re-run." The split would make more sense if different engineers owned each ticket or if T1's outcome would change sprint priorities before T2 starts.

2. **The user is on the critical path for both tickets.**
   Both tickets have "Ask User If" sections for credentials, real job URLs, and phone confirmation. If the user is not immediately available during implementation, the sprint stalls completely. Consider providing fallback URLs (real public job postings that don't require auth) or suggesting a standby credential setup so the agent can validate as much of the pipeline as possible without blocking on the user.

3. **T1's 0.5-day estimate assumes a clean run or trivial fixes.**
   If the run fails on multiple failure modes (Telegram config, missing Playwright/Chromium, model provider errors, PDF generation), the discovery work exceeds 0.5 days. The estimate is reasonable for *running the test*, but the ticket says "narrow fixes only if trivial" — if a non-trivial gap is found during T1, the agent has to decide whether to stop, create a separate fix ticket, or push into T2's scope. The sprint could define what "trivial" means explicitly (e.g., "one-file change, no new dependencies, no prompt changes").

4. **The regression check in Ticket 2 references non-existent test files.**
   The command `python -m pytest tests/test_pipeline_contract.py tests/test_pipeline_library_api.py -q` points to files that do not exist in the repository (there is no `tests/` directory). The plan acknowledges this with "If those tests are not applicable or fail due to unrelated existing issues, record exactly what was run and what failed" — but in practice this means the regression check is a no-op. Consider either removing the test command reference (since the tests don't exist) or replacing it with a real existence check of the code paths changed (e.g., `python -c "from applycling.pipeline import run_add_notify; print('ok')"`).

5. **The background worker gives no startup feedback.**
   `applycling telegram add` spawns a detached subprocess (`start_new_session=True`) and returns immediately with "Queued. Processing in background." If the worker has a startup failure (bad import, missing dependency, missing config), the user sees "Queued" and then silence. The first indication of failure comes when they check the worker log or don't receive Telegram messages. Consider adding a brief synchronous health check: spawn the process, wait 1-2 seconds, check if it's still alive, and warn if it died immediately. The log path is printed, which helps, but the default experience should surface early death.

6. **The sprint has no automated regression tests.**
   All acceptance criteria are manual observations (phone trigger, Telegram messages, log inspection). This is reasonable for Phase 1 validation, but it means any subsequent code change breaks the Telegram path silently until someone re-runs the full end-to-end. Not a problem to solve now, but worth noting so the agent considers whether any of the Ticket 2 fixes are worth adding a small automated check for (e.g., a unit test for a new utility function).

7. **The "Already built" section is accurate but could add confidence notes.**
   After auditing the codebase:
   - `run_add()`, `run_add_notify()`, `persist_add_result()`, `PipelineContext`, `AddResult` — confirmed in `applycling/pipeline.py`
   - `telegram setup`, `telegram add`, `telegram _run` — confirmed in `applycling/cli.py` (lines 2250, 2276, 2316)
   - `TelegramNotifier` with `notify()` and `send_document()` — confirmed in `applycling/telegram_notify.py`
   - Worker log at `output/telegram_worker.log` — confirmed in `cli.py` lines 2300-2310
   - SQLite tracker, `data/`, `output/` — confirmed
   - markdown/HTML/PDF rendering — confirmed

   The pieces compose on paper. The sprint is designed to validate that they compose in practice. This is exactly the right scope for this sprint.

8. **Telegram file size limit is mentioned but has no mitigation plan.**
   T1 step 4 checks "Generated PDFs are below Telegram file limits." Telegram's `sendDocument` limit is 50MB, which most resume PDFs won't approach. But if a model generates an abnormally large PDF (image-heavy, oversized base64 embedded content), the sprint has no documented fallback — does it show a warning? truncate? Not critical, but a quick note in Ticket 2 about what to do if PDFs exceed the limit would prevent a stall in the final e2e run.

### Summary

| Severity | Issue | Notes |
|----------|-------|-------|
| Moderate | T1 + T2 better merged — handoff overhead for same agent executing both | Consider merging |
| Moderate | User is critical path for both tickets | Add fallback URLs or credential notes |
| Minor | T1 estimate assumes clean run | Define "trivial" boundary |
| Minor | Regression check references non-existent test files | Replace with real import check or remove |
| Minor | No startup health check for background worker | Add 2-second liveness probe after spawn |
| Minor | No automated regression tests (acceptable for Phase 1) | Add note if any Ticket 2 fix is unit-testable |
| Minor | No mitigation for oversized PDFs | Add quick note in Ticket 2 |

None are blocking. The sprint plan is execution-ready and correctly scoped to validating the Telegram loop without pulling in Phase 2/3 infrastructure.

---

## Review (Hermes Agent — Inbound Architecture)

**Reviewer:** deepseek-v4-pro (via Hermes Agent)

**Date:** 2026-04-27

**Verdict:** The inbound Telegram trigger works, but the custom polling/listener is reinventing what Hermes already provides. The long-term path is `Hermes Gateway (Telegram) → applycling pipeline`, not a bespoke polling loop inside applycling.

### Observation: Hermes Already Solves This

Hermes ships with a mature Telegram gateway (`hermes gateway setup` → Telegram) that handles polling, multi-chat routing, DM pairing, slash commands, approval flows, and error recovery. It uses the same `getUpdates` long-poll mechanism but wraps it in a production-grade listener with session management, multi-user isolation, and platform parity (Discord, Slack, WhatsApp, etc. all work the same way).

The `applycling telegram listen` command and the `TelegramNotifier.get_updates()`/`poll()` methods replicate a subset of that surface with none of the hardening. Specifically, the custom implementation:

- Only serves one chat (the configured `chat_id`). Hermes handles any chat that messages the bot.
- Has no DM pairing or auth — anyone who gets the bot token can trigger jobs.
- Has no error recovery beyond `try/except TelegramError → updates = []`.
- Blocks the terminal. Hermes runs as a background service (`hermes gateway install`).
- Has no session management, `/help`, or platform parity.

These are all solved problems in Hermes's gateway layer. The sprint shouldn't re-solve them.

### Recommendation: Hermes Profile Instead of Custom Listener

**Personal/validation phase (now):**

```
hermes --profile applycling    # isolated Telegram bot, skills, memory
```

The user messages their Hermes bot on Telegram with a job URL. Hermes receives it, runs applycling via terminal (`cd applycling && .venv/bin/python -m applycling.cli telegram _run <url>`), and the outbound `TelegramNotifier` delivers progress + PDFs to the same chat. No custom polling code needed.

Key advantages:
- Hermes profiles keep the applycling bot completely isolated from other Hermes bots (different token, different config, different skills/memory). Adding a second use case later costs nothing.
- Hermes already handles `getUpdates` polling, offset tracking, chat routing, and error recovery. Deleting the custom `poll()`/`get_updates()`/`telegram listen` removes ~90 lines of untested networking code.
- The `TelegramNotifier.notify()` and `send_document()` methods remain useful — they're the outbound channel regardless of who triggers the pipeline.

**SaaS phase (Phase 3+):**

When applycling needs multi-tenancy, queues, and hosted persistence, it outgrows the Hermes profile. At that point it gets its own gateway infrastructure (webhooks, not polling; dedicated worker pool; tenant isolation). The Hermes profile was never the SaaS path — it was the validation vehicle. This is the right separation: Hermes carries the personal phase, applycling stands on its own at SaaS scale.

### What Should Stay vs. Go

| Code | Fate | Rationale |
|------|------|-----------|
| `TelegramNotifier.notify()` | **Keep** | Genuinely useful — outbound channel works regardless of trigger source |
| `TelegramNotifier.send_document()` | **Keep** | Same — PDF delivery is the core value prop |
| `TelegramNotifier.get_updates()` | **Remove or deprecate** | Redundant with Hermes gateway; untested networking code |
| `TelegramNotifier.poll()` | **Remove or deprecate** | Same; the polling loop is Hermes's job |
| `applycling telegram listen` | **Remove or deprecate** | Replaced by `hermes --profile applycling` + terminal invocation |
| `tests/test_telegram_listener_contract.py` | **Remove with listener** | Tests code that shouldn't exist |
| `_clean_chat_id()` in cli.py | **Keep** | Guards against copy-paste artifacts during setup — useful regardless |
| `password=True` on bot token prompt | **Keep** | Security hygiene — applies to setup, not the listener |

### On the Fallback Question

> "I'm also unsure if the current polling that we re-invented actually works or even useful if someone doesn't want Hermes."

It works — `get_updates` is literally the Telegram Bot API. But "useful if someone doesn't want Hermes" is a thin slice. A user who doesn't want Hermes but wants a Telegram bot that runs applycling needs: polling, error recovery, process supervision, auth, and multi-chat support. They'd be building 80% of a gateway anyway. The custom listener doesn't save them from that — it just defers the pain to the first production incident.

The right answer for "no Hermes" users isn't a polling loop in applycling. It's either:
- A one-liner cron job: `*/2 * * * * cd applycling && .venv/bin/python -m applycling.cli telegram check` (if we want a minimal poller)
- Or accepting that Telegram intake requires *some* gateway, and Hermes is the lightest one available today

The custom listener is a net negative for maintainability: 90 lines of networking code with zero integration tests against the live Telegram API, no multi-chat support, no error recovery, and a known replacement path (Hermes profile) that handles all of it for free.

### Summary

| Severity | Issue | Notes |
|----------|-------|-------|
| High | Custom polling/listener reinvents Hermes gateway | Remove in favor of `hermes --profile applycling` |
| Minor | Outbound `TelegramNotifier` is preserved and still valuable | `notify()` + `send_document()` stay |
| Minor | Chat ID guard and password prompt are worth keeping | `_clean_chat_id` + `password=True` are standalone fixes |
| Minor | Custom listener is throwaway code either way | Doesn't survive SaaS transition; Hermes profile path does |

---

## Review (Codex — Hermes Docs Consistency)

**Reviewer:** Codex

**Date:** 2026-04-27

**Scope:** Documentation and setup-script consistency only. Code behavior review is intentionally deferred.

**Verdict:** Architecture direction is now consistent: Hermes owns inbound Telegram intake and applycling owns generation plus outbound Telegram delivery. I found and fixed several documentation/script mismatches around the Hermes profile command shape.

### Findings And Fixes

1. **Prefer wrapper over raw profile flag.**
   - Finding: `README.md`, `AGENTS.md`, `DECISIONS.md`, and `memory/semantic.md` referenced `hermes --profile applycling`. That flag may be valid locally, but the generated wrapper is shorter and harder to misuse.
   - Fix: standardized repo docs on the preferred `applycling-hermes` wrapper for `~/.hermes/profiles/applycling/`.

2. **Setup script fallback bypassed the preferred wrapper.**
   - Finding: `scripts/setup_hermes_telegram.sh` fell back to `hermes --profile applycling` if the default wrapper did not exist.
   - Fix: script now creates/uses a dedicated `applycling-hermes` alias via `hermes profile alias applycling --name applycling-hermes`, and errors clearly if that wrapper is unavailable.

3. **Setup instructions bypassed the provisioning script.**
   - Finding: sprint docs and parent sprint plan told agents to manually run `hermes profile create/use` and `hermes gateway setup/run`, while README said to use `scripts/setup_hermes_telegram.sh`.
   - Fix: sprint docs now use `./scripts/setup_hermes_telegram.sh` followed by `applycling-hermes gateway status`.

4. **API-key placement language was contradictory.**
   - Finding: `AGENTS.md` still said all API keys live in repo-root `.env`, which conflicts with the Hermes profile `.env`.
   - Fix: clarified that applycling pipeline keys live in repo `.env`, while Hermes gateway keys live in `~/.hermes/profiles/applycling/.env`.

5. **DECISIONS formatting had a wrong heading.**
   - Finding: the Hermes gateway decision was under a duplicate/wrong `2026-04-23 — Skill Template Engine` heading.
   - Fix: corrected the heading to `2026-04-27 — Hermes Gateway For Telegram Intake` and aligned its command references with `applycling-hermes`.

6. **Removed-listener references remain only as historical context.**
   - Finding: `telegram listen`, `get_updates`, `poll`, and `test_telegram_listener_contract.py` still appear in this sprint file.
   - Status: acceptable. Those occurrences are in implementation history and pasted DeepSeek review text that explicitly describe the removed listener and its removal. Canonical instructions no longer tell agents to use or maintain that path.

7. **Bare `applycling` Hermes alias may coexist with project CLI name.**
   - Finding: `hermes profile create applycling` can create a bare `~/.local/bin/applycling` wrapper that points to the Hermes profile, while this project also has an applycling CLI.
   - Status: acceptable but worth avoiding in docs. Canonical docs use `python3 -m applycling.cli ...` for the project CLI and `applycling-hermes ...` for the Hermes profile.

### Files Updated

- `README.md`
- `AGENTS.md`
- `DECISIONS.md`
- `memory/semantic.md`
- `docs/planning/SPRINT_1_LOCAL_TELEGRAM_VALIDATION.md`
- `docs/planning/SPRINT_PERSONAL_USE_V2.md`
- `scripts/setup_hermes_telegram.sh`

### Checks

```bash
bash -n scripts/setup_hermes_telegram.sh
```

Result: passed.

```bash
rg -n "hermes --profile|telegram listen|get_updates|poll\\(|test_telegram_listener|All API keys live|no file access" README.md AGENTS.md DECISIONS.md memory/semantic.md .env.example docs/planning/SPRINT_1_LOCAL_TELEGRAM_VALIDATION.md docs/planning/SPRINT_PERSONAL_USE_V2.md scripts/setup_hermes_telegram.sh
```

Result: only expected historical-review/log references remain for removed listener terms; canonical command references now use `applycling-hermes`.

### Remaining Verification For Next Agent

- Run `./scripts/setup_hermes_telegram.sh` on the real machine state.
- Confirm `applycling-hermes gateway status` works.
- Confirm `~/.hermes/profiles/applycling/.env` contains `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USERS`, and the routing provider key.
- Send a real job URL to the applycling Telegram bot and verify Hermes invokes `.venv/bin/python -m applycling.cli telegram _run <url>`.
