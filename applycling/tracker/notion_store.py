"""Notion-backed implementation of TrackerStore.

The schema is created by `applycling notion connect`. This module just reads
and writes rows in that database. Property names are constants here so the
wizard and the store stay in sync.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Optional

from . import ALLOWED_UPDATE_FIELDS, Job, TrackerError, TrackerStore

ROOT = Path(__file__).resolve().parent.parent.parent
NOTION_CONFIG_PATH = ROOT / "data" / "notion.json"

# Property names. The connect wizard creates the database with exactly these
# names; this module reads/writes them. Keep both in sync.
PROP_TITLE = "Title"
PROP_JOB_ID = "Job ID"
PROP_COMPANY = "Company"
PROP_STATUS = "Status"
PROP_SOURCE_URL = "Source URL"
PROP_APPLICATION_URL = "Application URL"
PROP_FIT_SUMMARY = "Fit Summary"
PROP_PACKAGE_FOLDER = "Package Folder"
PROP_DATE_ADDED = "Date Added"
PROP_DATE_UPDATED = "Date Updated"


def is_connected() -> bool:
    """Return True if local Notion config exists and looks valid."""
    if not NOTION_CONFIG_PATH.exists():
        return False
    try:
        cfg = json.loads(NOTION_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(cfg.get("secret")) and bool(cfg.get("database_id"))


def load_config() -> dict[str, Any]:
    if not NOTION_CONFIG_PATH.exists():
        raise TrackerError(
            "Notion is not connected. Run `applycling notion connect` first."
        )
    return json.loads(NOTION_CONFIG_PATH.read_text(encoding="utf-8"))


def save_config(secret: str, database_id: str, parent_page_id: str) -> None:
    NOTION_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    NOTION_CONFIG_PATH.write_text(
        json.dumps(
            {
                "secret": secret,
                "database_id": database_id,
                "parent_page_id": parent_page_id,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _rich_text(value: Optional[str]) -> list[dict[str, Any]]:
    if value is None or value == "":
        return []
    # Notion rich_text is capped at 2000 chars per text block.
    return [{"type": "text", "text": {"content": value[:2000]}}]


def _read_rich_text(prop: dict[str, Any]) -> Optional[str]:
    rt = prop.get("rich_text") or []
    if not rt:
        return None
    return "".join(part.get("plain_text", "") for part in rt) or None


def _read_title(prop: dict[str, Any]) -> str:
    title = prop.get("title") or []
    return "".join(part.get("plain_text", "") for part in title)


class NotionStore(TrackerStore):
    def __init__(self) -> None:
        try:
            from notion_client import Client
        except ImportError as e:
            raise TrackerError(
                "notion-client is not installed. "
                "Run `pip install notion-client` inside your venv."
            ) from e
        cfg = load_config()
        self.secret = cfg["secret"]
        self.database_id = cfg["database_id"]
        self.client = Client(auth=self.secret)

    # ---- mapping helpers ----

    def _job_to_properties(self, job: Job) -> dict[str, Any]:
        props: dict[str, Any] = {
            PROP_TITLE: {"title": _rich_text(job.title)},
            PROP_JOB_ID: {"rich_text": _rich_text(job.id)},
            PROP_COMPANY: {"rich_text": _rich_text(job.company)},
            PROP_STATUS: {"select": {"name": job.status}},
            PROP_DATE_ADDED: {"date": {"start": job.date_added}},
            PROP_DATE_UPDATED: {"date": {"start": job.date_updated}},
        }
        if job.source_url:
            props[PROP_SOURCE_URL] = {"url": job.source_url}
        if job.application_url:
            props[PROP_APPLICATION_URL] = {"url": job.application_url}
        if job.fit_summary:
            props[PROP_FIT_SUMMARY] = {"rich_text": _rich_text(job.fit_summary)}
        if job.package_folder:
            props[PROP_PACKAGE_FOLDER] = {
                "rich_text": _rich_text(job.package_folder)
            }
        return props

    def _page_to_job(self, page: dict[str, Any]) -> Job:
        props = page.get("properties", {})

        def _opt_url(key: str) -> Optional[str]:
            return props.get(key, {}).get("url")

        def _opt_rt(key: str) -> Optional[str]:
            return _read_rich_text(props.get(key, {}))

        def _opt_select(key: str) -> Optional[str]:
            sel = props.get(key, {}).get("select")
            return sel.get("name") if sel else None

        def _opt_date(key: str) -> Optional[str]:
            d = props.get(key, {}).get("date")
            return d.get("start") if d else None

        return Job(
            id=_opt_rt(PROP_JOB_ID) or "",
            title=_read_title(props.get(PROP_TITLE, {})),
            company=_opt_rt(PROP_COMPANY) or "",
            date_added=_opt_date(PROP_DATE_ADDED) or "",
            date_updated=_opt_date(PROP_DATE_UPDATED) or "",
            status=_opt_select(PROP_STATUS) or "tailored",
            source_url=_opt_url(PROP_SOURCE_URL),
            application_url=_opt_url(PROP_APPLICATION_URL),
            fit_summary=_opt_rt(PROP_FIT_SUMMARY),
            package_folder=_opt_rt(PROP_PACKAGE_FOLDER),
        )

    # ---- internal queries ----

    def _next_id(self) -> str:
        max_n = 0
        cursor: Optional[str] = None
        while True:
            resp = self.client.databases.query(
                database_id=self.database_id,
                start_cursor=cursor,
                page_size=100,
            )
            for page in resp.get("results", []):
                jid = _read_rich_text(
                    page.get("properties", {}).get(PROP_JOB_ID, {})
                )
                if jid and jid.startswith("job_"):
                    try:
                        n = int(jid.split("_", 1)[1])
                    except (IndexError, ValueError):
                        continue
                    if n > max_n:
                        max_n = n
            if not resp.get("has_more"):
                break
            cursor = resp.get("next_cursor")
        return f"job_{max_n + 1:03d}"

    def _find_page_by_id(self, job_id: str) -> Optional[dict[str, Any]]:
        resp = self.client.databases.query(
            database_id=self.database_id,
            filter={
                "property": PROP_JOB_ID,
                "rich_text": {"equals": job_id},
            },
            page_size=1,
        )
        results = resp.get("results", [])
        return results[0] if results else None

    # ---- TrackerStore interface ----

    def save_job(self, job: Job) -> Job:
        if not job.id:
            job.id = self._next_id()
        now = _now()
        if not job.date_added:
            job.date_added = now
        if not job.date_updated:
            job.date_updated = now
        try:
            self.client.pages.create(
                parent={"database_id": self.database_id},
                properties=self._job_to_properties(job),
            )
        except Exception as e:
            raise TrackerError(f"Failed to save job to Notion: {e}") from e
        return job

    def load_jobs(self) -> list[Job]:
        jobs: list[Job] = []
        cursor: Optional[str] = None
        try:
            while True:
                resp = self.client.databases.query(
                    database_id=self.database_id,
                    start_cursor=cursor,
                    page_size=100,
                    sorts=[
                        {
                            "property": PROP_DATE_ADDED,
                            "direction": "descending",
                        }
                    ],
                )
                for page in resp.get("results", []):
                    jobs.append(self._page_to_job(page))
                if not resp.get("has_more"):
                    break
                cursor = resp.get("next_cursor")
        except Exception as e:
            raise TrackerError(f"Failed to load jobs from Notion: {e}") from e
        return jobs

    def load_job(self, job_id: str) -> Job:
        page = self._find_page_by_id(job_id)
        if page is None:
            raise TrackerError(f"No job found with id '{job_id}'.")
        return self._page_to_job(page)

    def update_job(self, job_id: str, **fields: Any) -> Job:
        invalid = set(fields) - ALLOWED_UPDATE_FIELDS
        if invalid:
            raise TrackerError(
                f"Cannot update fields: {sorted(invalid)}. "
                f"Allowed: {sorted(ALLOWED_UPDATE_FIELDS)}"
            )
        page = self._find_page_by_id(job_id)
        if page is None:
            raise TrackerError(f"No job found with id '{job_id}'.")

        update_props: dict[str, Any] = {}
        if "status" in fields:
            update_props[PROP_STATUS] = {"select": {"name": fields["status"]}}
        if "source_url" in fields:
            update_props[PROP_SOURCE_URL] = {"url": fields["source_url"]}
        if "application_url" in fields:
            update_props[PROP_APPLICATION_URL] = {
                "url": fields["application_url"]
            }
        if "fit_summary" in fields:
            update_props[PROP_FIT_SUMMARY] = {
                "rich_text": _rich_text(fields["fit_summary"])
            }
        if "package_folder" in fields:
            update_props[PROP_PACKAGE_FOLDER] = {
                "rich_text": _rich_text(fields["package_folder"])
            }
        update_props[PROP_DATE_UPDATED] = {"date": {"start": _now()}}

        try:
            self.client.pages.update(
                page_id=page["id"], properties=update_props
            )
        except Exception as e:
            raise TrackerError(f"Failed to update job in Notion: {e}") from e
        return self.load_job(job_id)
