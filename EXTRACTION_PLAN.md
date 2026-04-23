# Extraction Plan — Cross-Repo Agent Memory System

## Goal

Turn the applycling memory system into a reusable toolkit that works across any repository, for the same four agents: Claude Code, Hermes, OpenClaw, Codex.

---

## Proposed Architecture

Split the system into two layers:

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: AGENT-MEMORY-KIT (standalone tool / repo)         │
│                                                             │
│  - Generic memory protocol templates (preprompt, stop hook) │
│  - Agent adapters (Claude, Hermes, OpenClaw, Codex, etc.)   │
│  - CLI: `amk init`, `amk generate <agent>`                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                              ↓ reads
┌─────────────────────────────────────────────────────────────┐
│  Layer 2: PROJECT CONFIG (lives in each target repo)        │
│                                                             │
│  - `.memory.yaml` — project name, description, conventions  │
│  - `ARCHITECTURE.md` — project-specific architecture docs   │
│  - `memory/`, `dev/`, `DECISIONS.md` — runtime memory files │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Layer 1: Agent Memory Kit (new repo)

Suggested repo name: `agent-memory-kit` or `amk`

### Structure

```
amk/
  pyproject.toml
  README.md
  amk/
    __init__.py
    cli.py              # Click/Typer CLI: init, generate, doctor
    core.py             # Shared logic: config loading, template rendering
    adapters/
      __init__.py
      claude_code.py    # Generates CLAUDE.md + .claude/settings.json
      codex.py          # Generates AGENTS.md
      hermes.py         # Generates AGENTS.md (superset)
      openclaw.py       # Generates .openclaw-system.md
      cursor.py         # Optional
      windsurf.py       # Optional
      gemini_cli.py     # Optional
    templates/
      preprompt.txt     # Generic: read working.md, MCP efficiency, task-switching
      stop.sh           # Generic: diff inspection, update proposals
      memory_protocol.md # Generic memory system description (agent-agnostic)
      agent_entry/
        claude_code.md  # Skeleton for CLAUDE.md (project-agnostic rules)
        codex.md        # Skeleton for AGENTS.md
        openclaw.md     # Skeleton for .openclaw-system.md
  tests/
```

### How It Works

**Install once (globally or per-venv):**

```bash
pipx install agent-memory-kit
# or
pip install agent-memory-kit
```

**In each target repo:**

```bash
cd ~/projects/my-new-project
amk init
```

This creates:
- `.memory.yaml` — project config (you edit this)
- `memory/semantic.md` — empty template
- `memory/working.md` — empty template
- `DECISIONS.md` — empty template
- `dev/` — empty directory
- `.gitignore` entries for agent-generated files

**Then generate agent configs:**

```bash
amk generate claude-code   # CLAUDE.md + .claude/settings.json + hooks
amk generate hermes        # AGENTS.md
amk generate openclaw      # .openclaw-system.md
amk generate all           # everything
```

The adapters read `.memory.yaml` and `ARCHITECTURE.md` from the target repo, inject them into the generic templates, and write the agent-specific files.

---

## Layer 2: Project Config (per repo)

### `.memory.yaml`

```yaml
project:
  name: my-new-project
  description: A web service that does X
  language: python

architecture:
  file: ARCHITECTURE.md   # path to project architecture doc (optional)
  inline: |               # or inline (optional, overrides file)
    Key components:
    - api/ — FastAPI routes
    - db/ — SQLAlchemy models
    - worker/ — Celery background tasks

conventions:
  - "Use pytest for all tests"
  - "API keys live in .env"

skills:
  enabled: false          # set true if using agentskills.io standard
  directory: skills/      # where skill files live

agents:
  claude_code:
    enabled: true
    hooks:
      preprompt: true
      stop: true
  hermes:
    enabled: true
  openclaw:
    enabled: true
  codex:
    enabled: true
```

### `ARCHITECTURE.md` (optional but recommended)

This is where project-specific knowledge lives. It's referenced by `.memory.yaml` and injected into every agent's entry-point file. Keep it under 500 lines. Update it when architecture changes.

```markdown
# Architecture — my-new-project

## Core Systems

- **API layer:** FastAPI in `api/`, dependency injection for DB sessions
- **Data layer:** SQLAlchemy + asyncpg, migrations with Alembic
- **Background jobs:** Celery + Redis, tasks in `worker/tasks/`

## Key Patterns

- Thin controllers, fat services
- All DB access goes through repositories in `db/repos/`

## Key Conventions

- `pytest --asyncio-mode=auto` for all test runs
- Never commit `.env`
```

---

## What Changes in Each Adapter

### Claude Code Adapter

Currently: writes a hardcoded `CLAUDE.md` with applycling-specific content.

Extracted: reads `.memory.yaml` + `ARCHITECTURE.md`, renders:

```markdown
# {{ project.name }} — Developer Guide

**{{ project.description }}**

---

## Memory System (Session Startup + Hooks)

**On session start:** Read `memory/semantic.md` ONCE to load project context.

**On every turn:** The preprompt hook handles reading `memory/working.md`.

{{ memory_protocol }}

---

## Architecture

{{ architecture_content }}

---

## Key Conventions

{{ conventions }}
```

### Hermes / Codex Adapters

Currently: concatenates hardcoded project description + preprompt + architecture.md template.

Extracted: reads `.memory.yaml` + `ARCHITECTURE.md`, renders a project-agnostic `AGENTS.md`.

Hermes gets the `agentskills.io` note if `skills.enabled: true` in `.memory.yaml`.

### OpenClaw Adapter

Currently: hardcoded applycling project name and description.

Extracted: uses `.memory.yaml` for project metadata, injects generic memory protocol + architecture.

---

## Migration Path from Current System

### Step 1: Extract `.agent/` into new repo

```bash
# New repo: github.com/aommi/agent-memory-kit
git clone https://github.com/aommi/applycling agent-memory-kit
cd agent-memory-kit
git filter-branch --subdirectory-filter .agent -- --all
# Clean up: rename generate.py → amk/cli.py, add pyproject.toml, etc.
```

Or just copy the files and refactor.

### Step 2: Parameterize templates

- Replace all applycling-specific strings in templates with Jinja2 variables
- `architecture.md` template becomes a generic placeholder that reads from `ARCHITECTURE.md` or `.memory.yaml`
- `preprompt.txt` and `stop.sh` stay almost exactly as-is (they're already generic)

### Step 3: Add `amk init`

- Scaffolds `.memory.yaml`, `memory/`, `dev/`, `DECISIONS.md`
- Detects existing project type (Python, Node, etc.) and pre-fills conventions

### Step 4: Update applycling to use the extracted tool

```bash
cd /users/amirali/Documents/dev/applycling
pipx install agent-memory-kit
amk init        # creates .memory.yaml, migrates existing memory/
amk generate all
```

Then delete `.agent/` from applycling. The generated files (`CLAUDE.md`, `AGENTS.md`, etc.) remain, but they're now generated by the external tool.

### Step 5: Use in new repos

```bash
cd ~/projects/new-project
amk init
# edit .memory.yaml
amk generate claude-code hermes openclaw
```

---

## Simpler Alternative: Repo Template Approach

If building a pip-installable CLI feels like overkill for a solo workflow, use a **repo template** instead:

1. Create `github.com/aommi/agent-memory-template` containing:
   - `.agent/` (parameterized templates)
   - `memory/semantic.md` (empty template)
   - `memory/working.md` (empty template)
   - `DECISIONS.md` (empty template)
   - `dev/` (empty)
   - `ARCHITECTURE.md` (empty template)
   - `.memory.yaml` (empty template)
   - A `Makefile` with `make generate AGENT=claude-code`

2. In each new project:
   ```bash
   git clone https://github.com/aommi/agent-memory-template .agent-memory
   cp -r .agent-memory/. .
   rm -rf .agent-memory
   # edit .memory.yaml and ARCHITECTURE.md
   make generate all
   ```

3. When templates improve, update the template repo and re-run `make generate` in each project.

**Trade-off:** No pip install, no Python packaging, no global CLI. Just copy + generate. Good enough for 1-5 repos.

---

## Recommendation

Given your workflow (solo dev, multiple repos, 4 agents), I recommend the **middle path**:

1. **Extract `.agent/` into its own repo** (`aommi/agent-memory-kit`)
2. **Don't publish to PyPI yet** — just `pip install git+https://...` or keep it as a git submodule
3. **Use a `.memory.yaml` config** in each repo for project-specific content
4. **Keep `ARCHITECTURE.md` as the project-specific knowledge doc** that you maintain by hand
5. **The generic templates (`preprompt.txt`, `stop.sh`, memory protocol) live in the kit** and rarely change

This gives you reusability without the ceremony of a full open-source Python package.

---

## What I Can Do Now

If you want, I can:

1. **Create the extracted kit repo structure** locally (e.g., in `~/dev/agent-memory-kit/`) with parameterized templates
2. **Migrate applycling** to use the kit (create `.memory.yaml`, generate files, delete `.agent/`)
3. **Test it on a second dummy repo** to prove cross-repo portability
4. **Write the install/generate instructions** for each of your 4 agents

Which direction do you want to go?
