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
