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

from . import llm, notion_connect, package, pdf_import, storage
from .tracker import STATUSES, Job, TrackerError, get_store

console = Console()

STATUS_STYLES = {
    "tailored": "blue",
    "applied": "yellow",
    "interview": "green",
    "offer": "bold green",
    "rejected": "dim",
}


def _read_multiline(prompt_text: str) -> str:
    console.print(f"[bold]{prompt_text}[/bold]")
    console.print("[dim](end with a single line containing just `---`)[/dim]")
    lines: list[str] = []
    while True:
        try:
            line = input()
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

    title = Prompt.ask("Job title")
    company = Prompt.ask("Company name")
    source_url = Prompt.ask("Source URL (optional)", default="")
    job_description = _read_multiline("Paste the job description below:")
    if not job_description:
        console.print("[red]Empty job description — aborting.[/red]")
        sys.exit(1)

    # Tailor the resume.
    console.print()
    tailored_parts: list[str] = []
    try:
        with console.status(
            "[cyan]Tailoring your resume...[/cyan]", spinner="dots"
        ):
            for chunk in llm.tailor_resume(base_resume, job_description, model):
                tailored_parts.append(chunk)
    except llm.LLMError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    tailored = "".join(tailored_parts).strip()

    # Fit summary.
    summary_parts: list[str] = []
    try:
        with console.status(
            "[cyan]Generating fit summary...[/cyan]", spinner="dots"
        ):
            for chunk in llm.get_fit_summary(base_resume, job_description, model):
                summary_parts.append(chunk)
    except llm.LLMError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    fit_summary = "".join(summary_parts).strip()

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
            folder = package.assemble(job, tailored, fit_summary)
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
