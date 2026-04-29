"""Canonical job workflow states for applycling.

Import from here. Never hardcode status strings.
One state machine for all paths: UI, CLI, Telegram, API, MCP.
"""

from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class StatusAction:
    target: str
    label: str
    css_class: str


@dataclass(frozen=True)
class Status:
    value: str
    label: str
    color: str
    actions: tuple[StatusAction, ...] = ()
    is_system: bool = False  # system-managed, no user actions


STATES: tuple[Status, ...] = (
    Status("new", "New", "#6b7280", actions=(
        StatusAction("generating", "Regenerate", "btn-start"),
        StatusAction("archived", "Archive", "btn-skip"),
    )),
    Status("generating", "Generating", "#3b82f6", is_system=True),
    Status("reviewing", "Reviewing", "#f59e0b", actions=(
        StatusAction("reviewed", "Ready to Apply", "btn-apply"),
        StatusAction("generating", "Regenerate", "btn-start"),
        StatusAction("archived", "Archive", "btn-skip"),
    )),
    Status("reviewed", "Reviewed", "#10b981", actions=(
        StatusAction("applied", "Mark Applied", "btn-apply"),
        StatusAction("archived", "Archive", "btn-skip"),
    )),
    Status("applied", "Applied", "#8b5cf6", actions=(
        StatusAction("interviewing", "Interviewing", "btn-start"),
        StatusAction("offered", "Offered", "btn-apply"),
        StatusAction("accepted", "Accepted", "btn-apply"),
        StatusAction("rejected", "Rejected", "btn-skip"),
        StatusAction("archived", "Archive", "btn-skip"),
    )),
    Status("interviewing", "Interviewing", "#ec4899", actions=(
        StatusAction("offered", "Offered", "btn-apply"),
        StatusAction("accepted", "Accepted", "btn-apply"),
        StatusAction("rejected", "Rejected", "btn-skip"),
        StatusAction("archived", "Archive", "btn-skip"),
    )),
    Status("offered", "Offered", "#22c55e", actions=(
        StatusAction("accepted", "Accept Offer", "btn-apply"),
        StatusAction("archived", "Decline", "btn-skip"),
    )),
    Status("accepted", "Accepted", "#fbbf24", actions=(
        StatusAction("archived", "Archive", "btn-skip"),
    )),
    Status("rejected", "Rejected", "#ef4444", actions=(
        StatusAction("archived", "Archive", "btn-skip"),
    )),
    Status("failed", "Failed", "#dc2626"),
    Status("archived", "Archived", "#374151", actions=(
        StatusAction("reviewing", "Reopen", "btn-reopen"),
    )),
)

STATUS_VALUES: tuple[str, ...] = tuple(s.value for s in STATES)
STATUS_BY_VALUE: dict[str, Status] = {s.value: s for s in STATES}
DEFAULT_INITIAL_STATUS: str = "new"

# Allowed transitions — frozenset prevents accidental mutation
TRANSITIONS: dict[str, frozenset[str]] = {
    "new":          frozenset({"generating", "archived"}),
    "generating":   frozenset({"reviewing", "failed"}),
    "reviewing":    frozenset({"reviewed", "archived", "generating"}),
    "reviewed":     frozenset({"applied", "archived"}),
    "applied":      frozenset({"interviewing", "offered", "accepted", "rejected", "archived"}),
    "interviewing": frozenset({"offered", "accepted", "rejected", "archived"}),
    "offered":      frozenset({"accepted", "archived"}),
    "accepted":     frozenset({"archived"}),
    "rejected":     frozenset({"archived"}),
    "failed":       frozenset({"new"}),
    "archived":     frozenset({"reviewing", "new"}),
}

# pipeline_runs keeps independent vocabulary (run audit ≠ job lifecycle).

# Legacy migration — maps old CLI AND old workbench statuses to canonical
OLD_TO_NEW: dict[str, str] = {
    "tailored":  "reviewing",
    "interview": "interviewing",
    "offer":     "offered",
    # applied, rejected, failed are identity — no mapping needed
    "inbox":     "new",
    "running":   "generating",
    "generated": "reviewing",
    "skipped":   "archived",
}

LEGACY_STATUS_VALUES: frozenset[str] = frozenset(OLD_TO_NEW.keys())


def migrate_old_status(status: str) -> str:
    return OLD_TO_NEW.get(status, status)


def status_color(value: str) -> str:
    s = STATUS_BY_VALUE.get(value)
    return s.color if s else "#6b7280"


def status_label(value: str) -> str:
    s = STATUS_BY_VALUE.get(value)
    return s.label if s else value


def job_actions(status_value: str) -> tuple[StatusAction, ...]:
    s = STATUS_BY_VALUE.get(status_value)
    return s.actions if s else ()


def can_transition(from_status: str, to_status: str) -> bool:
    if from_status == to_status:
        return True
    return to_status in TRANSITIONS.get(from_status, frozenset())


def assert_valid_status(value: str) -> None:
    if value not in STATUS_BY_VALUE:
        raise ValueError(f"Unknown status '{value}'. Valid: {STATUS_VALUES}")
