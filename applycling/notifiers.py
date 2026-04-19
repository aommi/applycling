"""Notifier protocol — shared interface for all messaging channel integrations."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class Notifier(Protocol):
    """Any object that can send text messages and file attachments."""

    def notify(self, text: str) -> None:
        """Send a text message to the user."""
        ...

    def send_document(self, path: Path, caption: str = "") -> None:
        """Upload a file with an optional caption."""
        ...
