from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, cast

from homeassistant.core import Event, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo, EntityDescription
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from surepcio.devices.device import DeviceBase, PetBase

from custom_components.surepcha.helper import serialize
from custom_components.surepcha.method_field import FieldContext, MethodField

from .const import DOMAIN, EVENT_TIMELINE, OPTION_DEVICES
from .coordinator import SurePetCareDeviceDataUpdateCoordinator

logger = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class SurePetCareBaseEntityDescription(EntityDescription):
    """Describes SurePetCare Base entity."""

    field: MethodField
    frozen: bool = False


@dataclass(frozen=True, slots=True)
class TimelineEventRestoreData(ExtraStoredData):
    """Persist the parent timeline event used by an event-backed entity."""

    event_data: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        """Return JSON-serializable restored data."""
        return {"event_data": self.event_data}


class SurePetCareBaseEntity(
    CoordinatorEntity[SurePetCareDeviceDataUpdateCoordinator], RestoreEntity
):
    """Base SurePetCare device."""

    entity_description: SurePetCareBaseEntityDescription
    _attr_has_entity_name = True
    _cached_value: Any | None = None

    def __init__(
        self,
        coordinator: SurePetCareDeviceDataUpdateCoordinator,
    ) -> None:
        """Initialize a device."""
        super().__init__(coordinator)
        self._device: DeviceBase | PetBase = coordinator.data
        self._event_data: dict[str, Any] | None = None

    @property
    def device_info(self) -> DeviceInfo:
        """Return a device description for device registry."""
        parent_device_id = self._device.entity_info.parent_device_id
        device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{self._device.id}")},
            manufacturer="SurePetCare",
            model=self._device.product_name,
            model_id=str(self._device.product_id),
            name=self._device.name,
        )
        if parent_device_id is not None:
            parent_identifier = (DOMAIN, str(parent_device_id))
            try:
                device_info["via_device_id"] = dr.async_get_device_id_by_identifier(
                    self.hass,
                    parent_identifier,
                    config_entry_id=self.coordinator.config_entry.entry_id,
                )
            except ValueError:
                logger.debug(
                    "Skipping via_device_id for %s: parent %s not found in config entry %s",
                    self._device.id,
                    parent_identifier,
                    self.coordinator.config_entry.entry_id,
                )
        return device_info

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.entity_description.field.event_types:
            return
        self._cached_value = None
        super()._handle_coordinator_update()

    async def async_added_to_hass(self) -> None:
        """Subscribe to timeline events for event-backed fields."""
        await super().async_added_to_hass()
        if self.entity_description.field.event_types:
            if restored_data := await self.async_get_last_extra_data():
                event_data = restored_data.as_dict().get("event_data")
                if isinstance(event_data, dict):
                    self._event_data = event_data
            self.async_on_remove(
                self.hass.bus.async_listen(EVENT_TIMELINE, self._handle_timeline_event)
            )

    @property
    def extra_restore_state_data(self) -> ExtraStoredData | None:
        """Persist event data used to calculate an event-backed entity state."""
        if self._event_data is None:
            return None
        return TimelineEventRestoreData(self._event_data)

    @callback
    def _handle_timeline_event(self, event: Event) -> None:
        field = self.entity_description.field
        if str(event.data.get("household_id")) != str(self._device.household_id):
            return

        if event_data := field.apply_event(self.context, event.data):
            self._event_data = event_data
            self._write_event_state()

    @callback
    def _write_event_state(self) -> None:
        self._cached_value = None
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            cast(bool, self._device.available)
            and super().available
            and self.native_value is not None
        )

    @property
    def native_value(self) -> str | None:
        """Return the sensor value."""
        # Use cached value if available to avoid unnecessary processing on each update
        if self._cached_value is None:
            self._cached_value = serialize(
                self.entity_description.field.get(self.context)
            )
        return self._cached_value

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra state attributes."""
        if self.native_value is None:
            return None

        if not (
            self.entity_description.field.path_extra
            or self.entity_description.field.get_extra_fn
        ):
            return None

        return serialize(self.entity_description.field.get_extra(self.context))

    @property
    def context(self):
        merged_devices = {}
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            merged_devices.update(entry.options.get(OPTION_DEVICES, {}))
        # Current entry takes priority
        merged_devices.update(
            self.coordinator.config_entry.options.get(OPTION_DEVICES, {})
        )
        options = {
            **self.coordinator.config_entry.options,
            OPTION_DEVICES: merged_devices,
        }
        return FieldContext(
            self.coordinator.data, options, self.entity_id, self._event_data
        )

    async def send_command(self, value: Any) -> None:
        """Send command to device."""
        self.hass.async_create_task(self._send_command(value))

    async def _send_command(self, value: Any) -> None:
        """Send command to device."""
        command = self.entity_description.field(self.context, value)
        logger.debug(
            "send_command for %s: %s=%s (command: %s)",
            self.entity_id,
            self.entity_description.field.path,
            value,
            command,
        )
        await self.coordinator.client.api(command)
        # update entities with new data
        await self.coordinator.async_request_refresh()
