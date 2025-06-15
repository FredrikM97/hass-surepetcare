from __future__ import annotations
<<<<<<< HEAD
from dataclasses import dataclass
from typing import Any, Callable, cast
=======
from dataclasses import dataclass, is_dataclass, fields, asdict
from typing import Any, Callable, cast
from collections.abc import Mapping
from enum import Enum
>>>>>>> 0ad8e71 (Apply rework of entity paths)

from surepetcare.client import SurePetcareClient
from surepetcare.devices.device import SurepyDevice
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

        self._device: SurepyDevice = device_coordinator.data
        self._client = client

        device_info = {
            "identifiers": {(DOMAIN, f"{self._device.id}")},
            "manufacturer": "SurePetCare",
            "model": self._device.product_name,
            "model_id": self._device.product_id,
            "name": self._device.name,
        }
        if self._device.parent_device_id is not None:
            device_info["via_device"] = (DOMAIN, str(self._device.parent_device_id))
        self._attr_device_info = DeviceInfo(**device_info)
        self._attr_unique_id = f"{self._device.id}"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return cast(bool, self._device.available) and super().available

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        data = self.coordinator.data
<<<<<<< HEAD
        if self.entity_description.field_fn is not None:
            value = self.entity_description.field_fn(data, self.subentry_data)
        elif self.entity_description.field is not None:
=======
        if self.entity_description.field_fn:
            value = self.entity_description.field_fn(data, self.subentry_data)
        elif self.entity_description.field:
>>>>>>> 0ad8e71 (Apply rework of entity paths)
            value = get_by_paths(data, self.entity_description.field, native=True)
        else:
            value = get_by_paths(data, self.entity_description.key, native=True)
        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra state attributes."""
        data = self.coordinator.data
<<<<<<< HEAD
        if self.entity_description.extra_fn is not None:
            return self.entity_description.extra_fn(data, self.subentry_data)
        elif self.entity_description.extra_field is not None:
=======
        if self.entity_description.extra_fn:
            return self.entity_description.extra_fn(data, self.subentry_data)
        elif self.entity_description.extra_field:
>>>>>>> 0ad8e71 (Apply rework of entity paths)
            return get_by_paths(
                self.coordinator.data,
                self.entity_description.extra_field,
                serialize=True,
                flatten=True,
            )
        else:
            return None
