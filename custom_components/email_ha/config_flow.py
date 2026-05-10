"""Config flow for Email IMAP (Gmail via OAuth2)."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlowResult, OptionsFlow
from homeassistant.helpers import config_entry_oauth2_flow

from .const import (
    CONF_EMAIL,
    CONF_FOLDER,
    CONF_MAX_EMAILS,
    CONF_SCAN_INTERVAL,
    DEFAULT_FOLDER,
    DEFAULT_MAX_EMAILS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    GMAIL_SCOPES,
)

_LOGGER = logging.getLogger(__name__)

STEP_SETTINGS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_FOLDER, default=DEFAULT_FOLDER): str,
        vol.Optional(CONF_MAX_EMAILS, default=DEFAULT_MAX_EMAILS): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=100)
        ),
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            vol.Coerce(int), vol.Range(min=30, max=3600)
        ),
    }
)


class OAuth2FlowHandler(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN
):
    """Config flow for Email IMAP."""

    DOMAIN = DOMAIN

    def __init__(self) -> None:
        super().__init__()
        self._email: str = ""
        self._token_data: dict[str, Any] = {}

    @property
    def logger(self) -> logging.Logger:
        return _LOGGER

    @property
    def extra_authorize_data(self) -> dict[str, str]:
        """Scopes and params appended to the Google authorize URL."""
        return {
            "scope": GMAIL_SCOPES,
            "access_type": "offline",
            # Force the consent screen so Google always returns a refresh token
            "prompt": "consent",
        }

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the Gmail address, then hand off to OAuth2."""
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({vol.Required(CONF_EMAIL): str}),
                description_placeholders={
                    "credentials_url": (
                        "https://console.cloud.google.com/apis/credentials"
                    )
                },
            )

        self._email = user_input[CONF_EMAIL].strip().lower()
        await self.async_set_unique_id(self._email)
        self._abort_if_unique_id_configured()

        return await self.async_step_auth()

    async def async_oauth_create_entry(self, data: dict[str, Any]) -> ConfigFlowResult:
        """Intercept after token exchange to collect mailbox settings."""
        self._token_data = data
        return await self.async_step_settings()

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect folder / polling preferences before creating the entry."""
        if user_input is None:
            return self.async_show_form(
                step_id="settings",
                data_schema=STEP_SETTINGS_SCHEMA,
            )

        return self.async_create_entry(
            title=self._email,
            data={
                **self._token_data,
                CONF_EMAIL: self._email,
                CONF_FOLDER: user_input[CONF_FOLDER],
                CONF_MAX_EMAILS: user_input[CONF_MAX_EMAILS],
                CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
            },
        )

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return EmailIMAPOptionsFlow()


class EmailIMAPOptionsFlow(OptionsFlow):
    """Options flow to update folder and polling settings."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.data
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_FOLDER, default=current.get(CONF_FOLDER, DEFAULT_FOLDER)
                ): str,
                vol.Optional(
                    CONF_MAX_EMAILS,
                    default=current.get(CONF_MAX_EMAILS, DEFAULT_MAX_EMAILS),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=30, max=3600)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
