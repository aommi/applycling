# applycling Architecture Vision

*Canonical record of architectural principles, load-bearing assumptions, and planned
capabilities. Not a current-state inventory — for what's built today, see
`memory/semantic.md`. For sprint plans and tickets, see `docs/planning/` (local-only,
gitignored).*

*If you are reading this for the first time, you should leave knowing: (1) what the
architecture IS committed to, (2) why, and (3) where it is going. Do not re-derive
this analysis — extend it.*

---

## 1. Thesis

applycling is a **thin orchestrator of fat markdown skills** that turns any signal
about a job (URL, email, Telegram message, form field) into a complete application
package.

Three design commitments define the system:

1. **Intelligence lives in skills, not the runtime.** Each skill is a `SKILL.md`
   file: YAML frontmatter (contract) + prompt body (behavior). The Python harness
   is boring plumbing — loader, pipeline runner, LLM router, renderer.
2. **The pipeline is a library, not a CLI.** `applycling.pipeline` is the public
   contract. The CLI, OpenClaw, future web UI, and MCP tools are all callers of
   the same library. Every capability is invocable from anywhere.
3. **Composition is explicit.** Steps are ordered deterministically today.
   Context-based resolvers and agent-driven resolvers layer on top without
   rewriting the core.

This is Garry Tan's model — *thin harness, fat skills, learning loops, composition,
triggers, quality gates* — scoped to a deterministic domain, with a documented
on-ramp to full agent behavior.

**Two-level vocabulary (used throughout this doc):**
- **Skill** — a single `SKILL.md` file: one prompt, one output, one responsibility.
  The atomic unit.
- **Capability** — an orchestrated action that composes one or more skills in
  sequence. `generate_application_package` runs 8 skills in order. `interview_prep`
  and `follow_up_outreach` are lighter capabilities.

---

## 2. How applycling Maps to Garry Tan's Model

| Garry's primitive | applycling today | applycling destination |
|-------------------|------------------|------------------------|
| Fat skills as `.md` | ✅ 16 skills, one dir each | Same shape, more skills |
| Thin harness | ✅ loader + pipeline + CLI | Unchanged |
| Learning loops | ❌ not yet | `LEARNED.md` per skill (learning loops) |
| Composition / resolvers | ❌ linear pipeline only | `RESOLVER.md` routes on JD/company context (context-based resolvers) |
| Triggers | ❌ implicit (always run in order) | Frontmatter `trigger:` field (conditional → event-driven) |
| Quality gates | ❌ | Frontmatter `quality_gate:` + validators (agent routing) |
| Automatic signal detection | ❌ user-directed only | Activated for computer-use agent |

**Where we diverge intentionally:**

1. **No fuzzy agent routing in the linear pipeline phase.** The user's intent is
   always "turn this job URL into a package." Linear, deterministic, auditable.
   Resolvers are unnecessary until context genuinely branches.
2. **Learning is user-initiated, not autonomous.** A human reviews every output.
   Capturing their edits is higher-signal than guessing patterns from logs.
   Autonomous learning activates only when the human leaves the loop (computer-use
   territory).
3. **Triggers are optional, not mandatory.** Core pipeline steps have
   `trigger: always` (implicit). Optional skills use `trigger: conditional`.
   Event-driven triggers arrive with the agent routing capability.

These are *scoping* decisions, not departures from the philosophy.

---

## 3. Multi-Source Initiation (Library-First Design)

The pipeline is initiated by many sources today and in the near future:

```
┌─────────────┐   ┌─────────────┐   ┌──────────────┐   ┌─────────────┐
│     CLI     │   │ Hermes /    │   │  Local Web   │   │  Computer   │
│ applycling  │   │ OpenClaw    │   │  Workbench   │   │  use agent  │
│    add      │   │ (Telegram)  │   │  (:8080)     │   │  (future)   │
└──────┬──────┘   └──────┬──────┘   └──────┬───────┘   └──────┬──────┘
       │                 │                 │                   │
       └─────────────────┴──────┬──────────┴───────────────────┘
                                ▼
                 ┌──────────────────────────────┐
                 │   applycling.pipeline        │
                 │   (PipelineContext, Step,    │
                 │    Run — library API)        │
                 └──────────────┬───────────────┘
                                ▼
                 ┌──────────────────────────────┐
                 │   applycling.skills.*        │
                 │   load_skill() → render()    │
                 └──────────────┬───────────────┘
                                ▼
                 ┌──────────────────────────────┐
                 │   applycling.llm (provider   │
                 │   router: ollama/anthropic/  │
                 │   google/openai)             │
                 └──────────────────────────────┘
```

The interface layer is intentionally thin. The local CLI, Telegram/Discord/WhatsApp/
Slack (via Hermes/OpenClaw-style messaging gateways), MCP tools, and future Web UI
are all entry points that call the same `applycling.pipeline` library. Switching to
a new interface requires only a small adapter — no pipeline changes.

The local web workbench (`applycling/ui/` at `http://127.0.0.1:8080`) validates the
UI path for the same library API. Production web UI and MCP server are separate
planned capabilities (§5).

**Key invariants:**

- Every caller goes through `pipeline.py`. No caller reaches into `skills/`,
  `llm.py`, or `storage.py` directly.
- Steps **don't replan**. Orchestrators own control flow; a step takes inputs and
  produces outputs. This keeps capabilities composable by any caller.
- The CLI is a thin wrapper around the library, not the other way around.

### OpenClaw integration

**[VERIFIED against OpenClaw README 2026-04-18]**

OpenClaw is a personal AI assistant (local-first) that functions as a universal
messaging gateway. applycling is designed as **a capability within OpenClaw's
library**. Telegram is the primary user path today; other platforms work via the
same OpenClaw gateway.

The integration contract:

1. OpenClaw receives a job URL (via any supported messaging platform).
2. OpenClaw calls `applycling.pipeline.run_add(job_url, ctx)`.
3. applycling streams `on_status` events. OpenClaw's Gateway forwards updates to
   the user's chosen channel.
4. applycling returns an `AddResult`. OpenClaw handles persistence — applycling
   never knows where files live.

**[ASPIRATIONAL — pending context-based resolver work]**

The SKILL.md format was designed to be compatible with OpenClaw's
`~/.openclaw/workspace/skills/<skill>/SKILL.md` convention. In the resolver phase,
when applycling skills become context-switchable, this format alignment will enable
direct portability to OpenClaw's skill library.

**[UNDOCUMENTED]**

How applycling registers as a tool within OpenClaw's tool registry (discovery,
capability advertisement, invocation routing) is not yet documented. This will be
clarified when resolvers make skills directly discoverable.

### Hermes Telegram validation

For Phase 1 local Telegram validation, inbound Telegram intake is delegated to a
Hermes profile/gateway. Hermes receives the job URL from Telegram and invokes
applycling's terminal entry point. applycling remains responsible for pipeline
execution, outbound progress messages, PDF delivery, local output artifacts, and
worker logs.

This keeps the initial validation focused on the product loop while avoiding a
throwaway Telegram listener in applycling. Hosted SaaS intake should use dedicated
gateway/webhook infrastructure, not the Hermes personal-profile path.

---

## 4. Assumptions

Load-bearing premises the architecture depends on. Each assumption can be
invalidated by a concrete condition. When one is invalidated: append a supersession
to `DECISIONS.md` first, then update or remove the assumption here.

**Test for inclusion:** would invalidating this force a rewrite of the pipeline or
its core design? If yes → here. If no → `DECISIONS.md`.

> **Assumption: The pipeline is the right abstraction for all callers (library-first)**
> Load-bearing because: the multi-source design (CLI, Telegram, future web UI) depends
> on a single `pipeline.run_add()` contract. Every new caller costs ~100 lines, not a
> fork.
> Invalidated when: two callers need fundamentally different pipelines — different steps,
> different ordering, different outputs. At that point, split the pipeline or
> parameterize it.

> **Assumption: User intent is always "URL → package" (linear pipeline is sufficient)**
> Load-bearing because: agent routing earns its complexity only when intent genuinely
> branches. The linear shape also makes regressions easy to spot (diff the run_log).
> Invalidated when: the system handles multiple distinct intent types that need different
> step sequences concurrently. This is expected territory for the computer-use agent.

> **Assumption: Learning should be user-initiated, not autonomous**
> Load-bearing because: a human reviews every output. Their edits are labeled ground
> truth — orders of magnitude higher signal than behavioral heuristics.
> Invalidated when: the human leaves the review loop. Autonomous detection matters when
> the human is no longer in the loop, which is computer-use territory.

> **Assumption: Skills are the right abstraction boundary (fat skills + thin harness)**
> Load-bearing because: the SKILL.md contract (frontmatter + prompt body) is the API
> between product logic and the AI. Resolvers, learning loops, and forks all depend on
> this boundary staying clean.
> Invalidated when: skill files need their own logic layer (control flow, imports,
> conditionals). At that point, consider whether a richer format is warranted or whether
> the logic belongs in a resolver instead.

**DECISIONS.md vs. Assumptions:**
- `DECISIONS.md` = immutable log — "we chose X on date Y because Z" — append-only,
  never edited, only superseded
- Assumptions here = live load-bearing premises — mutable, updated when a premise is
  invalidated

---

## 5. Vision: Planned Capabilities

Capabilities not yet built, listed by function rather than sprint order.

### MCP server

An `applycling mcp serve` command exposes pipeline capabilities as MCP tools, making
applycling usable from any MCP-compatible client (Claude Desktop, Cursor, etc.) without
touching the CLI.

Each tool maps 1:1 to a pipeline capability and calls `applycling.pipeline` directly —
never via subprocess. This keeps it on the stable public contract and means new pipeline
features flow through automatically.

Initial tool surface:
- `add_job(url)` → `pipeline.run_add()`
- `list_jobs()` → tracker
- `get_package(job_id)` → artifact paths + content
- `interview_prep(job_id)`, `refine(job_id, feedback)`

**Compatibility discipline:** when a new pipeline capability ships, the corresponding MCP
tool ships in the same PR. This is enforced via two mechanisms:
- `memory/semantic.md` Key Patterns — active-session reminder for every agent
- `.agent/project.yaml` conventions — propagates into all agent entry-point files
  (CLAUDE.md, AGENTS.md, GEMINI.md, etc.) when `python .agent/generate.py all` is run,
  so no agent can miss the rule

**What it unlocks:** low-friction setup for additional users — `pip install applycling`,
`applycling setup` (enter resume/profile), add MCP config to client. No CLI knowledge,
no Telegram bot required. Each user still needs their own local profile and API key;
true multi-user is Phase 3.

### Context-based resolvers

Skills gain optional frontmatter fields: `trigger: always | conditional | variant`,
`when: <expression over ctx.job>`, `variant_of: <base_skill>`.

`applycling/skills/resolver.py` evaluates `when` expressions against the job/company
context and picks the right skill variant. The pipeline calls `resolve()` instead of
`load_skill()` for skills that have variants.

First variants: `positioning_brief_ai.md` (when JD mentions AI/ML/LLM),
`positioning_brief_startup.md` (when company ≤ 50 people).

Users can drop a custom variant into `~/.applycling/skills/` to override defaults.
`applycling resolve --dry-run <url>` prints which variant each skill resolved to.

A skill with no variants behaves identically to today — additive change, zero
regression.

### Learning loops

After each run, `<output>.original.md` is written alongside `<output>.md`. `applycling
learn <run_dir>` diffs edited vs. original, summarizes the diff via LLM, and appends
an observation to `skills/<name>/LEARNED.md`. `Skill.render()` injects `LEARNED.md`
content as `{learned_patterns}` (empty string if absent). Size cap per `LEARNED.md`;
LLM-summarize on overflow.

Patterns are visible, human-editable, and revertable — it's just a file.

### Computer-use agent + full agent routing

Frontmatter gains: `trigger: on_event`, `event: <detector_name>`,
`quality_gate: <validator_name>`, `chain_after: [skill1, skill2]`, `on_error: <policy>`.

Trigger registry detects browser signals ("form field asks X", "captcha present").
Quality-gate registry validates outputs (min-length, schema match, factual consistency
vs. `role_intel`). Dynamic resolver: agent requests `resolve_skill("answer_why_work_here",
ctx)` at runtime.

Execution loop: detect → resolve → render → generate → validate → submit → capture in
`LEARNED.md`.

All submit actions default to dry-run preview. Human confirms before first real
submission to any new site. Per-site trust list gates autonomous mode.

Open architectural question: does the computer-use agent live in applycling, OpenClaw,
or a new `applycling-browser` package? Leaning: new package; applycling stays focused
on document generation.

---

## 6. SaaS Scalability (Strategic Confirmation, Not Build Target)

The architecture supports SaaS without rework. Do not build for SaaS now; confirm
nothing blocks it.

| SaaS concern | Current architecture status |
|--------------|------------------------------|
| Multi-tenancy | `PipelineContext` is per-run and in-memory. Hosted mode loads profile, resume, stories, and applicant profile from tenant-scoped `user_contexts` rows instead of local `data/*` files; the context-loading adapter changes, not the generation pipeline. |
| Per-user skill overrides | `~/.applycling/skills/` already overrides built-in `applycling/skills/`. On SaaS, resolve user skills from a DB before built-ins. Same precedence, different store. |
| Provider keys per tenant | `llm.py` already takes provider/model per call. Inject per-tenant keys via `PipelineContext.config`. |
| Long-running jobs | `pipeline.run_add()` is already stream-friendly via `on_status`. A web worker picks up queued jobs (same `queue.py` pattern). |
| Observability | `run_log.json` is already structured. Ship it to a log sink on SaaS. |
| Cost controls | Token counts are already tracked per step. Enforce tenant budgets in the pipeline wrapper. |
| Skill sharing / marketplace | Skills are self-contained `SKILL.md` files. A marketplace is a registry + download into the user's skill dir. |
| Hosted persistence | Phased: local SQLite/Notion (current) → Docker + local Postgres + initial schema (shipped #22) → hosted Postgres with tenant isolation, `user_contexts`, rate limits, `ArtifactStore` (later). Full design in `docs/planning/DB_TECH_DESIGN.md` (local-only). |
| Notion as enhancement layer | Local mode only. In hosted mode Notion is deferred until after public beta, then planned as one-way Postgres → Notion sync. |

**The three things SaaS would require that don't exist yet:**
1. Auth + tenant isolation at the storage layer (trivial — `storage.py` is a
   file-path-based facade).
2. Hosted user context persistence (`user_contexts`) plus an import/onboarding path
   so SaaS generation never depends on local `data/*` files.
3. A hosted queue + worker pool (already partially designed for OpenClaw via
   `queue.py`).

Neither forces architectural change. The thin-harness / fat-skills split is the
asset here: skills scale horizontally (just more files), the runtime stays small.

---

## 7. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Skill contract creep (too many optional frontmatter fields) | Medium | Medium | Every new field must be additive (default = old behavior). Document each in `skills/loader.py` docstring. Reject fields that only one skill uses. |
| Resolver becomes implicit routing black box (resolvers) | Medium | High | `applycling resolve --dry-run` shows which variant each skill resolved to. Every resolution logged in `run_log.json`. |
| `LEARNED.md` drift / poisoning (learning loops) | Medium | Medium | Size cap + LLM-summarize on overflow. File is user-visible and deletable. Never inject raw user edits — always summarize first. |
| Skill forks diverge from built-ins | High | Low | `~/.applycling/skills/` files show a warning on load if the built-in schema has moved. `applycling skills diff` compares user skill to shipped version. |
| Provider lock-in via `model_hint` | Low | Medium | `model_hint` is a hint, not a requirement. Runtime can override. Skills avoid provider-specific syntax. |
| Quality gates become fragile validators (agent routing) | Medium | High | Validators live in `validators.py` (Python), not skills. Skills declare gate by name only. Validators are unit-tested. |
| Computer-use agent submits wrong answer (agent routing) | High if shipped naively | High | All submit actions default to dry-run preview. Human confirms before first real submission to any new site. Per-site trust list gates autonomous mode. |
| OpenClaw and applycling evolve out of sync | Medium | Medium | Pin `pipeline.run_add()` signature; version with `applycling.__version__`. OpenClaw runs against a declared version. |
| Prompt regressions when skill is edited | High | Medium | `output/<run>/run_log.json` captures the full prompt. A regression test fixture compares against golden runs for each shipped skill. (Not yet built — candidate for resolver phase hardening.) |

---

## 8. How to Add a New Pipeline Step

A "pipeline step" here means adding a new **skill** as a step within an existing
**capability**. To add a new top-level capability (e.g., a new orchestration like
`interview_prep`), follow the same skill-creation pattern but wire it into a new CLI
command rather than the `run_add()` pipeline.

All pipeline steps use the `_Step` context manager in `cli.py`, which handles timing,
logging, token counting, and status automatically.

**Step 1 — Create `applycling/skills/<name>/SKILL.md`:**

```markdown
---
name: my_step
description: One-line description
inputs:
  - input_key_one
  - input_key_two
output_file: my_step.md   # omit if the step produces no output file
---
You are an expert at...

=== INPUT ONE ===
{input_key_one}

=== INPUT TWO ===
{input_key_two}
```

**Step 2 — Add the function to `llm.py`:**

```python
from .skills import load_skill

def my_step(input_key_one: str, input_key_two: str, model: str, provider: str = "ollama") -> Iterator[str]:
    prompt = load_skill("my_step").render(input_key_one=input_key_one, input_key_two=input_key_two)
    yield from _stream_chat(model, prompt, provider)
```

**Step 3 — Use `_Step` in `cli.py` or `PipelineStep` in `pipeline.py`:**

```python
_s = _Step("my_step", step_logs, output_file="my_step.md")
_s.prompt_text = load_skill("my_step").render(input_key_one=..., input_key_two=...)
try:
    with _s, console.status("[cyan]Doing the thing...[/cyan]", spinner="dots"):
        for chunk in llm.my_step(..., provider=provider):
            _s.collect(chunk)
except llm.LLMError as e:
    console.print(f"[red]{e}[/red]")
    sys.exit(1)
result = _clean_llm_output(_s.output)
```

Notes:
- `prompt_text` must be set before entering the `with` block.
- `_Step.__exit__` auto-appends to `step_logs` — no manual append needed.
- Status is set to `"ok"`, `"skipped"`, or `"failed"` automatically.
- Use `[red]` + `sys.exit(1)` for critical steps; `[yellow]` + `continue` for optional.
- When the step ships: add it to `memory/semantic.md` (Core Systems) and remove it from
  Section 5 of this doc (Vision: Planned Capabilities). Current state belongs in
  `semantic.md`, not the vision doc.

---

## 9. Agent Agnosticism

The memory system (`memory/semantic.md`, `memory/working.md`, `dev/[task]/`,
`DECISIONS.md`) is portable across AI coding agents. The adapter layer (`.agent/`)
generates the right entry-point file and hook configuration for each tool.

**Supported agents:**
- **Claude Code**: `CLAUDE.md` + `.claude/settings.json` hooks (full hook support)
- **Codex**: `AGENTS.md` (hooks not supported — relies on agent reading entry-point)
- **Hermes** (Nous Research): `AGENTS.md` superset of Codex; agentskills.io-compatible
- **Cursor**: `.cursor/rules/memory.mdc` with `alwaysApply: true`
- **Gemini CLI**: `GEMINI.md` + `.gemini/context.md`
- **Windsurf**: `.windsurfrules` (instruction-driven, no hook support)
- **OpenClaw**: `.openclaw-system.md` (system prompt include)

```bash
python .agent/generate.py <agent>   # or 'all' for all agents
```

**What stays portable:**
- `memory/semantic.md` — distilled project knowledge
- `memory/working.md` — live task state
- `DECISIONS.md` — append-only log
- `dev/[task]/` — task context

See `.agent/README.md` for details.

---

## 10. What This Document Is Not

- Not a current-state inventory — see `memory/semantic.md`
- Not a sprint plan or ticket list — see `docs/planning/` (local-only, gitignored)
- Not an API reference — see docstrings in `pipeline.py` and `skills/loader.py`
- Not a user guide — see `README.md`
- Never contains: ticket numbers, sprint phases, implementation checklists, or
  current build status

If a change contradicts any section here, update this doc in the same commit. This is
the source of truth for *why* applycling looks the way it does and *where* it is going.
