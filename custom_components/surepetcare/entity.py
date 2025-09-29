from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, cast

from surepcio import SurePetcareClient
from surepcio.devices.device import DeviceBase, PetBase
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN, OPTION_DEVICES
from .coordinator import SurePetCareDeviceDataUpdateCoordinator

@dataclass(frozen=True, kw_only=True)
class SurePetCareBaseEntityDescription:
    """Describes SurePetCare Base entity."""
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
        return cast(bool, self._device.available) and super().available

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        return serialize(self._convert_value())

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra state attributes."""
        if self.native_value is None:
            return None
        data = self.coordinator.data
        if self.entity_description.extra_fn is not None:
            return serialize(self.entity_description.extra_fn(
                data, self.coordinator.config_entry.options
            ))
        return None

    def _convert_value(self) -> Any:
        data = self.coordinator.data
        desc = self.entity_description
        if getattr(desc, "field_fn", None) is not None:
            return serialize(desc.field_fn(data, self.coordinator.config_entry.options))
        return None


def find_entity_id_by_name(entry_data: dict, name: str) -> str | None:
    """Find the entity ID by its name in entry_data['entities']."""
    return next(
        (
            entity_id
            for entity_id, entity in entry_data.get(OPTION_DEVICES, {}).items()
            if entity.get("name") == name
        ),
        None,
    )

def serialize(obj):
    """Recursively convert objects/enums/lists/dicts to JSON-serializable types."""
    if isinstance(obj, Enum):
        return obj.name
    elif isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    elif isinstance(obj, dict):
        return {k: serialize(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple, set)):
        return [serialize(v) for v in obj]
    elif hasattr(obj, "__dict__"):
        return {k: serialize(v) for k, v in obj.__dict__.items() if not k.startswith("_")}
    else:
        return str(obj)

def build_nested_dict(field_path: str, value: float | int | str) -> dict:
    """Build a nested dict/list structure from a dotted field path, handling list indices.
    Skips the top-level 'control' key.
    """
    parts = field_path.split(".")
    if parts and parts[0] == "control":
        parts = parts[1:]
    result: object = value
    for part in reversed(parts):
        if part.isdigit():
            idx = int(part)
            lst: list = []
            while len(lst) <= idx:
                lst.append(None)
            lst[idx] = result
            result = lst
        else:
            result = {part: result}
    return result if isinstance(result, dict) else {parts[0]: result}
