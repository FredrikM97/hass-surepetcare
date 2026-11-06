"""Present library toggle interactions."""

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from surepcio.entities.pet import movement_reading
from surepcio.enums import PetLocation, ProductId, TimelineEventType

from .coordinator import SurePetcareConfigEntry
from .entity import SurePetCareBaseEntity
from .field_helpers import _flap_profiles, _indoor_only, _write_indoor_only
from .fields import FLAP_PRODUCTS, SurePetCareBooleanDescription


@dataclass(frozen=True, kw_only=True)
class SurePetCareSwitchEntityDescription(
    SwitchEntityDescription, SurePetCareBooleanDescription
):
    """Native switch metadata and SurePetCare API behavior."""


SWITCH_FIELDS: dict[ProductId, tuple[SurePetCareSwitchEntityDescription, ...]] = {
    ProductId.PET: (
        SurePetCareSwitchEntityDescription(
            key="position",
            icon="mdi:door",
            supported_products=FLAP_PRODUCTS,
            value=lambda _, event: (
                movement_reading(event)[0] == PetLocation.OUTSIDE,
                {},
            ),
            timeline_events=(TimelineEventType.MOVEMENT,),
            command=lambda entity, value: entity.device.set_position(value),
            true_value=PetLocation.OUTSIDE,
            false_value=PetLocation.INSIDE,
        ),
        SurePetCareSwitchEntityDescription(
            key="indoor_only",
            icon="mdi:door",
            supported_products=FLAP_PRODUCTS,
            value=_indoor_only,
            command=_write_indoor_only,
            attributes=lambda entity: {
                "flap_devices": [
                    item.id
                    for item in _flap_profiles(entity)
                ]
            },
        ),
    ),
    ProductId.PET_DOOR: (
        SurePetCareSwitchEntityDescription(
            key="curfew_enabled",
            value="control.curfew.enabled",
            command=lambda entity, value: entity.device.set_curfew_enabled(value),
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
        SurePetCareSwitch(coordinator, device, description)
        for device in coordinator.devices.values()
        for description in SWITCH_FIELDS.get(device.product, ())
    ]
    entities = [entity for entity in entities if entity.is_supported]
    async_add_entities(entities)


class SurePetCareSwitch(SurePetCareBaseEntity, SwitchEntity):
    """A library-provided toggle."""

    entity_description: SurePetCareSwitchEntityDescription

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state is not None and state.state in (STATE_ON, STATE_OFF):
            self._update_state(state.state == STATE_ON, dict(state.attributes))

    def _set_value(self, value: Any) -> None:
        self._attr_is_on = value

    @property
    def is_on(self) -> bool | None:
        return self._attr_is_on

    async def async_turn_on(self, **kwargs) -> None:
        await self.send_command(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.send_command(False)
