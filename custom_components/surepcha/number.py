"""Support for Sure Petcare number entity."""

import logging
from dataclasses import dataclass

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import UnitOfMass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from surepcio.enums import ProductId, TimelineEventType

from custom_components.surepcha.method_field import MethodField

from .coordinator import SurePetcareConfigEntry, SurePetCareDeviceDataUpdateCoordinator
from .entity import SurePetCareBaseEntityDescription
from .event_entity import SurePetCareEventEntity

logger = logging.getLogger(__name__)


def set_bowl_target(ctx, value, index):
    settings = [setting.model_dump() for setting in ctx.device.control.bowls.settings]
    settings[index]["target"] = value
    return ctx.device.set_control(bowls={"settings": settings})


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
            mode=NumberMode.SLIDER,
            icon="mdi:scale",
            native_max_value=300,
            field=MethodField(
                path="data.weight.target[0]",
                set_fn=lambda ctx, value: set_bowl_target(ctx, value, 0),
                event_types=frozenset(
                    {
                        TimelineEventType.FEEDING,
                        TimelineEventType.WEIGHT_CHANGED,
                        TimelineEventType.TARGET_WEIGHT_SET,
                    }
                ),
            ),
            native_unit_of_measurement=UnitOfMass.GRAMS,
            entity_category=EntityCategory.CONFIG,
        ),
        SurePetCareNumberEntityDescription(
            key="bowl_1_target_weight",
            translation_key="target_weight",
            translation_placeholders={"bowl": "Two"},
            mode=NumberMode.SLIDER,
            icon="mdi:scale",
            native_max_value=300,
            field=MethodField(
                path="data.weight.target[1]",
                set_fn=lambda ctx, value: set_bowl_target(ctx, value, 1),
                event_types=frozenset(
                    {
                        TimelineEventType.FEEDING,
                        TimelineEventType.WEIGHT_CHANGED,
                        TimelineEventType.TARGET_WEIGHT_SET,
                    }
                ),
            ),
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
    coordinators = entry.runtime_data.device_coordinators

    entities = [
        SurePetCareNumber(
            coordinator,
            description=description,
        )
        for coordinator in coordinators
        for description in SENSORS.get(coordinator.product_id, ())
    ]
    async_add_entities(entities)


class SurePetCareNumber(SurePetCareEventEntity, NumberEntity):
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

    @property
    def native_value(self) -> float | None:  # type: ignore[override]
        """Return the current value."""
        value = super().native_value
        return float(value) if value is not None else None
