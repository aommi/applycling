"""Interactive wizard to connect applycling to a Notion workspace.

Creates the Job Tracker database under a user-supplied parent page and saves
the integration secret + database id to data/notion.json.
"""

from __future__ import annotations

import re
import sys
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from .tracker import notion_store

console = Console()

# Database schema. Property names mirror notion_store.PROP_* constants.
DATABASE_SCHEMA: dict[str, Any] = {
    notion_store.PROP_TITLE: {"title": {}},
    notion_store.PROP_JOB_ID: {"rich_text": {}},
    notion_store.PROP_COMPANY: {"rich_text": {}},
    notion_store.PROP_STATUS: {
        "select": {
            "options": [
                {"name": "tailored", "color": "blue"},
                {"name": "applied", "color": "yellow"},
                {"name": "interview", "color": "green"},
                {"name": "offer", "color": "purple"},
                {"name": "rejected", "color": "gray"},
            ]
        }
    },
    notion_store.PROP_SOURCE_URL: {"url": {}},
    notion_store.PROP_APPLICATION_URL: {"url": {}},
    notion_store.PROP_FIT_SUMMARY: {"rich_text": {}},
    notion_store.PROP_PACKAGE_FOLDER: {"rich_text": {}},
    notion_store.PROP_DATE_ADDED: {"date": {}},
    notion_store.PROP_DATE_UPDATED: {"date": {}},
}


def _extract_page_id(url_or_id: str) -> str:
    """Pull a Notion page id from a full URL or accept a raw id.

    Notion URLs end with a 32-hex chunk like
    https://www.notion.so/My-Page-33d53a51362880acbed6f357f664eba7
    """
    s = url_or_id.strip()
    matches = re.findall(r"[0-9a-fA-F]{32}", s.replace("-", ""))
    if not matches:
        raise ValueError(
            "Could not find a Notion page id in that input. "
            "Paste the full page URL or a 32-character page id."
        )
    raw = matches[-1]
    return f"{raw[0:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:32]}"


def run() -> None:
    """Interactive Notion connect flow. Called from `applycling notion connect`."""
    console.print(Panel.fit("[bold]applycling — Notion connect[/bold]", style="cyan"))
    console.print(
        "This wizard will create a Job Tracker database in your Notion workspace.\n"
    )
    console.print(
        "[dim]Before you continue:[/dim]\n"
        "  1. Create an integration at "
        "[link=https://www.notion.so/my-integrations]https://www.notion.so/my-integrations[/link]\n"
        "  2. Copy the Internal Integration Secret\n"
        "  3. Open the Notion page where the tracker should live\n"
        "  4. Click ··· → Connections → add your integration\n"
    )

    secret = Prompt.ask("Integration secret", password=True)
    page_url = Prompt.ask("Parent page URL or id")

    try:
        parent_page_id = _extract_page_id(page_url)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)

    try:
        from notion_client import Client
    except ImportError:
        console.print(
            "[red]notion-client is not installed.[/red] Run "
            "[bold]pip install notion-client[/bold] inside your venv."
        )
        sys.exit(1)

    client = Client(auth=secret)

    console.print("\n[cyan]Creating the Job Tracker database…[/cyan]")
    try:
        db = client.databases.create(
            parent={"type": "page_id", "page_id": parent_page_id},
            title=[{"type": "text", "text": {"content": "Job Tracker"}}],
            icon={"type": "emoji", "emoji": "💼"},
            properties=DATABASE_SCHEMA,
        )
    except Exception as e:
        console.print(f"[red]Failed to create database:[/red] {e}")
        console.print(
            "\n[dim]Common causes:[/dim]\n"
            "  • The integration is not shared with the parent page (··· → Connections)\n"
            "  • The integration secret is wrong\n"
            "  • The page id couldn't be found in your workspace"
        )
        sys.exit(1)

    database_id = db["id"]
    notion_store.save_config(
        secret=secret,
        database_id=database_id,
        parent_page_id=parent_page_id,
    )

    console.print(
        Panel.fit(
            f"[green]Connected![/green]\n"
            f"Database id: [bold]{database_id}[/bold]\n"
            f"Saved to: [bold]data/notion.json[/bold]\n\n"
            f"Open Notion to see the new Job Tracker database.\n"
            f"Next: run [bold]applycling add[/bold] — your job will land here.",
            style="green",
        )
    )
    console.print(
        "\n[dim]One manual step: the Notion API can't create database views, so add a "
        "Review Queue view yourself. Open the database, click + Add view, choose Table, "
        "name it 'Review Queue', and add filter: Status equals 'tailored'.[/dim]"
    )
