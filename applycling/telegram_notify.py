"""Telegram Bot API client for applycling status notifications."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path


class TelegramError(Exception):
    pass


class TelegramNotifier:
    """Send text messages and documents to a Telegram chat via Bot API."""

    def __init__(self, token: str, chat_id: str) -> None:
        self._base = f"https://api.telegram.org/bot{token}"
        self._chat_id = chat_id

    def notify(self, text: str) -> None:
        """Send a plain-text message."""
        self._post("sendMessage", {"chat_id": self._chat_id, "text": text})

    def send_document(self, path: Path, caption: str = "") -> None:
        """Upload a file to the chat."""
        boundary = "applycling_boundary_8f3a"
        parts: list[bytes] = []

        def _field(name: str, value: str) -> bytes:
            return (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                f"{value}\r\n"
            ).encode()

        parts.append(_field("chat_id", self._chat_id))
        if caption:
            parts.append(_field("caption", caption))

        file_bytes = path.read_bytes()
        parts.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="document"; filename="{path.name}"\r\n'
                "Content-Type: application/octet-stream\r\n\r\n"
            ).encode()
            + file_bytes
            + b"\r\n"
        )
        parts.append(f"--{boundary}--\r\n".encode())

        body = b"".join(parts)
        req = urllib.request.Request(
            f"{self._base}/sendDocument",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            raise TelegramError(f"sendDocument HTTP {exc.code}: {exc.read().decode(errors='replace')}") from exc
        if not result.get("ok"):
            raise TelegramError(f"sendDocument failed: {result}")

    def _post(self, method: str, payload: dict) -> dict:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{self._base}/{method}",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            raise TelegramError(f"{method} HTTP {exc.code}: {exc.read().decode(errors='replace')}") from exc
        if not result.get("ok"):
            raise TelegramError(f"{method} failed: {result}")
        return result


# ── Multi-tenant helpers ─────────────────────────────────────────────

def _get_chat_id_for_user(user_id: str) -> int | None:
    """Look up a user's Telegram chat_id from the database."""
    import os
    import psycopg

    url = os.environ.get("DATABASE_URL")
    if not url:
        return None

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT chat_id FROM users WHERE id = %s AND deleted_at IS NULL",
                (user_id,),
            )
            row = cur.fetchone()
    return row[0] if row and row[0] else None


def notify_to_user(token: str, user_id: str, text: str) -> bool:
    """Send a Telegram message to a specific user via their stored chat_id."""
    chat_id = _get_chat_id_for_user(user_id)
    if not chat_id:
        import sys
        print(
            f"[telegram] No chat_id for user {user_id}, cannot notify.",
            file=sys.stderr, flush=True,
        )
        return False
    notifier = TelegramNotifier(token, str(chat_id))
    try:
        notifier.notify(text)
        return True
    except TelegramError as e:
        import sys
        print(
            f"[telegram] Failed to notify user {user_id}: {e}",
            file=sys.stderr, flush=True,
        )
        return False


def notify_error_to_user(token: str, user_id: str, job_url: str, error: str) -> bool:
    """Send a user-friendly error message for a failed pipeline generation."""
    msg = (
        "Sorry, I couldn't generate an application package for that job.\n\n"
        f"URL: {job_url}\n"
        f"Error: {str(error)[:200]}\n\n"
        "Try a different job URL or contact Amirali for help."
    )
    return notify_to_user(token, user_id, msg)
