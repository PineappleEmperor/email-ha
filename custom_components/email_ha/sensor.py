"""Sensor platform for Email IMAP."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_DATE,
    ATTR_FOLDER,
    ATTR_MESSAGE_ID,
    ATTR_PREVIEW,
    ATTR_SENDER,
    ATTR_SUBJECT,
    ATTR_UID,
    CONF_EMAIL,
    CONF_FOLDER,
    DOMAIN,
)
from .coordinator import EmailData, EmailDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Email IMAP sensors for a config entry."""
    coordinator: EmailDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            UnreadCountSensor(coordinator, entry),
            TotalCountSensor(coordinator, entry),
            FoldersSensor(coordinator, entry),
            LastEmailSensor(coordinator, entry),
        ]
    )


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=f"Gmail – {entry.data[CONF_EMAIL].split('@')[0]}",
        manufacturer="Google",
        model="Gmail IMAP (OAuth2)",
        entry_type=DeviceEntryType.SERVICE,
    )


class _BaseEmailSensor(CoordinatorEntity[EmailDataUpdateCoordinator], SensorEntity):
    """Base class for Email IMAP sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EmailDataUpdateCoordinator,
        entry: ConfigEntry,
        unique_suffix: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{unique_suffix}"
        self._attr_device_info = _device_info(entry)

    @property
    def _email_data(self) -> EmailData | None:
        return self.coordinator.data


class UnreadCountSensor(_BaseEmailSensor):
    """Number of unread messages in the monitored folder."""

    _attr_name = "Unread count"
    _attr_icon = "mdi:email-outline"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "messages"

    def __init__(
        self, coordinator: EmailDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry, "unread_count")

    @property
    def native_value(self) -> int | None:
        data = self._email_data
        return data.unread_count if data else None

    @property
    def extra_state_attributes(self) -> dict:
        return {ATTR_FOLDER: self._entry.data.get(CONF_FOLDER, "INBOX")}


class TotalCountSensor(_BaseEmailSensor):
    """Total number of messages in the monitored folder."""

    _attr_name = "Total count"
    _attr_icon = "mdi:email-multiple-outline"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "messages"

    def __init__(
        self, coordinator: EmailDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry, "total_count")

    @property
    def native_value(self) -> int | None:
        data = self._email_data
        return data.total_count if data else None

    @property
    def extra_state_attributes(self) -> dict:
        return {ATTR_FOLDER: self._entry.data.get(CONF_FOLDER, "INBOX")}


class FoldersSensor(_BaseEmailSensor):
    """Number of mailbox folders on the account, with folder list as attribute."""

    _attr_name = "Folders"
    _attr_icon = "mdi:folder-multiple-outline"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "folders"

    def __init__(
        self, coordinator: EmailDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry, "folders")

    @property
    def native_value(self) -> int | None:
        data = self._email_data
        return len(data.folders) if data else None

    @property
    def extra_state_attributes(self) -> dict:
        data = self._email_data
        return {"folders": data.folders if data else []}


class LastEmailSensor(_BaseEmailSensor):
    """Subject line of the most-recently received email."""

    _attr_name = "Last email"
    _attr_icon = "mdi:email"

    def __init__(
        self, coordinator: EmailDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry, "last_email")

    @property
    def native_value(self) -> str | None:
        data = self._email_data
        if data and data.latest_email:
            return data.latest_email.get(ATTR_SUBJECT) or "(no subject)"
        return None

    @property
    def extra_state_attributes(self) -> dict:
        data = self._email_data
        if not data or not data.latest_email:
            return {}
        email = data.latest_email
        recent = [
            {ATTR_SUBJECT: e.get(ATTR_SUBJECT), ATTR_SENDER: e.get(ATTR_SENDER)}
            for e in data.emails[:3]
        ]
        return {
            ATTR_SENDER: email.get(ATTR_SENDER),
            ATTR_DATE: email.get(ATTR_DATE),
            ATTR_PREVIEW: email.get(ATTR_PREVIEW),
            ATTR_MESSAGE_ID: email.get(ATTR_MESSAGE_ID),
            ATTR_UID: email.get(ATTR_UID),
            ATTR_FOLDER: self._entry.data.get(CONF_FOLDER, "INBOX"),
            "recent_emails": recent,
        }
