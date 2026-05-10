"""Async IMAP client with XOAUTH2 authentication."""
from __future__ import annotations

import email
from email.header import decode_header
from email.message import Message
from email.utils import parsedate_to_datetime
import logging
import re
from typing import Any

import aioimaplib

_LOGGER = logging.getLogger(__name__)



def _decode_header_value(value: str | None) -> str:
    """Decode RFC 2047 encoded words in an email header value."""
    if not value:
        return ""
    parts = decode_header(value)
    result = []
    for part, charset in parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(str(part))
    return "".join(result)


def _get_text_body(msg: Message, max_length: int = 500) -> str:
    """Extract plain-text body preview from an email message."""
    if msg.is_multipart():
        for part in msg.walk():
            if (
                part.get_content_type() == "text/plain"
                and not part.get("Content-Disposition")
            ):
                try:
                    payload = part.get_payload(decode=True)
                    if isinstance(payload, bytes):
                        charset = part.get_content_charset() or "utf-8"
                        return payload.decode(charset, errors="replace")[:max_length]
                except Exception:  # noqa: BLE001
                    pass
    else:
        try:
            payload = msg.get_payload(decode=True)
            if isinstance(payload, bytes):
                charset = msg.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")[:max_length]
        except Exception:  # noqa: BLE001
            pass
    return ""


def parse_email_bytes(raw: bytes, uid: str) -> dict[str, Any]:
    """Parse raw email bytes into a structured dictionary."""
    msg = email.message_from_bytes(raw)

    date_str = msg.get("Date", "")
    date_iso: str | None = None
    if date_str:
        try:
            date_iso = parsedate_to_datetime(date_str).isoformat()
        except Exception:  # noqa: BLE001
            date_iso = date_str

    return {
        "uid": uid,
        "subject": _decode_header_value(msg.get("Subject")),
        "sender": _decode_header_value(msg.get("From", "")),
        "date": date_iso,
        "message_id": (msg.get("Message-ID") or "").strip(),
        "preview": _get_text_body(msg, 500).strip()[:200],
    }


def _extract_literal_bytes(lines: list) -> bytes | None:
    """Pull the raw message bytes out of an aioimaplib fetch response."""
    best: bytes | None = None
    for item in lines:
        if isinstance(item, (bytes, bytearray)):
            b = bytes(item)
            if best is None or len(b) > len(best):
                best = b
    # Discard obviously-short status lines (closing parens, etc.)
    if best is not None and len(best) < 50:
        return None
    return best


class ImapAuthError(Exception):
    """Raised when XOAUTH2 authentication fails."""


class ImapClientError(Exception):
    """Raised on general IMAP operation errors."""


class ImapClient:
    """Async IMAP client that authenticates via XOAUTH2."""

    def __init__(self, host: str, port: int = 993) -> None:
        self._host = host
        self._port = port
        self._client: aioimaplib.IMAP4_SSL | None = None

    async def __aenter__(self) -> ImapClient:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.disconnect()

    async def connect(self, user: str, access_token: str) -> None:
        """Open a TLS connection and authenticate via XOAUTH2."""
        client = aioimaplib.IMAP4_SSL(host=self._host, port=self._port)
        await client.wait_hello_from_server()

        response = await client.xoauth2(user, access_token)
        if response.result != "OK":
            await client.logout()
            raise ImapAuthError(
                f"XOAUTH2 authentication failed: {response.lines}"
            )

        self._client = client

    async def disconnect(self) -> None:
        """Log out and close the connection."""
        if self._client is not None:
            try:
                await self._client.logout()
            except Exception:  # noqa: BLE001
                pass
            finally:
                self._client = None

    async def get_folder_status(self, folder: str) -> dict[str, int]:
        """Return MESSAGES and UNSEEN counts for a folder."""
        if self._client is None:
            raise ImapClientError("Not connected")

        response = await self._client.status(folder, "(MESSAGES UNSEEN)")
        result = {"messages": 0, "unseen": 0}
        if response.result != "OK":
            return result

        for line in response.lines:
            text = line.decode() if isinstance(line, bytes) else str(line)
            for key in ("MESSAGES", "UNSEEN"):
                m = re.search(rf"{key} (\d+)", text)
                if m:
                    result[key.lower()] = int(m.group(1))

        return result

    async def search_emails(
        self,
        folder: str,
        criteria: str = "ALL",
        max_results: int = 10,
    ) -> list[dict[str, Any]]:
        """IMAP criteria search."""
        if self._client is None:
            raise ImapClientError("Not connected")

        exam_resp = await self._client.select(folder)
        if exam_resp.result != "OK":
            raise ImapClientError(
                f"Cannot open folder '{folder}': {exam_resp.lines}"
            )

        response = await self._client.uid_search(*criteria.split(), charset=None)
        if response.result != "OK" or not response.lines:
            return []

        uid_line = response.lines[0]
        if isinstance(uid_line, bytes):
            uid_line = uid_line.decode()
        uids = uid_line.strip().split()
        if not uids:
            return []

        # UIDs are in ascending order – take the most recent N
        recent = uids[-max_results:]

        emails: list[dict[str, Any]] = []
        for uid in reversed(recent):
            data = await self._fetch_email(uid)
            if data:
                emails.append(data)

        return emails

    async def _fetch_email(self, uid: str) -> dict[str, Any] | None:
        """Fetch and parse a single message by UID."""
        if self._client is None:
            return None
        try:
            response = await self._client.uid("fetch", uid, "(BODY.PEEK[])")
            if response.result != "OK":
                return None
            raw = _extract_literal_bytes(response.lines)
            if raw is None:
                return None
            return parse_email_bytes(raw, uid)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Failed to fetch UID %s: %s", uid, err)
            return None
