from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, cast

from homeassistant.core import Event, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo, EntityDescription
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


class SurePetCareBaseEntity(CoordinatorEntity[SurePetCareDeviceDataUpdateCoordinator]):
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

    @property
    def _event_driven(self) -> bool:
        """Return True if timeline events, not polling, drive this entity's state."""
        return self.entity_description.field.is_event_driven

    async def async_added_to_hass(self) -> None:
        """Listen for timeline events if the field is driven by them."""
        await super().async_added_to_hass()
        if self._event_driven:
            self.async_on_remove(
                self.hass.bus.async_listen(EVENT_TIMELINE, self._handle_timeline_event)
            )

    @callback
    def _handle_timeline_event(self, event: Event) -> None:
        """Apply a timeline event to this entity's device, if it is about it."""
        payload = event.data
        key = "pets" if isinstance(self._device, PetBase) else "devices"
        is_ours = self._device.id in payload.get(key, ())
        if not is_ours or payload.get("household_id") != self._device.household_id:
            return
        # Entities of one pet share its data: the first applies the event, the
        # others find it already applied. Either way each must re-read its state.
        self.entity_description.field.apply_event(self.context, payload)
        self._refresh_state()

    def _refresh_state(self) -> None:
        """Drop the cached value and write the new state."""
        self._cached_value = None
        self.async_write_ha_state()

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator.

        Event-driven entities take their state from timeline events, so a poll
        no longer updates them (their first state is read when they are added).
        """
        if self._event_driven:
            return
        self._cached_value = None
        super()._handle_coordinator_update()

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
        return FieldContext(self.coordinator.data, options, self.entity_id)

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
        if self._event_driven:
            # The refresh above does not update event-driven entities.
            self._refresh_state()
