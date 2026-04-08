# Apply Companion

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

Apply Companion is a normal Python package — install it into a virtual environment so it doesn't fight with anything else on your system.

```bash
cd /path/to/apply-companion
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
```

After this you should have an `apply-companion` command on your PATH **while the venv is active**:

```bash
apply-companion --help
```

> **Each new terminal** you'll need to re-activate the venv before running the command:
> ```bash
> cd /path/to/apply-companion
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
apply-companion setup
```

You'll be asked to:
1. **Paste your base resume.** Type/paste it into the terminal, then put `---` on its own line and press Enter to finish.
2. **Pick an Ollama model** from the numbered list of models you have installed.

Both your resume and your model choice are saved under `data/`.

---

## Daily use

```bash
apply-companion add
```

Walks you through:
1. Job title
2. Company name
3. Paste the job description, end with `---` on its own line

It then streams a tailored resume from your local model, prints a short fit summary in a panel, and saves the tailored resume to `output/{company}-{title}-{date}.md`. The job gets a tracking ID like `job_001`.

```bash
apply-companion list                # table of every tracked job
apply-companion view job_001        # render a tailored resume in the terminal
apply-companion status job_001      # update status: tailored / applied / interview / offer / rejected
```

---

## Where things live

```
apply-companion/
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
- **`No base resume found`** → run `apply-companion setup` first.
- **`command not found: apply-companion`** → activate the venv (`source .venv/bin/activate`), or run it directly with `.venv/bin/apply-companion ...`.
- **`Package 'apply-companion' requires a different Python`** → your active interpreter is older than 3.10. Create the venv with `python3.12 -m venv .venv` instead of plain `python3`.
