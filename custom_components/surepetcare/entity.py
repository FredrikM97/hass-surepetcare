from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, cast

from surepcio import SurePetcareClient
from surepcio.devices.device import DeviceBase, PetBase
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN
from .coordinator import SurePetCareDeviceDataUpdateCoordinator
from .entity_path import get_by_paths


@dataclass(frozen=True, kw_only=True)
class SurePetCareBaseEntityDescription:
    """Describes SurePetCare Base entity."""

    field: str | None = None
    field_fn: Callable | None = None
    extra_fn: Callable | None = None
    extra_field: dict[str, str] | str | None = None
    frozen: bool = False


class SurePetCareBaseEntity(CoordinatorEntity[SurePetCareDeviceDataUpdateCoordinator]):
    """Base SurePetCare device."""

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
            and self._convert_value() is not None
            and super().available
        )

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        return self._convert_value()

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra state attributes."""
        if self.native_value is None:
            return None
        data = self.coordinator.data
        if self.entity_description.extra_fn is not None:
            return self.entity_description.extra_fn(
                data, self.coordinator.config_entry.options
            )
        extra_field = getattr(self.entity_description, "extra_field", None)
        if extra_field and isinstance(extra_field, (str, dict)):
            return get_by_paths(
                self.coordinator.data,
                extra_field,
                serialize=True,
                flatten=True,
            )
        return None

    def _convert_value(self) -> Any:
        data = self.coordinator.data
        desc = self.entity_description
        if getattr(desc, "field_fn", None) is not None:
            return desc.field_fn(data, self.coordinator.config_entry.options)
        if getattr(desc, "field", None):
            return get_by_paths(data, desc.field, native=True)
        if getattr(desc, "key", None):
            return get_by_paths(data, desc.key, native=True)
        return None
