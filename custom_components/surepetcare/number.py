"""Support for Sure Petcare number entity."""

from dataclasses import dataclass
import logging

from surepcio.enums import ProductId
from surepcio import SurePetcareClient
from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    COORDINATOR,
    COORDINATOR_DICT,
    DOMAIN,
    KEY_API,
)
from .coordinator import SurePetCareDeviceDataUpdateCoordinator
from .entity import (
    SurePetCareBaseEntity,
    SurePetCareBaseEntityDescription,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class SurePetCareNumberEntityDescription(
    SurePetCareBaseEntityDescription, NumberEntityDescription
):
    """Describes SurePetCare number entity."""


SENSORS: dict[str, tuple[SurePetCareNumberEntityDescription, ...]] = {
    ProductId.FEEDER_CONNECT: (
        SurePetCareNumberEntityDescription(
            key="bowl_1_target_weight", field="control.bowls.settings.0.target"
        ),
        SurePetCareNumberEntityDescription(
            key="bowl_2_target_weight", field="control.bowls.settings.1.target"
        ),
    )
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up SurePetCare sensors for each matching device."""
    coordinator_data = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR]
    client = coordinator_data[KEY_API]

    entities = []
    for device_id, device_coordinator in coordinator_data[COORDINATOR_DICT].items():
        descriptions = SENSORS.get(device_coordinator.product_id, ())
        for description in descriptions:
            entities.append(
                SurePetCareNumber(
                    device_coordinator,
                    client,
                    description=description,
                )
            )
    async_add_entities(entities, update_before_add=True)


class SurePetCareNumber(SurePetCareBaseEntity, NumberEntity):
    """The platform class required by Home Assistant."""

    entity_description: SurePetCareNumberEntityDescription

    def __init__(
        self,
        device_coordinator: SurePetCareDeviceDataUpdateCoordinator,
        client: SurePetcareClient,
        description: SurePetCareNumberEntityDescription,
    ) -> None:
        """Initialize a Surepetcare Number Entity."""
        super().__init__(
            device_coordinator=device_coordinator,
            client=client,
        )
        self.entity_description = description
        self._attr_name = description.name
        self._attr_unique_id = f"{self._attr_unique_id}-{description.key}"
        self._attr_native_unit_of_measurement = description.native_unit_of_measurement
        self._attr_min_value = (
            description.min_value if hasattr(description, "min_value") else None
        )
        self._attr_max_value = (
            description.max_value if hasattr(description, "max_value") else None
        )
        self._attr_step = description.step if hasattr(description, "step") else None

    async def async_set_native_value(self, value: float) -> None:  # type: ignore[override]
        """Set new value for the number (target weight)."""
        if self.entity_description.field is None:
            return None
        await self.coordinator.client.api(
            self._device.set_control(
                **build_nested_dict(self.entity_description.field, value)
            )
        )
        await self.coordinator.async_request_refresh()


def build_nested_dict(field_path: str, value: float) -> dict:
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
