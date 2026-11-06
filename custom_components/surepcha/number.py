"""Present library numeric controls."""

from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import UnitOfMass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from surepcio.enums import ProductId

from .coordinator import SurePetcareConfigEntry
from .entity import SurePetCareBaseEntity
from .field_helpers import _bowl_target, _has_second_bowl
from .fields import SurePetCareDescriptionMixin


@dataclass(frozen=True, kw_only=True)
class SurePetCareNumberEntityDescription(
    NumberEntityDescription, SurePetCareDescriptionMixin
):
    """Native number metadata and SurePetCare API behavior."""


NUMBER_FIELDS: dict[ProductId, tuple[SurePetCareNumberEntityDescription, ...]] = {
    ProductId.FEEDER_CONNECT: (
        SurePetCareNumberEntityDescription(
            key="bowl_0_target_weight",
            translation_key="target_weight",
            translation_placeholders={"bowl": "One"},
            icon="mdi:scale",
            mode=NumberMode.SLIDER,
            entity_category=EntityCategory.CONFIG,
            value=lambda entity: _bowl_target(entity.device, 0),
            command=lambda entity, value: entity.device.set_target_weight(0, value),
            native_unit_of_measurement=UnitOfMass.GRAMS,
            native_min_value=0.0,
            native_max_value=300,
            native_step=1.0,
        ),
        SurePetCareNumberEntityDescription(
            key="bowl_1_target_weight",
            translation_key="target_weight",
            translation_placeholders={"bowl": "Two"},
            icon="mdi:scale",
            mode=NumberMode.SLIDER,
            entity_category=EntityCategory.CONFIG,
            value=lambda entity: _bowl_target(entity.device, 1),
            supported=_has_second_bowl,
            command=lambda entity, value: entity.device.set_target_weight(1, value),
            native_unit_of_measurement=UnitOfMass.GRAMS,
            native_min_value=0.0,
            native_max_value=300,
            native_step=1.0,
        ),
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SurePetcareConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    entities = [
        SurePetCareNumber(coordinator, device, description)
        for device in coordinator.devices.values()
        for description in NUMBER_FIELDS.get(device.product, ())
    ]
    entities = [entity for entity in entities if entity.is_supported]
    async_add_entities(entities)


class SurePetCareNumber(SurePetCareBaseEntity, NumberEntity):
    """A library-provided numeric control."""

    entity_description: SurePetCareNumberEntityDescription

    def _set_value(self, value: Any) -> None:
        self._attr_native_value = value

    @property
    def native_value(self) -> float | None:
        return self._attr_native_value

    async def async_set_native_value(self, value: float) -> None:
        await self.send_command(value)
