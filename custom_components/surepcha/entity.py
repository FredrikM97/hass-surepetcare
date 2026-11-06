from __future__ import annotations

import logging
from typing import Any

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import UNDEFINED
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from surepcio.devices.device import SurePetCareBase
from surepcio.timeline import TimelineEvent

from .const import DOMAIN
from .coordinator import SurePetCareCoordinator
from .field_helpers import iter_device_events
from .fields import SurePetCareDescriptionMixin
from .helper import serialize

logger = logging.getLogger(__name__)


class SurePetCareBaseEntity(CoordinatorEntity[SurePetCareCoordinator], RestoreEntity):
    """Base SurePetCare device."""

    _attr_has_entity_name = True
    entity_description: SurePetCareDescriptionMixin

    def __init__(
        self,
        coordinator: SurePetCareCoordinator,
        device: SurePetCareBase,
        description: SurePetCareDescriptionMixin,
    ) -> None:
        """Initialize a device."""
        super().__init__(coordinator)
        self.device = device
        self._attr_extra_state_attributes = {}
        self.entity_description = description
        self._attr_translation_key = description.translation_key or description.key
        self._attr_unique_id = f"{device.id}-{description.key}"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self.entity_description.timeline_events:
            self.async_on_remove(
                self.coordinator.async_subscribe_timeline(self._handle_timeline)
            )

    @property
    def is_supported(self) -> bool:
        """Whether household hardware and device configuration allow discovery."""
        description = self.entity_description
        if description.supported_products and not any(
            device.product in description.supported_products
            for device in self.coordinator.devices.values()
        ):
            return False
        supported = description.supported
        return supported is None or supported(self.device)

    def _set_value(self, value: Any) -> None:
        """Store a value exposed by the platform's state property."""
        raise NotImplementedError

    def _update_state(self, value: Any, attributes: dict[str, Any]) -> None:
        self._set_value(value)
        self._attr_extra_state_attributes = (
            serialize(attributes) if value is not None else {}
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        return self._attr_extra_state_attributes

    def _handle_coordinator_update(self) -> None:
        description = self.entity_description
        if (
            description.value is not None
            and not description.timeline_events
            and self.device.id not in self.coordinator.device_errors
        ):
            self._update_state(*description.read_value(self))
        super()._handle_coordinator_update()

    def _handle_timeline(self, event: TimelineEvent) -> None:
        description = self.entity_description
        if event.event_type in description.timeline_events:
            for source in iter_device_events(
                event, self.device, self.coordinator.devices.values()
            ):
                reading = description.read_timeline(self.device, source)
                if reading is not None:
                    self._update_state(*reading)
                    self.async_write_ha_state()

    @property
    def name(self) -> str | None:
        """Use HA translations, retaining discovery for fields without translations."""
        name = super().name
        return (
            self.entity_description.key.replace("_", " ").capitalize()
            if name is UNDEFINED
            else name
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return a device description for device registry."""
        parent_device_id = self.device.entity_info.parent_device_id
        device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{self.device.id}")},
            manufacturer="SurePetCare",
            model=self.device.product_name,
            model_id=str(self.device.product_id),
            name=self.device.name,
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
                    self.device.id,
                    parent_identifier,
                    self.coordinator.config_entry.entry_id,
                )
        return device_info

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.device.id not in self.coordinator.device_errors
            and bool(self.device.available)
            and super().available
        )

    async def send_command(self, value: Any) -> None:
        """Send command to device."""
        description = self.entity_description
        if description.command is None:
            raise HomeAssistantError(
                f"Field {self.entity_description.key!r} is not writable"
            )
        value = description.prepare_command_value(value, self)
        await self.coordinator.client.api(description.command(self, value))
        await self.coordinator.async_refresh_device(self.device)
