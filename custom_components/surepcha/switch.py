"""Present library toggle interactions."""

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from surepcio.devices.entities import DevicePetTag
from surepcio.entities.pet import movement_reading
from surepcio.enums import (
    PetDeviceLocationProfile,
    PetLocation,
    ProductId,
    TimelineEventType,
)

from .const import PRODUCT_ID
from .coordinator import SurePetcareConfigEntry
from .entity import FLAP_PRODUCTS, SurePetCareBaseEntity, SurePetCareBooleanDescription
from .helper import get_device_options

logger = logging.getLogger(__name__)


def flap_profiles(entity: SurePetCareBaseEntity) -> list[DevicePetTag]:
    options = get_device_options(entity.hass, entity.coordinator.config_entry)
    flaps = {
        int(device_id)
        for device_id, metadata in options.items()
        if ProductId.find(metadata.get(PRODUCT_ID)) in FLAP_PRODUCTS
    }
    return [item for item in entity.device.status.devices.items if item.id in flaps]


def indoor_only(entity: SurePetCareBaseEntity) -> bool | None:
    profiles = {item.profile for item in flap_profiles(entity)}
    if not profiles:
        return None
    if len(profiles) > 1:
        logger.warning(
            "Flap device profiles are not uniform for pet %s: %s",
            entity.device.id,
            profiles,
        )
    return profiles == {PetDeviceLocationProfile.INDOOR_ONLY}


def write_indoor_only(entity: SurePetCareBaseEntity, value: Any) -> list[Any]:
    pet: Any = entity.device
    profiles = flap_profiles(entity)
    if not profiles:
        raise ValueError(f"No flap devices are assigned to pet {pet.id}")
    profile = (
        PetDeviceLocationProfile.INDOOR_ONLY
        if value
        else PetDeviceLocationProfile.NO_RESTRICTION
    )
    return [
        pet.set_profile(item.id, profile) for item in profiles if item.id is not None
    ]


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
            value=indoor_only,
            command=write_indoor_only,
            attributes=lambda entity: {
                "flap_devices": [item.id for item in flap_profiles(entity)]
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
