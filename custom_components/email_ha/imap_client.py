"""Async IMAP client with XOAUTH2 authentication."""
from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
import email
from email.header import decode_header
from email.message import Message
from email.utils import parseaddr, parsedate_to_datetime
from html.parser import HTMLParser
import logging
import re
from typing import Any, Self, cast

import aioimaplib
from aioimaplib.aioimaplib import STOP_WAIT_SERVER_PUSH

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


def _get_text_body(msg: Message, max_length: int | None = 500) -> str:
    """Extract plain-text body from an email message. Pass max_length=None for full text."""
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
                        text = payload.decode(charset, errors="replace")
                        return text if max_length is None else text[:max_length]
                except (LookupError, binascii.Error) as err:
                    _LOGGER.debug("Failed to decode multipart text body: %s: %s", type(err).__name__, err)
    elif msg.get_content_type() == "text/plain":
        try:
            payload = msg.get_payload(decode=True)
            if isinstance(payload, bytes):
                charset = msg.get_content_charset() or "utf-8"
                text = payload.decode(charset, errors="replace")
                return text if max_length is None else text[:max_length]
        except (LookupError, binascii.Error) as err:
            _LOGGER.debug("Failed to decode text body: %s: %s", type(err).__name__, err)
    return ""


def _get_html_body(msg: Message) -> str:
    """Extract HTML body from an email message."""
    if msg.is_multipart():
        for part in msg.walk():
            if (
                part.get_content_type() == "text/html"
                and not part.get("Content-Disposition")
            ):
                try:
                    payload = part.get_payload(decode=True)
                    if isinstance(payload, bytes):
                        charset = part.get_content_charset() or "utf-8"
                        return payload.decode(charset, errors="replace")
                except (LookupError, binascii.Error) as err:
                    _LOGGER.debug("Failed to decode HTML body: %s: %s", type(err).__name__, err)
    elif msg.get_content_type() == "text/html":
        try:
            payload = msg.get_payload(decode=True)
            if isinstance(payload, bytes):
                charset = msg.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
        except (LookupError, binascii.Error) as err:
            _LOGGER.debug("Failed to decode HTML body: %s: %s", type(err).__name__, err)
    return ""


_HTML_SKIP_TAGS = frozenset({"script", "style", "head", "title"})
_HTML_BREAK_TAGS = frozenset(
    {
        "br", "p", "div", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6",
        "table", "ul", "ol", "blockquote", "section", "article", "header",
        "footer", "hr", "pre",
    }
)


class _HtmlTextExtractor(HTMLParser):
    """Collect visible text from an HTML document."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _HTML_SKIP_TAGS:
            self._skip_depth += 1
        elif tag in _HTML_BREAK_TAGS:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _HTML_SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in _HTML_BREAK_TAGS:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._chunks.append(data)

    def get_text(self) -> str:
        """Return the collapsed visible text."""
        text = "".join(self._chunks)
        text = re.sub(r"[^\S\n]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        return re.sub(r"\n{3,}", "\n\n", text).strip()


def _html_to_text(html: str) -> str:
    """Derive a plain-text approximation of an HTML body."""
    parser = _HtmlTextExtractor()
    try:
        parser.feed(html)
        parser.close()
    except AssertionError as err:
        _LOGGER.debug("HTML-to-text extraction failed: %s: %s", type(err).__name__, err)
        return ""
    return parser.get_text()


def _get_attachments(msg: Message) -> list[dict[str, Any]]:
    """Extract attachments from an email as base64-encoded data with metadata."""
    attachments: list[dict[str, Any]] = []
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        content_disposition = str(part.get("Content-Disposition", ""))
        if "attachment" not in content_disposition:
            continue
        try:
            payload = part.get_payload(decode=True)
        except (LookupError, binascii.Error) as err:
            _LOGGER.debug("Failed to decode attachment payload: %s: %s", type(err).__name__, err)
            continue
        if not isinstance(payload, bytes):
            continue
        attachments.append({
            "filename": _decode_header_value(part.get_filename() or "attachment"),
            "content_type": part.get_content_type(),
            "size": len(payload),
            "data": base64.b64encode(payload).decode("ascii"),
        })
    return attachments


def parse_email_bytes(
    raw: bytes,
    uid: str,
    include_full_body: bool = False,
    include_attachments: bool = False,
) -> dict[str, Any]:
    """Parse raw email bytes into a structured dictionary."""
    msg = email.message_from_bytes(raw)

    date_str = msg.get("Date", "")
    date_iso: str | None = None
    if date_str:
        try:
            date_iso = parsedate_to_datetime(date_str).isoformat()
        except (TypeError, ValueError, IndexError):
            date_iso = date_str

    sender_name, sender_email = parseaddr(_decode_header_value(msg.get("From", "")))

    result: dict[str, Any] = {
        "uid": uid,
        "subject": _decode_header_value(msg.get("Subject")),
        "sender_name": sender_name,
        "sender_email": sender_email,
        "date": date_iso,
    }
    if include_full_body:
        body_text = _get_text_body(msg, None).strip()
        body_html = _get_html_body(msg).strip()
        # Consumers must be able to tell a real text/plain part from a lossy
        # tag-stripped approximation of the HTML.
        derived = not body_text and bool(body_html)
        if derived:
            body_text = _html_to_text(body_html)
        result["body_text"] = body_text
        result["body_html"] = body_html
        result["body_text_derived_from_html"] = derived
    if include_attachments:
        result["attachments"] = _get_attachments(msg)
    return result


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

    async def __aenter__(self) -> Self:
        """Enter context manager."""
        return self

    async def __aexit__(self, *_: object) -> None:
        """Exit context manager and disconnect."""
        await self.disconnect()

    async def connect(self, user: str, access_token: str) -> None:
        """Open a TLS connection and authenticate via XOAUTH2."""
        client = aioimaplib.IMAP4_SSL(host=self._host, port=self._port)
        await client.wait_hello_from_server()

        response = await client.xoauth2(user, cast(bytes, access_token))
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
            except (OSError, aioimaplib.AioImapException) as err:
                _LOGGER.debug("IMAP logout failed: %s: %s", type(err).__name__, err)
            finally:
                self._client = None

    async def list_folders(self) -> list[str]:
        """Return selectable folder names for the account."""
        if self._client is None:
            raise ImapClientError("Not connected")

        response = await self._client.list('""', cast(re.Pattern[str], '"*"'))
        if response.result != "OK":
            return []

        folders: list[str] = []
        for line in response.lines:
            text = line.decode() if isinstance(line, bytes) else str(line)
            if r"\Noselect" in text:
                continue
            m = re.search(r'"/" (?:"([^"]+)"|(\S+))$', text)
            if m:
                folders.append(m.group(1) or m.group(2))
        return folders

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
        include_full_body: bool = False,
        include_attachments: bool = False,
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
        if response.result != "OK":
            raise ImapClientError(
                f"UID SEARCH failed for folder '{folder}': {response.lines}"
            )
        if not response.lines:
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
            data = await self._fetch_email(uid, include_full_body, include_attachments)
            if data:
                emails.append(data)

        return emails

    async def _fetch_email(
        self,
        uid: str,
        include_full_body: bool = False,
        include_attachments: bool = False,
    ) -> dict[str, Any] | None:
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
            return parse_email_bytes(raw, uid, include_full_body, include_attachments)
        except (OSError, aioimaplib.AioImapException) as err:
            _LOGGER.debug("Failed to fetch UID %s: %s: %s", uid, type(err).__name__, err)
            return None

    async def idle_wait(self, timeout: float) -> list[bytes] | None:
        """Run one IDLE cycle; folder must already be selected."""
        if self._client is None:
            raise ImapClientError("Not connected")
        idle = await self._client.idle_start(timeout=timeout)
        try:
            push = cast(list[bytes], await self._client.wait_server_push())
        except asyncio.TimeoutError:
            return None
        else:
            if push is STOP_WAIT_SERVER_PUSH or not push:
                return None
            return [line for line in push if isinstance(line, bytes)] or None
        finally:
            self._client.idle_done()
            if not idle.done():
                idle.cancel()
            with contextlib.suppress(asyncio.CancelledError, aioimaplib.AioImapException):
                async with asyncio.timeout(10):
                    await idle
