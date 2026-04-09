# applycling

> Your clingy job-search companion. We won't leave you alone until you land your next role.

A small CLI that tailors your resume to job descriptions using a **local Ollama LLM**. Nothing leaves your machine.

It can:
- Save your base resume once.
- For each job, paste in the description and get back a tailored resume + a short, honest fit summary.
- Track every job you've tailored a resume for, with a status (tailored / applied / interview / offer / rejected).

---

## Prerequisites

- **Python 3.10+**
- **[Ollama](https://ollama.com)** installed and running
- At least one chat model pulled. Recommended (fast and good at text):
  - `ollama pull llama3.2`
  - `ollama pull mistral`
  - `ollama pull phi3`

If you're on macOS and only have the system Python (3.9), install a newer one with Homebrew:

```bash
brew install python@3.12
```

This gives you `python3.12` without touching the macOS-bundled `python3`.

---

## Install

applycling is a normal Python package — install it into a virtual environment so it doesn't fight with anything else on your system.

```bash
cd /path/to/applycling
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
```

After this you should have an `applycling` command on your PATH **while the venv is active**:

```bash
applycling --help
```

> **Each new terminal** you'll need to re-activate the venv before running the command:
> ```bash
> cd /path/to/applycling
> source .venv/bin/activate
> ```
> Type `deactivate` to leave the venv.

---

## First-time setup

Make sure Ollama is running in another terminal:

```bash
ollama serve
```

Then, with the venv active:

```bash
applycling setup
```

You'll be asked to:
1. **Paste your base resume.** Type/paste it into the terminal, then put `---` on its own line and press Enter to finish.
2. **Pick an Ollama model** from the numbered list of models you have installed.

Both your resume and your model choice are saved under `data/`.

---

## Tracker storage (planned: v0.2)

> The current version stores everything locally in `data/jobs.json`. v0.2 (Epic 0 on the dev board) replaces this with a pluggable `TrackerStore` so you can pick where your job tracker lives. The plan and the connection steps are below — they're aspirational until v0.2 ships.

In v0.2, applycling will support three backends:

- **Notion (recommended)** — your job tracker becomes a real Notion database, with views you can open on any device. Best for reviewing in the morning and editing on a real keyboard.
- **SQLite (default if no backend is configured)** — a single local file at `data/tracker.db`. Zero config, no account required.
- **CSV** — import/export only, not a primary store. Use it to move data in or out.

### Connecting to Notion

One-time setup:

1. Go to https://www.notion.so/my-integrations and click **+ New integration**.
2. Name it `applycling`, set the workspace, and submit.
3. Copy the **Internal Integration Secret** — you'll need it in a moment.
4. In your Notion workspace, open the page where you want the job tracker to live (any page works).
5. Click **··· → Connections → Connect to → applycling** to share that page with the integration.

Then, with the venv active:

```bash
applycling notion connect
```

You'll be asked for your integration secret and the URL of the parent page. applycling creates a "Job Tracker" database under that page with the columns it needs (title, company, source URL, status, application URL, fit summary, package folder, dates), and adds a **Review Queue** view filtered to `status = tailored`.

### Daily use after connecting

`applycling add` works exactly the same way it does today, but each tailored job now appears as a row in your Notion Job Tracker with a link to its package folder. Open the **Review Queue** view in Notion when you sit down in the morning to see what's waiting.

---

## Daily use

```bash
applycling add
```

Walks you through:
1. Job title
2. Company name
3. Paste the job description, end with `---` on its own line

It then streams a tailored resume from your local model, prints a short fit summary in a panel, and saves the tailored resume to `output/{company}-{title}-{date}.md`. The job gets a tracking ID like `job_001`.

```bash
applycling list                # table of every tracked job
applycling view job_001        # render a tailored resume in the terminal
applycling status job_001      # update status: tailored / applied / interview / offer / rejected
```

---

## Where things live

```
applycling/
├── data/
│   ├── resume.md     # your base resume
│   ├── config.json   # which Ollama model to use
│   └── jobs.json     # all tracked jobs
└── output/
    └── {company}-{title}-{date}.md   # one file per tailored resume
```

Everything stays on your machine.

---

## Troubleshooting

- **`Ollama doesn't seem to be running`** → start it with `ollama serve` in another terminal.
- **`No Ollama models installed`** → pull one, e.g. `ollama pull llama3.2`.
- **`No base resume found`** → run `applycling setup` first.
- **`command not found: applycling`** → activate the venv (`source .venv/bin/activate`), or run it directly with `.venv/bin/applycling ...`.
- **`Package 'applycling' requires a different Python`** → your active interpreter is older than 3.10. Create the venv with `python3.12 -m venv .venv` instead of plain `python3`.
