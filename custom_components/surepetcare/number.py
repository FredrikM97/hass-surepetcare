"""Support for Sure Petcare number entity."""

from dataclasses import dataclass
import logging

from surepcio.enums import ProductId
from surepcio import SurePetcareClient
from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
)
from homeassistant.const import UnitOfMass
from homeassistant.helpers.entity import EntityCategory
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from custom_components.surepetcare.helper import MethodField, should_add_entity

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
            key="bowl_0_target_weight",
            translation_key="target_weight",
            translation_placeholders={"bowl": "One"},
            field=MethodField(path="control.bowls.settings[0].target"),
            native_unit_of_measurement=UnitOfMass.GRAMS,
            entity_category=EntityCategory.CONFIG,
        ),
        SurePetCareNumberEntityDescription(
            key="bowl_1_target_weight",
            translation_key="target_weight",
            translation_placeholders={"bowl": "Two"},
            field=MethodField(path="control.bowls.settings[1].target"),
            native_unit_of_measurement=UnitOfMass.GRAMS,
            entity_category=EntityCategory.CONFIG,
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
    for device_coordinator in coordinator_data[COORDINATOR_DICT].values():
        descriptions = SENSORS.get(device_coordinator.product_id, ())
        entities.extend(
            [
                SurePetCareNumber(
                    device_coordinator,
                    client,
                    description=description,
                )
                for description in descriptions
                if should_add_entity(description, device_coordinator.data, config_entry.options)
            ]
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
        """Set new value."""
        await self.send_command(value)
