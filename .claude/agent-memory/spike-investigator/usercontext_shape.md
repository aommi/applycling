---
name: UserContext Shape
description: Drafted UserContext, StepResult, CheckpointResolver dataclass shapes for Ticket 2 library refactor
type: project
---

Derived from T0 spike. Fields drawn from what cli.py add() loads at the top of the function (lines 537–551) plus what the plan document specifies.

## UserContext

```python
@dataclass
class UserContext:
    # Paths
    data_dir: Path           # default: storage.DATA_DIR (repo/data/)
    output_dir: Path         # from config["output_dir"] or storage.OUTPUT_DIR

    # Loaded data (loaded once at entry, threaded through every step)
    profile: dict | None     # from profile.json — name, email, voice_tone, never_fabricate, etc.
    resume: str              # base resume text (never mutated by LLM)
    stories: str | None      # from stories.md
    linkedin_profile: str | None  # from linkedin_profile.md (if use_linkedin_profile=True)
    config: dict             # full config.json contents

    # Future extension (Ticket 1)
    # applicant_profile: dict | None  # from applicant_profile.json

    # Infrastructure (never call directly — always pass via context)
    tracker: TrackerStore    # from get_store()

    # Convenience
    model: str               # resolved: model_arg or config["model"]
    provider: str            # resolved: provider_arg or config["provider"]
```

## StepResult

```python
@dataclass
class StepResult:
    name: str
    status: str              # "ok" | "skipped" | "failed"
    output: str              # cleaned LLM output (post _clean_llm_output)
    output_file: str | None  # filename in package folder (e.g. "strategy.md")
    duration_seconds: float
    tokens_in: int
    tokens_out: int
    started_at: str          # ISO UTC
    finished_at: str         # ISO UTC
    checkpoint: "CheckpointRecord | None" = None
    error: Exception | None = None
```

## CheckpointSpec

```python
@dataclass
class CheckpointSpec:
    name: str                # e.g. "angle", "gap", "strategy_edit"
    prompt: str              # question shown to user or sent to Telegram
    options: list[str]       # ranked options (top = AutoResolver default)
    default: str             # fallback if resolver returns None
```

## CheckpointRecord

```python
@dataclass
class CheckpointRecord:
    name: str
    chosen: str
    rationale: str
    alternatives: list[str]
    resolved_by: str         # "auto" | "interactive" | "telegram" | "override"
```

## CheckpointResolver (interface)

```python
class CheckpointResolver(Protocol):
    def resolve(self, spec: CheckpointSpec) -> str:
        """Return the chosen option string. Must never block indefinitely."""
        ...
```

## Concrete Resolvers

- `AutoResolver`: picks `spec.options[0]`, logs to checkpoints.md, returns immediately
- `InteractiveResolver`: prompts via Rich console (existing `_pick` / `Prompt.ask` pattern)
- `TelegramResolver`: future — sends options to Telegram, awaits reply (async with timeout fallback to auto)

## Notes

- `UserContext` is constructed once at the entry point (`pipeline.add()`) and threaded through every step. No step constructs its own context.
- Multi-user future: swap file-backed loaders for DB-backed ones without changing any step signatures.
- `tracker` field: always `get_store()` — never instantiate NotionStore or SQLiteStore directly in steps.
- `linkedin_profile` loading is gated by `config["use_linkedin_profile"]` — context carries the resolved value (None if disabled).
