"""applycling CLI."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from . import llm, notion_connect, package, pdf_import, prompts, storage
from .tracker import STATUSES, Job, TrackerError, get_store

console = Console()

STATUS_STYLES = {
    "tailored": "blue",
    "applied": "yellow",
    "interview": "green",
    "offer": "bold green",
    "rejected": "dim",
}


def _profile_header_markdown(profile: dict) -> str:
    """Build the static top section of the resume from stored profile fields."""
    lines = []
    name = profile.get("name", "").strip()
    if name:
        lines.append(f"# {name}\n")
    contact = " · ".join(filter(None, [
        profile.get("email", "").strip(),
        profile.get("phone", "").strip(),
        profile.get("location", "").strip(),
    ]))
    if contact:
        lines.append(contact)
    links = " · ".join(filter(None, [
        profile.get("linkedin", "").strip(),
        profile.get("github", "").strip(),
    ]))
    if links:
        lines.append(links)
    return "\n".join(lines)


def _read_multiline(prompt_text: str) -> str:
    console.print(f"[bold]{prompt_text}[/bold]")
    console.print("[dim]Paste the text, then type [bold]---[/bold] on its own line and press Enter to finish.[/dim]")
    lines: list[str] = []
    while True:
        try:
            line = input("> " if not lines else "  ")
        except EOFError:
            break
        if line.strip() == "---":
            break
        lines.append(line)
    return "\n".join(lines).strip()


def _require_config() -> dict:
    try:
        return storage.load_config()
    except storage.StorageError:
        console.print(
            "[red]No config found.[/red] Run [bold]applycling setup[/bold] first."
        )
        sys.exit(1)


def _require_resume() -> str:
    try:
        return storage.load_resume()
    except storage.StorageError:
        console.print(
            "[red]No base resume found.[/red] Run [bold]applycling setup[/bold] first."
        )
        sys.exit(1)


@click.group()
def main() -> None:
    """applycling — your clingy job-search companion."""


# ---------- setup ----------

def _setup_resume_from_pdf(model: str) -> str:
    """Interactive PDF import. Returns the cleaned Markdown."""
    while True:
        path_str = Prompt.ask("PDF path")
        # Tolerate quoted paths and escaped spaces from drag-and-drop.
        cleaned_path = path_str.strip().strip("'\"").replace("\\ ", " ")
        pdf_path = Path(cleaned_path).expanduser()
        if not pdf_path.exists():
            console.print(f"[red]File not found:[/red] {pdf_path}")
            continue

        try:
            console.print()
            with console.status(
                "[cyan]Extracting text from PDF...[/cyan]", spinner="dots"
            ):
                raw = pdf_import.extract_text(pdf_path)
        except pdf_import.PDFImportError as e:
            console.print(f"[red]{e}[/red]")
            continue

        skip_llm = Prompt.ask(
            "Clean up text with Ollama? (skip if using a large model on limited RAM)",
            choices=["yes", "skip"],
            default="yes",
        )
        if skip_llm == "skip":
            cleaned = raw
        else:
            try:
                parts: list[str] = []
                with console.status(
                    "[cyan]Cleaning into Markdown via Ollama...[/cyan]",
                    spinner="dots",
                ):
                    for chunk in pdf_import.clean_to_markdown(raw, model):
                        parts.append(chunk)
            except llm.LLMError as e:
                console.print(f"[red]{e}[/red]")
                sys.exit(1)
            cleaned = "".join(parts).strip()

        console.print()
        console.print(
            Panel(Markdown(cleaned), title="Extracted resume", style="cyan")
        )

        choice = Prompt.ask(
            "Looks right?",
            choices=["yes", "redo", "paste"],
            default="yes",
        )
        if choice == "yes":
            return cleaned
        if choice == "paste":
            return _read_multiline("Paste your base resume below:")
        # redo: loop and ask for a different PDF


@main.command()
def setup() -> None:
    """First-time setup: save base resume and pick an Ollama model."""
    console.print(Panel.fit("[bold]applycling — Setup[/bold]", style="cyan"))

    # Pick a model first so the PDF importer can use it.
    try:
        models = llm.get_available_models()
    except llm.LLMError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    if not models:
        console.print(
            "[red]No Ollama models installed.[/red] Try: "
            "[bold]ollama pull llama3.2[/bold]"
        )
        sys.exit(1)

    console.print("\n[bold]Available Ollama models:[/bold]")
    for i, name in enumerate(models, 1):
        console.print(f"  [cyan]{i}[/cyan]. {name}")
    choice = Prompt.ask(
        "Pick a model",
        choices=[str(i) for i in range(1, len(models) + 1)],
        default="1",
    )
    chosen_model = models[int(choice) - 1]

    # Pick how to provide the base resume.
    console.print()
    source = Prompt.ask(
        "Base resume input",
        choices=["pdf", "paste"],
        default="pdf",
    )
    if source == "pdf":
        resume = _setup_resume_from_pdf(chosen_model)
    else:
        resume = _read_multiline("Paste your base resume below:")

    if not resume:
        console.print("[red]Empty resume — aborting.[/red]")
        sys.exit(1)

    storage.save_resume(resume)
    storage.save_config({"model": chosen_model})

    # Collect personal details (stored separately, never passed to the LLM).
    console.print("\n[bold]Personal details[/bold] [dim](used verbatim in every resume — never rewritten by AI)[/dim]")
    existing = storage.load_profile() or {}
    profile = {
        "name":     Prompt.ask("Full name",       default=existing.get("name", "")),
        "email":    Prompt.ask("Email",            default=existing.get("email", "")),
        "phone":    Prompt.ask("Phone",            default=existing.get("phone", "")),
        "location": Prompt.ask("Location",         default=existing.get("location", "")),
        "linkedin": Prompt.ask("LinkedIn URL",     default=existing.get("linkedin", "")),
        "github":   Prompt.ask("GitHub URL",       default=existing.get("github", "")),
    }
    storage.save_profile({k: v for k, v in profile.items() if v})

    # Ensure Playwright browsers are installed (needed for PDF rendering).
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.launch()  # quick check — will fail if browsers missing
    except Exception:
        console.print("\n[yellow]Installing Playwright browsers (one-time)…[/yellow]")
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=False,
        )
        if result.returncode != 0:
            console.print(
                "[red]Playwright browser install failed.[/red] "
                "Run manually: [bold]playwright install chromium[/bold]"
            )

    console.print(
        Panel.fit(
            f"[green]Setup complete![/green]\n"
            f"Model: [bold]{chosen_model}[/bold]\n\n"
            f"Next steps:\n"
            f"  • Optional: [bold]applycling notion connect[/bold] "
            f"to use Notion as your tracker.\n"
            f"  • Then: [bold]applycling add[/bold] to tailor your resume to a job.",
            style="green",
        )
    )


# ---------- add ----------

@main.command()
def add() -> None:
    """Add a job: tailor a resume + assemble an application package."""
    cfg = _require_config()
    base_resume = _require_resume()
    model = cfg.get("model")
    if not model:
        console.print("[red]No model in config.[/red] Run setup again.")
        sys.exit(1)
    profile = storage.load_profile()
    context = storage.load_context()

    # Token tracking: list of (step_name, prompt_text, output_text).
    token_steps: list[tuple[str, str, str]] = []

    source_url = Prompt.ask("Job posting URL (leave blank to enter details manually)", default="")
    title = company = job_description = ""

    company_url = ""
    if source_url:
        from . import scraper
        try:
            with console.status("[cyan]Fetching job posting...[/cyan]", spinner="dots"):
                posting, scrape_tokens = scraper.fetch_job_posting(source_url, model)
            token_steps.append(("Job scraping", scrape_tokens[0], scrape_tokens[1]))
            title = posting.title
            company = posting.company
            job_description = posting.description
            company_url = posting.company_url
            console.print(f"[green]Fetched:[/green] [bold]{title}[/bold] @ [bold]{company}[/bold]")
            title = Prompt.ask("Job title", default=title)
            company = Prompt.ask("Company name", default=company)
            if company_url:
                console.print(f"[dim]Company page detected: {company_url}[/dim]")
            company_url = Prompt.ask("Company page URL (for context)", default=company_url)
        except Exception as e:
            console.print(f"[yellow]Could not auto-fetch details ({e}) — falling back to manual entry.[/yellow]")
            source_url = ""

    if not source_url:
        title = Prompt.ask("Job title")
        company = Prompt.ask("Company name")
        source_url = Prompt.ask("Source URL (optional)", default="")
        company_url = Prompt.ask("Company page URL (optional)", default="")
        job_description = _read_multiline("Paste the job description below (end with --- on its own line):")

    if not job_description:
        console.print("[red]Empty job description — aborting.[/red]")
        sys.exit(1)

    want_summary = Prompt.ask(
        "Include a profile summary section?", choices=["y", "n"], default="y"
    ) == "y"

    if context:
        console.print("[dim]Context hints file found — will be considered during tailoring.[/dim]")

    # ---- Pass 1: company context (optional) ----
    company_context = ""
    if company_url:
        try:
            from . import scraper as _scraper
            with console.status("[cyan]Fetching company context...[/cyan]", spinner="dots"):
                company_context, ctx_tokens = _scraper.fetch_company_context(company_url, model)
            token_steps.append(("Company context", ctx_tokens[0], ctx_tokens[1]))
        except Exception as e:
            console.print(f"[yellow]Company context fetch failed ({e}) — skipping.[/yellow]")

    # ---- Pass 1: Role Analyst ----
    console.print()
    strategy_parts: list[str] = []
    try:
        with console.status("[cyan]Analysing role...[/cyan]", spinner="dots"):
            for chunk in llm.analyze_role(job_description, model, company_context or None):
                strategy_parts.append(chunk)
    except llm.LLMError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    strategy = "".join(strategy_parts).strip()
    _analyst_co = f"\n\n=== COMPANY CONTEXT ===\n{company_context}" if company_context else ""
    _analyst_prompt = prompts.ROLE_ANALYST_PROMPT.format(
        job_description=job_description, company_section=_analyst_co
    )
    token_steps.append(("Role Analyst", _analyst_prompt, strategy))

    # Show strategy and let the user edit before proceeding.
    console.print(Panel(strategy, title="[bold]Role strategy[/bold] — review and edit if needed", style="cyan"))
    if Prompt.ask("Proceed with this strategy?", choices=["y", "n", "edit"], default="y") == "edit":
        strategy = _read_multiline("Paste your edited strategy:")

    # ---- Pass 2: Resume Tailor ----
    tailored_parts: list[str] = []
    try:
        with console.status(
            "[cyan]Tailoring your resume...[/cyan]", spinner="dots"
        ):
            for chunk in llm.tailor_resume(
                base_resume, job_description, model,
                context=context, strategy=strategy
            ):
                tailored_parts.append(chunk)
    except llm.LLMError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    tailored_body = "".join(tailored_parts).strip()
    _ctx_section = (
        "\n- You have been given OPTIONAL CONTEXT below. "
        "Include items from it only if they genuinely strengthen this application for this specific role. "
        "Omit anything that isn't relevant."
    ) if context else ""
    _tailor_prompt = prompts.TAILOR_RESUME_PROMPT.format(
        resume=base_resume, job_description=job_description, context_section=_ctx_section
    )
    if strategy:
        _tailor_prompt += f"\n\n=== POSITIONING STRATEGY (follow this closely) ===\n{strategy}\n"
    if context:
        _tailor_prompt += f"\n\n=== OPTIONAL CONTEXT (include only if relevant) ===\n{context}\n"
    token_steps.append(("Resume Tailor", _tailor_prompt, tailored_body))

    # Optionally generate a per-job profile summary.
    profile_summary = ""
    if want_summary:
        summary_parts: list[str] = []
        try:
            with console.status(
                "[cyan]Generating profile summary...[/cyan]", spinner="dots"
            ):
                for chunk in llm.get_profile_summary(base_resume, job_description, model):
                    summary_parts.append(chunk)
        except llm.LLMError as e:
            console.print(f"[yellow]Profile summary failed ({e}) — skipping.[/yellow]")
        profile_summary = "".join(summary_parts).strip()
        if profile_summary:
            _ps_prompt = prompts.PROFILE_SUMMARY_PROMPT.format(
                resume=base_resume, job_description=job_description
            )
            token_steps.append(("Profile Summary", _ps_prompt, profile_summary))

    # Assemble the final resume: static profile header + optional summary + tailored body.
    resume_sections = []
    if profile:
        resume_sections.append(_profile_header_markdown(profile))
    if profile_summary:
        resume_sections.append(f"## Profile\n\n{profile_summary}")
    resume_sections.append(tailored_body)
    tailored = "\n\n".join(resume_sections)

    # Fit summary (the internal reviewer note — not in the resume itself).
    fit_parts: list[str] = []
    try:
        with console.status(
            "[cyan]Generating fit summary...[/cyan]", spinner="dots"
        ):
            for chunk in llm.get_fit_summary(base_resume, job_description, model):
                fit_parts.append(chunk)
    except llm.LLMError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    fit_summary = "".join(fit_parts).strip()
    _fit_prompt = prompts.FIT_SUMMARY_PROMPT.format(
        resume=base_resume, job_description=job_description
    )
    token_steps.append(("Fit Summary", _fit_prompt, fit_summary))

    # Persist the job (auto-assigns id + dates).
    store = get_store()
    job = Job(
        id="",
        title=title,
        company=company,
        date_added="",
        date_updated="",
        status="tailored",
        source_url=source_url or None,
        fit_summary=fit_summary or None,
    )
    try:
        job = store.save_job(job)
    except TrackerError as e:
        console.print(f"[red]Failed to save job:[/red] {e}")
        sys.exit(1)

    # Build the application package folder (md + html + pdf + manifest).
    try:
        with console.status(
            "[cyan]Rendering HTML + PDF and assembling package...[/cyan]",
            spinner="dots",
        ):
            folder = package.assemble(
                job, tailored, fit_summary,
                strategy=strategy or None,
                company_context=company_context or None,
            )
    except Exception as e:
        console.print(f"[red]Package assembly failed:[/red] {e}")
        sys.exit(1)

    # Record the package folder back on the tracker row.
    try:
        job = store.update_job(job.id, package_folder=str(folder))
    except TrackerError as e:
        console.print(
            f"[yellow]Saved package but failed to record folder path:[/yellow] {e}"
        )

    console.print()
    console.print(
        Panel(
            fit_summary or "[dim](no summary)[/dim]",
            title="Fit Summary",
            style="magenta",
        )
    )
    console.print(f"\n[green]Package folder:[/green] [bold]{folder}[/bold]")
    console.print(f"[green]Tracked as:[/green] [bold]{job.id}[/bold]")

    # Token usage estimate — per-step breakdown.
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        total_in = total_out = 0
        step_lines = []
        for step_name, prompt_text, output_text in token_steps:
            s_in = len(enc.encode(prompt_text))
            s_out = len(enc.encode(output_text))
            total_in += s_in
            total_out += s_out
            step_lines.append(f"  {step_name:<20} {s_in:>6,} in + {s_out:>6,} out")
        total = total_in + total_out
        costs = [
            ("Gemini 2.0 Flash",  0.10,  0.40),
            ("GPT-4o mini",       0.15,  0.60),
            ("Claude Haiku 3.5",  0.80,  4.00),
            ("GPT-4o",            2.50, 10.00),
            ("Claude Sonnet 3.7", 3.00, 15.00),
            ("Gemini 2.5 Pro",    2.50, 15.00),
            ("o4-mini",           1.10,  4.40),
            ("Claude Opus 4",    15.00, 75.00),
            ("o3",               10.00, 40.00),
        ]
        cost_lines = "\n".join(
            f"  {name:<22} ${(total_in * inp + total_out * out) / 1_000_000:.4f}"
            for name, inp, out in costs
        )
        breakdown = "\n".join(step_lines)
        console.print(
            f"\n[dim]Token usage (tiktoken cl100k):\n"
            f"{breakdown}\n"
            f"  {'─' * 40}\n"
            f"  {'Total':<20} {total_in:>6,} in + {total_out:>6,} out = {total:,}\n\n"
            f"  API cost estimate:\n{cost_lines}[/dim]"
        )
    except Exception:
        pass


# ---------- list / view / status ----------

@main.command(name="list")
def list_jobs() -> None:
    """List all tracked jobs."""
    try:
        jobs = get_store().load_jobs()
    except TrackerError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    if not jobs:
        console.print("[dim]No jobs tracked yet. Run `applycling add`.[/dim]")
        return

    table = Table(title="Tracked Jobs")
    table.add_column("ID", style="cyan")
    table.add_column("Company", style="bold")
    table.add_column("Title")
    table.add_column("Date")
    table.add_column("Status")
    for j in jobs:
        style = STATUS_STYLES.get(j.status, "white")
        table.add_row(
            j.id or "?",
            j.company or "?",
            j.title or "?",
            (j.date_added or "?").split("T")[0],
            f"[{style}]{j.status}[/{style}]",
        )
    console.print(table)


@main.command()
@click.argument("job_id")
def status(job_id: str) -> None:
    """Update the status of a tracked job."""
    store = get_store()
    try:
        job = store.load_job(job_id)
    except TrackerError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    console.print(
        f"Current status for [bold]{job.id}[/bold] "
        f"({job.company or '?'} — {job.title or '?'}): "
        f"[{STATUS_STYLES.get(job.status, 'white')}]{job.status}[/]"
    )
    new_status = Prompt.ask(
        "New status", choices=list(STATUSES), default=job.status
    )
    try:
        store.update_job(job_id, status=new_status)
    except TrackerError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    console.print(f"[green]Updated[/green] {job_id} → [bold]{new_status}[/bold]")


@main.command()
@click.argument("job_id")
def view(job_id: str) -> None:
    """View the tailored resume for a job."""
    try:
        job = get_store().load_job(job_id)
    except TrackerError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    folder = job.package_folder
    if not folder:
        console.print("[red]No package folder recorded for this job.[/red]")
        sys.exit(1)
    md_path = Path(folder) / "resume.md"
    if not md_path.exists():
        console.print(f"[red]Tailored resume file is missing:[/red] {md_path}")
        sys.exit(1)
    text = md_path.read_text(encoding="utf-8")
    console.print(
        Panel(
            f"[bold]{job.company or '?'}[/bold] — {job.title or '?'}  "
            f"[dim]({job.id})[/dim]",
            style="cyan",
        )
    )
    console.print(Markdown(text))


# ---------- notion subgroup ----------

@main.group()
def notion() -> None:
    """Notion integration commands."""


@notion.command(name="connect")
def notion_connect_cmd() -> None:
    """Interactive setup for Notion as the job tracker backend."""
    notion_connect.run()


if __name__ == "__main__":
    main()
