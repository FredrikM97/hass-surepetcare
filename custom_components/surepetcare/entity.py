from __future__ import annotations
from dataclasses import dataclass
from typing import Any, cast

from surepcio import SurePetcareClient
from surepcio.devices.device import DeviceBase, PetBase
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.surepetcare.helper import MethodField, serialize
from .const import DOMAIN
from .coordinator import SurePetCareDeviceDataUpdateCoordinator


@dataclass(frozen=True, kw_only=True)
class SurePetCareBaseEntityDescription:
    """Describes SurePetCare Base entity."""

    field: MethodField
    frozen: bool = False


class SurePetCareBaseEntity(CoordinatorEntity[SurePetCareDeviceDataUpdateCoordinator]):
    """Base SurePetCare device."""

    entity_description: SurePetCareBaseEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        device_coordinator: SurePetCareDeviceDataUpdateCoordinator,
        client: SurePetcareClient,
    ) -> None:
        """Initialize a device."""
        super().__init__(device_coordinator)

        self._device: DeviceBase | PetBase = device_coordinator.data
        self._client = client
        self._attr_unique_id = f"{self._device.id}"

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
        return serialize(
            self.entity_description.field.get(
                self.coordinator.data, self.coordinator.config_entry.options
            )
        )

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

        return serialize(
            self.entity_description.field.get_extra(
                self.coordinator.data, self.coordinator.config_entry.options
            )
        )

    async def send_command(self, value: Any) -> None:
        """Send command to device."""
        command = self.entity_description.field(
            self._device, self.coordinator.config_entry.options, value
        )
        await self.coordinator.client.api(command)
        await self.coordinator.async_request_refresh()
