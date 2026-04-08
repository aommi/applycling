"""applycling CLI."""

from __future__ import annotations

import datetime as dt
import re
import sys

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from . import llm, storage

console = Console()

STATUSES = ["tailored", "applied", "interview", "offer", "rejected"]
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


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "untitled"


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


@main.command()
def setup() -> None:
    """First-time setup: save base resume and pick an Ollama model."""
    console.print(Panel.fit("[bold]applycling — Setup[/bold]", style="cyan"))

    resume = _read_multiline("Paste your base resume below:")
    if not resume:
        console.print("[red]Empty resume — aborting.[/red]")
        sys.exit(1)

    try:
        models = llm.get_available_models()
    except llm.LLMError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    if not models:
        console.print(
            "[red]No Ollama models installed.[/red] Try: [bold]ollama pull llama3.2[/bold]"
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
    chosen = models[int(choice) - 1]

    storage.save_resume(resume)
    storage.save_config({"model": chosen})

    console.print(
        Panel.fit(
            f"[green]Setup complete![/green]\n"
            f"Model: [bold]{chosen}[/bold]\n\n"
            f"Next: [bold]applycling add[/bold] to tailor your resume to a job.",
            style="green",
        )
    )


@main.command()
def add() -> None:
    """Add a job: paste a JD, get a tailored resume + fit summary."""
    config = _require_config()
    resume = _require_resume()
    model = config.get("model")
    if not model:
        console.print("[red]No model in config.[/red] Run setup again.")
        sys.exit(1)

    title = Prompt.ask("Job title")
    company = Prompt.ask("Company name")
    job_description = _read_multiline("Paste the job description below:")
    if not job_description:
        console.print("[red]Empty job description — aborting.[/red]")
        sys.exit(1)

    # Tailor resume (streamed) under a spinner that stops on first token.
    console.print()
    tailored_parts: list[str] = []
    try:
        with console.status("[cyan]Tailoring your resume...[/cyan]", spinner="dots"):
            stream = llm.tailor_resume(resume, job_description, model)
            for chunk in stream:
                tailored_parts.append(chunk)
    except llm.LLMError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    tailored_resume = "".join(tailored_parts).strip()

    # Fit summary
    summary_parts: list[str] = []
    try:
        with console.status("[cyan]Generating fit summary...[/cyan]", spinner="dots"):
            for chunk in llm.get_fit_summary(resume, job_description, model):
                summary_parts.append(chunk)
    except llm.LLMError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    fit_summary = "".join(summary_parts).strip()

    # Save tailored resume
    today = dt.date.today().isoformat()
    filename = f"{_slugify(company)}-{_slugify(title)}-{today}.md"
    output_path = storage.OUTPUT_DIR / filename
    storage.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_text(tailored_resume, encoding="utf-8")

    job = storage.save_job(
        {
            "title": title,
            "company": company,
            "date_added": today,
            "status": "tailored",
            "output_file": str(output_path),
        }
    )

    console.print()
    console.print(
        Panel(fit_summary or "[dim](no summary returned)[/dim]", title="Fit Summary", style="magenta")
    )
    console.print(
        f"\n[green]Tailored resume saved to:[/green] [bold]{output_path}[/bold]"
    )
    console.print(f"[green]Tracked as:[/green] [bold]{job['id']}[/bold]")


@main.command(name="list")
def list_jobs() -> None:
    """List all tracked jobs."""
    jobs = storage.load_jobs()
    if not jobs:
        console.print("[dim]No jobs tracked yet. Run `applycling add`.[/dim]")
        return

    table = Table(title="Tracked Jobs")
    table.add_column("ID", style="cyan")
    table.add_column("Company", style="bold")
    table.add_column("Title")
    table.add_column("Date")
    table.add_column("Status")

    for job in jobs:
        status = job.get("status", "tailored")
        style = STATUS_STYLES.get(status, "white")
        table.add_row(
            job.get("id", "?"),
            job.get("company", "?"),
            job.get("title", "?"),
            job.get("date_added", "?"),
            f"[{style}]{status}[/{style}]",
        )
    console.print(table)


@main.command()
@click.argument("job_id")
def status(job_id: str) -> None:
    """Update the status of a tracked job."""
    try:
        job = storage.load_job(job_id)
    except storage.StorageError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    console.print(
        f"Current status for [bold]{job['id']}[/bold] "
        f"({job.get('company', '?')} — {job.get('title', '?')}): "
        f"[{STATUS_STYLES.get(job.get('status', 'tailored'), 'white')}]"
        f"{job.get('status', 'tailored')}[/]"
    )
    new_status = Prompt.ask(
        "New status",
        choices=STATUSES,
        default=job.get("status", "tailored"),
    )
    storage.update_job_status(job_id, new_status)
    console.print(f"[green]Updated[/green] {job_id} → [bold]{new_status}[/bold]")


@main.command()
@click.argument("job_id")
def view(job_id: str) -> None:
    """View the tailored resume for a job."""
    try:
        job = storage.load_job(job_id)
    except storage.StorageError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    output_file = job.get("output_file")
    if not output_file:
        console.print("[red]No output file recorded for this job.[/red]")
        sys.exit(1)

    from pathlib import Path

    path = Path(output_file)
    if not path.exists():
        console.print(f"[red]Tailored resume file is missing:[/red] {path}")
        sys.exit(1)

    text = path.read_text(encoding="utf-8")
    console.print(
        Panel(
            f"[bold]{job.get('company', '?')}[/bold] — {job.get('title', '?')}  "
            f"[dim]({job['id']})[/dim]",
            style="cyan",
        )
    )
    console.print(Markdown(text))


if __name__ == "__main__":
    main()
