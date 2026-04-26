"""Support for Sure Petcare number entity."""

from dataclasses import dataclass
import logging

from surepcio.enums import ProductId
from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
)
from homeassistant.const import UnitOfMass
from homeassistant.helpers.entity import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from custom_components.surepcha.method_field import MethodField

from .coordinator import SurePetCareDeviceDataUpdateCoordinator, SurePetcareConfigEntry
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
            mode="slider",
            icon="mdi:scale",
            native_max_value=300,
            field=MethodField(path="control.bowls.settings[0].target"),
            native_unit_of_measurement=UnitOfMass.GRAMS,
            entity_category=EntityCategory.CONFIG,
        ),
        SurePetCareNumberEntityDescription(
            key="bowl_1_target_weight",
            translation_key="target_weight",
            translation_placeholders={"bowl": "Two"},
            mode="slider",
            icon="mdi:scale",
            native_max_value=300,
            field=MethodField(path="control.bowls.settings[1].target"),
            native_unit_of_measurement=UnitOfMass.GRAMS,
            entity_category=EntityCategory.CONFIG,
        ),
    )
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SurePetcareConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up SurePetCare sensors for each matching device."""
    coordinators = entry.runtime_data

    entities = [
        SurePetCareNumber(
            coordinator,
            description=description,
        )
        for coordinator in coordinators
        for description in SENSORS.get(coordinator.product_id, ())
    ]
    async_add_entities(entities)


class SurePetCareNumber(SurePetCareBaseEntity, NumberEntity):
    """The platform class required by Home Assistant."""

    entity_description: SurePetCareNumberEntityDescription

    def __init__(
        self,
        coordinator: SurePetCareDeviceDataUpdateCoordinator,
        description: SurePetCareNumberEntityDescription,
    ) -> None:
        """Initialize a Surepetcare Number Entity."""
        super().__init__(
            coordinator=coordinator,
        )
        self.entity_description = description
        self._attr_unique_id = f"{coordinator._device.id}-{description.key}"

    async def async_set_native_value(self, value: float) -> None:  # type: ignore[override]
        """Set new value."""
        await self.send_command(value)
