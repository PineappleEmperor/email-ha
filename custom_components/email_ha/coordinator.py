"""DataUpdateCoordinator for Email IMAP."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.config_entry_oauth2_flow import OAuth2Session
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_EMAIL, CONF_FOLDER, DOMAIN, EVENT_NEW_EMAIL, POLL_FETCH_COUNT
from .imap_client import ImapAuthError, ImapClient

_LOGGER = logging.getLogger(__name__)


@dataclass
class EmailData:
    """Holds the polled email state for one account/folder."""

    emails: list[dict[str, Any]] = field(default_factory=list)
    unread_count: int = 0
    total_count: int = 0
    folders: list[str] = field(default_factory=list)

    @property
    def latest_email(self) -> dict[str, Any] | None:
        """Return the most-recent email, or None if empty."""
        return self.emails[0] if self.emails else None

    @property
    def latest_uid(self) -> str | None:
        """UID of the most-recent email (used to detect new mail)."""
        latest = self.latest_email
        return latest["uid"] if latest else None


class EmailDataUpdateCoordinator(DataUpdateCoordinator[EmailData]):
    """Polls an IMAP folder and fires an event when new mail arrives."""

    def __init__(
        self,
        hass: HomeAssistant,
        oauth_session: OAuth2Session,
        email_address: str,
        imap_host: str,
        imap_port: int,
        folder: str,
        scan_interval: int,
    ) -> None:
        self.oauth_session = oauth_session
        self._email = email_address
        self._imap_host = imap_host
        self._imap_port = imap_port
        self._folder = folder
        self._last_uid: str | None = None

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}:{email_address}",
            update_interval=timedelta(seconds=scan_interval),
        )

    async def _async_update_data(self) -> EmailData:
        """Fetch latest emails; raise on auth or connection failure."""
        try:
            await self.oauth_session.async_ensure_token_valid()
        except Exception as err:
            raise ConfigEntryAuthFailed(
                f"Token refresh failed for {self._email}"
            ) from err

        token: dict[str, Any] = self.oauth_session.token  # type: ignore[assignment]
        access_token = str(token["access_token"])

        try:
            async with ImapClient(self._imap_host, self._imap_port) as client:
                await client.connect(self._email, access_token)
                status = await client.get_folder_status(self._folder)
                folders = await client.list_folders()
                emails = await client.search_emails(
                    self._folder, "ALL", POLL_FETCH_COUNT
                )
        except ImapAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except Exception as err:
            raise UpdateFailed(f"IMAP error for {self._email}: {err}") from err

        data = EmailData(
            emails=emails,
            unread_count=status.get("unseen", 0),
            total_count=status.get("messages", 0),
            folders=folders,
        )
        self._fire_new_email_event(data)
        return data

    def _fire_new_email_event(self, data: EmailData) -> None:
        """Fire EVENT_NEW_EMAIL when the latest UID has changed."""
        new_uid = data.latest_uid
        if new_uid and new_uid != self._last_uid:
            if self._last_uid is not None:
                # Only fire after the first successful poll so we don't spam on startup
                self.hass.bus.async_fire(
                    EVENT_NEW_EMAIL,
                    {
                        "email_address": self._email,
                        "folder": self._folder,
                        **(data.latest_email or {}),
                    },
                )
            self._last_uid = new_uid


def coordinator_from_entry(
    hass: HomeAssistant, entry_id: str
) -> EmailDataUpdateCoordinator | None:
    """Return the coordinator for entry_id, or None if not found."""
    return hass.data.get(DOMAIN, {}).get(entry_id)
