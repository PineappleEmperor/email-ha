"""Email IMAP integration for Home Assistant."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ConfigEntryNotReady, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.config_entry_oauth2_flow import (
    OAuth2Session,
    async_get_config_entry_implementation,
)

from .const import (
    CONF_EMAIL,
    CONF_FOLDER,
    CONF_SCAN_INTERVAL,
    DEFAULT_FOLDER,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    GMAIL_IMAP_HOST,
    GMAIL_IMAP_PORT,
    PLATFORMS,
    SERVICE_ATTR_FOLDER,
    SERVICE_ATTR_INCLUDE_ATTACHMENTS,
    SERVICE_ATTR_INCLUDE_FULL_BODY,
    SERVICE_ATTR_MAX_RESULTS,
    SERVICE_ATTR_SEARCH_CRITERIA,
    SERVICE_QUERY_EMAILS,
)
from .coordinator import EmailDataUpdateCoordinator
from .imap_client import ImapAuthError, ImapClient

_LOGGER = logging.getLogger(__name__)

QUERY_EMAILS_SCHEMA = vol.Schema(
    {
        vol.Optional("config_entry_id"): cv.string,
        vol.Optional(SERVICE_ATTR_FOLDER, default=DEFAULT_FOLDER): cv.string,
        vol.Optional(SERVICE_ATTR_SEARCH_CRITERIA, default="ALL"): cv.string,
        vol.Optional(SERVICE_ATTR_MAX_RESULTS, default=50): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=200)
        ),
        vol.Optional(SERVICE_ATTR_INCLUDE_FULL_BODY, default=False): cv.boolean,
        vol.Optional(SERVICE_ATTR_INCLUDE_ATTACHMENTS, default=False): cv.boolean,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Email IMAP from a config entry."""
    implementation = await async_get_config_entry_implementation(hass, entry)
    oauth_session = OAuth2Session(hass, entry, implementation)

    coordinator = EmailDataUpdateCoordinator(
        hass=hass,
        oauth_session=oauth_session,
        email_address=entry.data[CONF_EMAIL],
        imap_host=GMAIL_IMAP_HOST,
        imap_port=GMAIL_IMAP_PORT,
        folder=entry.data.get(CONF_FOLDER, DEFAULT_FOLDER),
        scan_interval=entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        _LOGGER.warning("Initial email fetch failed: %s: %s", type(err).__name__, err)
        raise ConfigEntryNotReady(f"Initial email fetch failed: {type(err).__name__}: {err}") from err

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(
        entry, [Platform(p) for p in PLATFORMS]
    )

    _register_services(hass)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    coordinator.start_idle()
    entry.async_on_unload(coordinator.stop_idle)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(
        entry, [Platform(p) for p in PLATFORMS]
    )
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    if not hass.data.get(DOMAIN):
        hass.services.async_remove(DOMAIN, SERVICE_QUERY_EMAILS)

    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload entry when user-facing config changes (not on token refresh)."""
    coordinator: EmailDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    if (
        entry.data.get(CONF_FOLDER) != coordinator.folder
        or entry.data.get(CONF_SCAN_INTERVAL) != coordinator.scan_interval
    ):
        await hass.config_entries.async_reload(entry.entry_id)


def _register_services(hass: HomeAssistant) -> None:
    """Register integration-level services (idempotent)."""
    if hass.services.has_service(DOMAIN, SERVICE_QUERY_EMAILS):
        return

    async def handle_query_emails(call: ServiceCall) -> dict[str, Any]:
        """Query emails from any configured account."""
        configured: dict = hass.data.get(DOMAIN, {})
        entry_id: str | None = call.data.get("config_entry_id")
        if entry_id is None:
            if len(configured) == 1:
                entry_id = next(iter(configured))
            else:
                raise ServiceValidationError(
                    "Multiple email accounts configured — specify an account."
                )
        coordinator: EmailDataUpdateCoordinator | None = configured.get(entry_id)
        if coordinator is None:
            raise ServiceValidationError(
                f"No Email IMAP entry with id '{entry_id}'."
            )

        folder: str = call.data.get(SERVICE_ATTR_FOLDER, DEFAULT_FOLDER)
        criteria: str = call.data.get(SERVICE_ATTR_SEARCH_CRITERIA, "ALL")
        max_results: int = call.data.get(SERVICE_ATTR_MAX_RESULTS, 50)
        include_full_body: bool = call.data.get(SERVICE_ATTR_INCLUDE_FULL_BODY, False)
        include_attachments: bool = call.data.get(SERVICE_ATTR_INCLUDE_ATTACHMENTS, False)

        try:
            await coordinator.oauth_session.async_ensure_token_valid()
        except Exception as err:
            _LOGGER.warning("Token refresh failed: %s: %s", type(err).__name__, err)
            raise ServiceValidationError(f"Token refresh failed: {type(err).__name__}: {err}") from err

        token: dict[str, Any] = coordinator.oauth_session.token  # type: ignore[assignment]
        access_token = str(token["access_token"])

        config_entry = coordinator.config_entry
        if config_entry is None:
            raise ServiceValidationError("Config entry not available for this coordinator")

        try:
            async with ImapClient(GMAIL_IMAP_HOST, GMAIL_IMAP_PORT) as client:
                await client.connect(config_entry.data[CONF_EMAIL], access_token)
                emails = await client.search_emails(
                    folder, criteria, max_results,
                    include_full_body=include_full_body,
                    include_attachments=include_attachments,
                )
        except ImapAuthError as err:
            raise ServiceValidationError(f"IMAP authentication error: {err}") from err
        except Exception as err:
            _LOGGER.warning("IMAP query failed: %s: %s", type(err).__name__, err)
            raise ServiceValidationError(f"IMAP query failed: {type(err).__name__}: {err}") from err

        return {"emails": emails}

    hass.services.async_register(
        DOMAIN,
        SERVICE_QUERY_EMAILS,
        handle_query_emails,
        schema=QUERY_EMAILS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
