from __future__ import annotations
from dataclasses import dataclass
import logging
from typing import Any, cast

from surepcio.devices.device import DeviceBase, PetBase
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.surepcha.helper import serialize
from custom_components.surepcha.method_field import FieldContext, MethodField
from .const import DOMAIN
from .coordinator import SurePetCareDeviceDataUpdateCoordinator

logger = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class SurePetCareBaseEntityDescription:
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
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._device.id}")},
            manufacturer="SurePetCare",
            model=self._device.product_name,
            model_id=self._device.product_id,
            name=self._device.name,
            via_device=(DOMAIN, str(self._device.entity_info.parent_device_id))
            if self._device.entity_info.parent_device_id is not None
            else None,
        )

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
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
        return FieldContext(
            self.coordinator.data, self.coordinator.config_entry.options, self.entity_id
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
