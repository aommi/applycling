# applycling — 2-Week Sprint Plan (OpenClaw-first)

> Build plan to make applycling work as a mobile-first personal job-application system, with architecture that extends cleanly to multi-user / SaaS later.
> Topology: **OpenClaw** (agent, multi-channel AI hub) invokes **applycling** (skill, deterministic pipeline of steps).

---

## Goal

End of sprint: from your phone, send a job URL to Telegram. OpenClaw queues it, runs the applycling skill, delivers the application package (PDFs + metadata) back to Telegram within ~10 min and updates a Notion row. Next morning you review, optionally refine via `applycling refine`, and apply.

```
Phone (anytime):    see job → forward URL to Telegram bot
                    → OpenClaw queues + triggers applycling skill (event-driven, not cron)
~10 min later:      PDFs delivered to Telegram, Notion row updated
Next morning:       review packages (PDFs on phone, or flat files on laptop)
                    → refine any that need adjustment (`applycling refine` or Telegram reply)
Applying:           paste form questions → `applycling answer` → copy/paste → submit
```

Flexible sprint end — quality of the shape beats hitting exactly 10 days.

---

## Terminology (precise — used consistently below)

- **Agent** = OpenClaw. Chooses tools, routes across channels, loops, replans.
- **Skill** = applycling. A deterministic composable pipeline the agent invokes.
- **Step** = a unit inside a skill's pipeline (scrape, role_intel, tailor, cover_letter, email, brief, ats, critique, package, ...).
- **Checkpoint** = a named decision gate inside a step where the caller may intervene (pick an angle, answer a gap question). Has a default resolver so the pipeline never blocks.

Reserving "agent" for orchestrators that replan prevents us from baking bad autonomy into steps later. Steps are deterministic; orchestrators are not.

---

## Bottlenecks this plan targets

1. **Mobile intake gap** — seeing jobs on phone with no way to act → OpenClaw's Telegram channel handles this.
2. **Form-filling time sink** — 15–30 min/app on short-answer questions → `applycling answer` handles this.
3. **Terminal dependency** — all daily flows move to Telegram + Notion + PDFs; terminal is power-user fallback.
4. **Extensibility drag** — current steps re-implement status/logging/token tracking individually → `PipelineStep` contract in Ticket 2 formalizes what every step shares.

Explicitly dropped from earlier drafts:
- `applycling score` (cheap model triage pre-gate). Not building.
- Notion artifact sync (stuffing resume/cover letter content into Notion blocks). Not building — artifacts stay as flat files; Notion stores only tracking metadata + paths.

---

## Current state (reference — do not re-derive)

Relevant existing code:
- `applycling/cli.py` — all commands, `_Step` context manager pattern (the seed of the new `PipelineStep` contract)
- `applycling/llm.py` — provider routing (ollama/anthropic/openai/google), `_stream_chat()`
- `applycling/skills/` — all prompt templates (individual SKILL.md files per step)
- `applycling/storage.py` — config/resume/profile/stories file storage, `save_config()` merges
- `applycling/tracker/` — `TrackerStore` abstraction (Notion + SQLite), `get_store()` auto-detects
- `applycling/notion_connect.py` — Notion setup wizard
- `applycling/package.py` — output folder assembly, `run_log.json`
- `applycling/render.py` — markdown → HTML → PDF (Playwright)

Existing data files in `data/`:
- `config.json`, `profile.json`, `resume.md`, `stories.md`, `notion.json`

Existing output structure per run in `output/{company}-{title}-{date}[-{model}]/`:
- `resume.md/.html/.pdf`, `cover_letter.md/.html/.pdf`
- `positioning_brief.md`, `strategy.md`, `email_inmail.md`
- `fit_summary.md`, `company_context.md`, `job.json`, `run_log.json`

Existing commands: `setup`, `add`, `refine`, `critique`, `prep`, `questions`, `notion connect`.

Patterns to reuse (non-negotiable — do not reinvent):
- **Step bookkeeping** — use `_Step` pattern for anything that calls an LLM (after Ticket 2 this becomes `PipelineStep`)
- **Cleaning output** — always apply `_clean_llm_output()` to LLM results
- **Multi-line paste input** — existing pattern uses `---` as terminator
- **Interactive refine loop** — `applycling refine` is the shape for iterate-with-feedback commands
- **Config merge** — `storage.save_config()` merges, never partial-overwrites

---

## Architecture

### Library-first: applycling is a callable skill

The critical shift: **applycling becomes a library**. CLI is a thin wrapper. OpenClaw (and future web UI, MCP tools, eval harness) call `applycling.pipeline` functions directly in Python.

Public entry points after refactor:

```python
# applycling/pipeline.py

def add(url, context, options=None, resolver=None, on_status=None) -> Package
def refine(job_id, artifact, feedback, context, options=None) -> Artifact
def answer_questions(job_id, questions, context, options=None) -> list[Answer]
```

- `context: UserContext` — profile, resume, stories, applicant_profile, config, tracker, paths. Threaded through every step. Multi-user later = swap the default file-backed context for a DB-backed one. No function signatures change.
- `resolver: CheckpointResolver` — resolves checkpoint decisions. Default is `AutoResolver` (picks top option, logs decision). CLI uses `InteractiveResolver` (prompts user). Future Telegram-HITL uses a `TelegramResolver`.
- `on_status: Callable` — emits named events ("step_started", "step_completed", "checkpoint_resolved"). CLI renders rich spinners; OpenClaw forwards to Telegram; tests ignore.

### The `PipelineStep` contract

Every step (today's and every future one) implements the same shape:

```python
class PipelineStep:
    name: str                         # "role_intel"
    output_file: str | None           # "role_intel.md"
    needs: tuple[str, ...]            # upstream steps it depends on
    checkpoint: CheckpointSpec | None # decision gate, if any

    def run(self, ctx: UserContext, inputs: StepInputs) -> StepResult:
        ...
```

`StepResult` carries: content, metadata (timing, tokens, cost, model, status), and optional `CheckpointRecord`.

**What the base class / framework handles automatically (never re-wired per step):**
- Status event emission (`on_status`).
- Token count + cost estimate (existing logic lifted from `_Step`).
- `run_log.json` entry.
- Output file write (if `output_file` is declared).
- `_clean_llm_output` applied to LLM results.
- Error handling (ok / skipped / failed).
- Checkpoint resolution via the resolver.

**Adding a new step later** (e.g., recruiter outreach generator, salary parser, interview probe):
1. Add the prompt as a new `SKILL.md` file under `applycling/skills/<step_name>/`.
2. Implement a `PipelineStep` subclass.
3. Register it in the relevant pipeline composition.

That's it. No wiring of status/logging/tokens/files — all inherited. Same shape as the existing `_Step` pattern, just extracted from `cli.py` into a proper, presentation-free library class.

### Checkpoints (how HITL works without blocking)

Today, `applycling add` pauses on two gates: angle confirmation and gap handling. After Ticket 2, these become **checkpoints** — named decision points the caller resolves via a `CheckpointResolver`.

Three resolver implementations:

| Resolver | Used by | Behavior |
|---|---|---|
| `InteractiveResolver` | CLI `applycling add` | Prompts user, blocks, uses answer |
| `AutoResolver` | OpenClaw (sprint default) | Picks top-ranked option, logs decision |
| `TelegramResolver` | OpenClaw (future) | Sends options to Telegram, waits for reply |

`AutoResolver` never blocks — package is always ready. Every decision is recorded to `output/<job>/checkpoints.md`:

```
## Angle
Chosen: Technical depth
Rationale: JD emphasizes distributed systems; your backend bullets score highest.
Alternatives: Product intuition (your PM-adjacent work), 0→1 builder (your startup stint).

## Gap: Kubernetes
Chosen: Transferable framing — emphasize Docker + AWS ECS.
Alternatives: Acknowledge + learning intent; lean away entirely.
```

Next-morning review flow:
1. Glance at `checkpoints.md` (or Telegram summary if OpenClaw sends one).
2. If an angle or gap-handling is wrong, re-run from that checkpoint:
   `applycling refine resume --checkpoint angle --override "product intuition"`
3. Only affected downstream steps re-run (resume, cover letter, email). Scrape/role-intel/company-context are cached.

This turns HITL from *blocking input* into *auditable decisions with targeted overrides*. Packages always ship; refinement is targeted, not regenerate-everything-with-different-vibes.

### Queue

`applycling/queue.py` — `QueueStore` interface mirroring `TrackerStore`:

```python
class QueueStore:
    def append(url, source) -> Job
    def claim() -> Job | None
    def complete(job_id, package_folder)
    def fail(job_id, error)
    def list_pending() -> list[Job]

class JSONLQueue(QueueStore):
    """Default: backed by data/queue.jsonl"""
```

A hidden `applycling process-queue` CLI command is included for end-to-end testing without OpenClaw. In normal operation OpenClaw's skill handler calls `queue.claim()` + `pipeline.add()` directly.

### What stays out of scope (from the technical review)

- **No self-scoring quality gates inside steps.** Self-evaluation is unreliable. Quality checks use `applycling critique` (existing judge-model pass) or deterministic checks (keyword overlap, regex for generic phrases).
- **No retrieval / vector store.** Direct context loading handles 5–20 artifacts per job fine. Revisit when there's an actual retrieval problem.
- **No auto-learned "recurring_gaps" / dynamic candidate model.** Profile/stories/applicant_profile are user-authored and user-editable. No system-inferred facts silently accumulate.
- **Steps don't replan.** Orchestrators (`pipeline.add()`, OpenClaw) own control flow. A step takes inputs and produces outputs — nothing more.

---

## Tickets

### Ticket 0 — Pre-sprint scoping + OpenClaw hello-world (½–1 day)

**Priority:** P0 (de-risks Ticket 2 and the OpenClaw integration)

**What to do:**
1. Read `cli.py add` end-to-end; map each phase into a candidate step, noting:
   - Inputs (what it reads from state or prior steps)
   - Outputs (what file/data it produces)
   - Whether it has an interactive gate (→ becomes a checkpoint)
   - Whether it's LLM-backed, scrape-backed, or pure transform
2. Sketch `UserContext`, `StepResult`, `CheckpointResolver`, `CheckpointSpec` dataclasses.
3. Write a hello-world OpenClaw skill on your local machine that echoes a Telegram message. Confirm:
   - How skills are registered.
   - Whether OpenClaw runs skills in-process or isolated (affects Playwright / subprocess design).
   - How long a skill can run (a 10-min pipeline needs either streaming status or a background-worker pattern).
4. Output: a short notes file (`SCOPING_NOTES.md`, gitignored or in a scratch folder) capturing these answers so Ticket 2 and the OpenClaw integration can proceed without guesswork.

**Acceptance:** you can state concretely (a) the list of steps and their checkpoints, (b) `UserContext` shape, (c) how the applycling skill will run inside OpenClaw.

---

### Ticket 1 — `applicant_profile.json` + setup wizard extension (½ day)

**Priority:** P1 (foundation — Ticket 3 depends on it)

**What to build:**
1. New file: `data/applicant_profile.json`
2. Extend `applycling setup` wizard to collect (pre-fill existing, skip if already set):
   - `work_auth` — e.g. "Canadian PR", "needs H1B"
   - `sponsorship_needed` — bool
   - `visa_status` — optional free-text
   - `relocation` — bool + preferred cities
   - `remote_preference` — "remote" / "hybrid" / "on-site" / "flexible"
   - `comp_expectation` — `{min, target, currency}`
   - `notice_period` — e.g. "2 weeks", "immediate"
   - `earliest_start_date` — optional
   - `demographics` — opt-in, for EEOC fields
3. Add `storage.load_applicant_profile()` / `save_applicant_profile()` with merge semantics matching `save_config`.
4. Update `CLAUDE.md` "Project structure" + "Config keys" sections.

**Acceptance:**
- Running `applycling setup` collects each field; re-runs pre-fill.
- File is gitignored.
- `.env.example` unchanged (only API keys/secrets belong there).

---

### Ticket 2 — Service layer refactor: skill pipeline + `PipelineStep` contract (~3 days)

**Priority:** P0 (keystone — everything downstream depends on it)

**What to build:**

1. **`applycling/pipeline.py`** — public skill API.
   - `UserContext` dataclass: `data_dir`, `output_dir`, `tracker`, `profile`, `applicant_profile`, `resume`, `stories`, `config`. Constructed once at entry, threaded through every step.
   - `PipelineStep` base class with the contract described in Architecture. Handles status emission, token/cost tracking, `run_log.json`, output-file writing, `_clean_llm_output`, error classification.
   - `CheckpointSpec` + `CheckpointRecord` + `CheckpointResolver` interface with `InteractiveResolver` and `AutoResolver` implementations.
   - Step implementations for the current pipeline: `ScrapeStep`, `RoleIntelStep`, `CompanyContextStep`, `AngleStep` (checkpoint), `GapStep` (checkpoint), `ResumeTailorStep`, `FormatResumeStep`, `CoverLetterStep`, `EmailInMailStep`, `PositioningBriefStep`, `ATSScoreStep`, `PackageStep`.
   - Public functions: `add`, `refine`, `answer_questions`. Each accepts `context`, `options`, `resolver`, `on_status`.

2. **`applycling/queue.py`** — `QueueStore` + `JSONLQueue`. `get_queue()` auto-detection following `get_store()` pattern.

3. **Refactor `cli.py`** — each command becomes a thin wrapper: build `UserContext`, pick `InteractiveResolver`, call `pipeline.func()`, format output. Add `--non-interactive` flag that swaps to `AutoResolver`. No behavior changes to end-user CLI.

4. **Hidden CLI for E2E testing without OpenClaw:** `applycling process-queue` — claims one pending job, runs `pipeline.add()`, completes. Internal tool, not in primary `--help`.

5. **Refactor regression guard.** Before starting, run `applycling add` on a pinned JD with a pinned config and snapshot the output folder. After refactor, re-run and validate:
   - All expected files exist.
   - Markdown files parse (no malformed frontmatter / broken lists).
   - Each expected section header appears.
   - `run_log.json` shape matches (same step names, all statuses "ok").
   Don't diff LLM content directly — non-determinism makes that useless. Validate structure.

6. **Refine with checkpoint override.** Extend `applycling refine` with `--checkpoint <name> --override <value>`. When present, re-runs only the steps downstream of that checkpoint, reusing cached upstream artifacts.

**Acceptance:**
- `from applycling import pipeline; pipeline.add(url, context, resolver=AutoResolver())` runs end-to-end, produces the full package, emits status events, writes `checkpoints.md`.
- All existing CLI commands still work identically in interactive mode.
- `applycling add --non-interactive` runs without prompts and writes `checkpoints.md`.
- `applycling process-queue` claims and processes queued jobs.
- `applycling refine resume --checkpoint angle --override "product intuition"` re-runs only resume / cover letter / email / brief.
- Regression guard: post-refactor structural validation matches pre-refactor snapshot.

---

### Ticket 3 — `applycling answer` (1 day)

**Priority:** P1 (form-filling time sink)
**Depends on:** Ticket 1 (applicant_profile), Ticket 2 (`pipeline.answer_questions`)

**What to build:**

1. `applycling/skills/answer_questions/SKILL.md` — the prompt template. Inputs: `{resume}`, `{stories}`, `{profile}`, `{applicant_profile}`, `{role_intel}`, `{company_context}`, `{positioning_brief}`, `{questions}`. Output: one markdown section per question.

2. `pipeline.answer_questions(job_id, questions, context, options)`:
   - Load all context from the job's package folder.
   - Parse pasted questions into a list.
   - Single LLM call (with `PipelineStep` bookkeeping).
   - Return list of answers keyed to questions.

3. CLI: `applycling answer <job_id>`:
   - Multi-line paste prompt (existing `---` terminator pattern).
   - Streams output.
   - Interactive refine loop (same shape as `applycling refine`): `[a]ccept`, `[e]dit in $EDITOR`, `[r]efine with feedback`, `[q]uit`.
   - Appends to `output/<job>/answers.md` (single file, sections per run with timestamp header; never overwrite prior).

**Acceptance:** pasted form questions produce drafted answers in <30s; refine loop works; answers are grounded in job context + applicant profile.

---

### Ticket 4 — OpenClaw applycling skill + Telegram flow (local POC) (~2 days)

**Priority:** P1 (the point of the sprint)
**Depends on:** Ticket 2, Ticket 3

**What to build:**

1. **Install OpenClaw locally** (Docker or native per their docs). Configure your Telegram bot token.

2. **applycling skill wrapper.** Thin Python module that exposes:
   - `apply(url)` → `queue.append(url, "telegram")` + trigger background `pipeline.add()` call. Returns immediately with "queued" ack.
   - `refine(job_id, artifact, feedback)` → calls `pipeline.refine()`.
   - `answer(job_id, questions)` → calls `pipeline.answer_questions()`.
   - `status(job_id)` → returns current state from queue + tracker.
   
   The wrapper passes an `on_status` callback that forwards events to OpenClaw → Telegram. Resolver is `AutoResolver` (ships `checkpoints.md` with the package).

3. **Background processing.** Exact mechanism decided in Ticket 0 based on OpenClaw capabilities. Three possibilities:
   - OpenClaw runs skills as long-lived tasks → skill simply calls `pipeline.add()` synchronously and emits status.
   - OpenClaw expects fast skill returns → skill spawns a worker (asyncio task, subprocess, or OpenClaw's native background-job primitive) and emits status via the callback.
   - Fallback: `applycling process-queue` runs as a separate systemd/launchd service; skill only appends to queue.
   
   Pick the cleanest option given what Ticket 0 discovered.

4. **Telegram UX:**
   - Send a URL → bot replies "✅ Queued. Processing..."
   - Status updates as skill emits them: "📄 Scraping JD...", "🎯 Analyzing role...", "✍️ Tailoring resume...", "📦 Assembling package..."
   - On completion: attach resume.pdf + cover_letter.pdf, include Notion row link, include 1-line checkpoints summary ("Angle: technical depth; Gap handled: kubernetes transferable framing").
   - On failure: short error + link to local log.

5. **Refine / answer via Telegram (stretch for this ticket; graceful if deferred):**
   - Reply to a package message with "refine resume: make it more technical" → triggers `skill.refine()`.
   - Reply with "answer: <questions>" → triggers `skill.answer()`, returns answers as a Telegram message.

**Acceptance:**
- From your phone, send a LinkedIn job URL to your Telegram bot.
- Receive status updates.
- Within ~10 min, receive PDFs + Notion link + checkpoint summary.
- Notion row reflects job + status + scores + local folder path.
- Package folder on your local machine contains the full artifact set + `checkpoints.md`.

---

### Ticket 5 — Notion metadata sync (1 day)

**Priority:** P2 (tracking UX)
**Depends on:** Ticket 2

**Scope correction:** Notion stores **metadata only**. No artifact content. Resume / cover letter / brief / email / fit-summary stay as flat files on disk. Mobile access to artifact content is via Telegram attachments (PDFs), not Notion toggles.

**What to build:**
1. Audit `applycling/tracker/notion_store.py`; document current fields.
2. Extend the Notion schema with:
   - `Match Score`, `ATS Score` (number)
   - `Status` (select: queued / processing / ready / applied / interview / offer / rejected / error)
   - `Generated At` (datetime)
   - `Local Folder` (url — `file://` link to the package folder)
   - `Checkpoints Summary` (rich_text — 1-line summary from `checkpoints.md`)
   - `Work Auth Fit`, `Comp Fit` (booleans derived from applicant_profile vs job metadata if available)
3. After `pipeline.add()` completes, call `tracker.sync_job(job, package_metadata)` — updates the row in place. No duplication on re-runs.

**Acceptance:** After `applycling add` (or a Telegram-triggered run), the Notion row shows all metadata fields populated. Clicking the local-folder link opens the package folder. Re-running updates in place.

---

## OpenClaw local POC (deployment notes)

Running OpenClaw locally for the sprint — no VPS work until the POC is proven.

1. Install OpenClaw per their docs (Docker recommended).
2. Clone applycling alongside, `pip install -e .`, run `applycling setup`.
3. Register the applycling skill in OpenClaw (exact mechanism discovered in Ticket 0).
4. Configure your Telegram bot token in OpenClaw.
5. Everything runs on your laptop; no data sync needed during POC.

Post-sprint, moving to a VPS becomes straightforward: same code, same skill, different host. Handle that when you're ready to keep the bot running 24/7.

---

## Daily workflow (after sprint completes)

### Setup (one-time)
- `applycling setup` — resume, profile, stories, applicant_profile.
- OpenClaw + Telegram bot running locally.

### During the day (phone)
1. See job on LinkedIn.
2. Forward URL to your applycling Telegram bot.
3. Bot replies: "✅ Queued. Processing..."
4. ~10 min later: bot sends resume.pdf + cover_letter.pdf + Notion link + checkpoint summary.

### Review (anywhere)
- Phone: skim the Telegram PDFs + checkpoint summary.
- Laptop: open the package folder for full artifacts (positioning brief, email draft, fit summary, etc.).
- Notion for filtering / status tracking.

### Refine (if needed)
- If an angle or gap handling is wrong:
  - Telegram: reply "refine resume: <feedback>" (if stretch shipped)
  - Laptop: `applycling refine resume --checkpoint angle --override "product intuition"`
- Only affected downstream artifacts re-run. Package updated in place.

### Apply (desktop)
1. Open the actual application form.
2. Copy resume text + cover letter from package folder (or attach PDFs).
3. For form questions: `applycling answer <job_id>`, paste questions, copy drafted answers, refine if needed.
4. Fill personal details from applicant_profile (work auth, comp, etc.).
5. Submit. Update Notion status to `applied`.

### Track
- Notion is the tracking surface: filter by status, update as things progress.
- Email monitoring for confirmations is a post-sprint extension.

---

## Out of scope for this sprint

- Postgres, migrations, auth, billing, web scaffold, multi-user.
- Auto-Apply / browser automation.
- VPS deployment (POC runs locally).
- MCP exposure (the `PipelineStep` contract makes this cheap later, but not this sprint).
- Eval harness (same — the contract unlocks it; not building it now).
- Telegram-based HITL checkpoint prompts (`AutoResolver` is the sprint default; revisit once the default flow is smooth).

---

## Notes for the implementing agent

- **Follow `CLAUDE.md` conventions** — `_Step` → `PipelineStep`, `_clean_llm_output`, config merges. Don't deviate.
- **Step bookkeeping is inherited, not copy-pasted.** After Ticket 2, no step should manually handle token counting, status emission, or run_log entries — that's the base class's job.
- **Library API is the contract.** `pipeline.add()`, `pipeline.refine()`, `pipeline.answer_questions()` must be clean, testable, presentation-free. CLI wraps; OpenClaw wraps; future web UI wraps.
- **Steps are deterministic; orchestrators are not.** No step decides what to run next. No self-scoring gates inside a step. No auto-learning silently mutating user state.
- **Data files gitignored.** `applicant_profile.json`, `queue.jsonl` go in `data/` (already ignored). `.env.example` only holds API keys / secrets — never PII, never paths.
- **Test end-to-end after each ticket.** Ticket 1: setup writes `applicant_profile.json`. Ticket 2: library call + CLI both work; `--non-interactive` writes `checkpoints.md`; regression guard passes. Ticket 3: answer flow works, refine loop works. Ticket 4: full Telegram round-trip. Ticket 5: Notion row populated, in-place updates, no duplicates.
- **Pre-push workflow:** implement → test → update `CLAUDE.md` + `README.md` → commit → push. Don't skip the docs step.
