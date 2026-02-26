"""Switch platform for SurePetCare integration."""

from __future__ import annotations
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any
from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.surepcha.helper import (
    list_attr,
    option_product_id,
)
from custom_components.surepcha.method_field import SwitchMethodField
from .coordinator import SurePetCareDeviceDataUpdateCoordinator
from .entity import (
    SurePetCareBaseEntity,
    SurePetCareBaseEntityDescription,
)
from surepcio.command import Command
from surepcio.devices import Pet
from surepcio.enums import ProductId, PetDeviceLocationProfile, PetLocation
from .const import COORDINATOR, COORDINATOR_DICT, DOMAIN, FLAP_PRODUCTS, KEY_API
import logging

logger = logging.getLogger(__name__)


def profile_is_indoor(
    pet: Pet, entry_options: MappingProxyType[str, Any]
) -> bool | None:
    """Return True if all flap device profiles are indoor only."""
    devices = list_attr(pet, "status", "devices", "items")
    if not devices:
        return None
    profiles = {
        d.profile
        for d in devices
        if option_product_id(entry_options, d.id) in FLAP_PRODUCTS
    }
    if len(profiles) > 1:
        logger.warning(f"Flap device profiles are not uniform: {profiles}")
    if len(profiles) == 0:
        logger.debug(f"No flap devices found for pet {pet.name}")
        return None
    return profiles == {PetDeviceLocationProfile.INDOOR_ONLY}


def set_profile(
    pet: Pet,
    entry_options: MappingProxyType[str, Any],
    profile: PetDeviceLocationProfile,
) -> list[Command]:
    """Set all flap devices to the given profile and return the results."""
    if not getattr(pet, "status", None):
        return []

    return [
        pet.set_profile(d.id, profile)
        for d in list_attr(pet.status, "devices", "items")
        if option_product_id(entry_options, d.id) in FLAP_PRODUCTS
    ]


@dataclass(frozen=True, kw_only=True)
class SurePetCareSwitchEntityDescription(
    SurePetCareBaseEntityDescription, SwitchEntityDescription
):
    """Describes SurePetCare switch entity."""


# Example: Add your switch entity descriptions here
SWITCHES: dict[str, tuple[SurePetCareSwitchEntityDescription, ...]] = {
    ProductId.PET: (
        SurePetCareSwitchEntityDescription(
            key="indoor_only",
            translation_key="indoor_only",
            entity_registry_enabled_default=False,
            field=SwitchMethodField(
                get_fn=profile_is_indoor,
                set_fn=set_profile,
                on=PetDeviceLocationProfile.INDOOR_ONLY,
                off=PetDeviceLocationProfile.NO_RESTRICTION,
                get_extra_fn=lambda pet, r: {
                    "flap_devices": [
                        str(d.id)
                        for d in list_attr(pet.status, "devices", "items")
                        if option_product_id(r, d.id) in FLAP_PRODUCTS
                    ]
                },
            ),
            icon="mdi:door",
        ),
        SurePetCareSwitchEntityDescription(
            key="position",
            translation_key="position",
            entity_registry_enabled_default=False,
            field=SwitchMethodField(
                path="status.activity.where",
                set_fn=lambda device, r, value: device.set_position(value),
                on=PetLocation.OUTSIDE,
                off=PetLocation.INSIDE,
            ),
            icon="mdi:door",
        ),
    ),
    ProductId.PET_DOOR: (
        SurePetCareSwitchEntityDescription(
            key="curfew_enabled",
            translation_key="curfew_enabled",
            field=SwitchMethodField(path="control.curfew.enabled"),
        ),
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SurePetCare switch for each matching device."""
    coordinator_data = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR]
    client = coordinator_data[KEY_API]

    entities = []
    for device_coordinator in coordinator_data[COORDINATOR_DICT].values():
        descriptions = SWITCHES.get(device_coordinator.product_id, ())
        entities.extend(
            [
                SurePetCareSwitch(
                    device_coordinator,
                    client,
                    description=description,
                )
                for description in descriptions
            ]
        )
    async_add_entities(entities, update_before_add=True)


class SurePetCareSwitch(SurePetCareBaseEntity, SwitchEntity):
    """Switch entity for SurePetCare device."""

    entity_description: SurePetCareSwitchEntityDescription

    def __init__(
        self,
        device_coordinator: SurePetCareDeviceDataUpdateCoordinator,
        client,
        description: SurePetCareSwitchEntityDescription,
    ) -> None:
        super().__init__(
            device_coordinator=device_coordinator,
            client=client,
        )
        self.entity_description = description
        self._attr_unique_id = f"{self._attr_unique_id}-{description.key}"

    @property
    def is_on(self) -> bool:
        return self.native_value is True

    async def async_turn_on(self, **kwargs):
        await self.send_command(True)

    async def async_turn_off(self, **kwargs):
        await self.send_command(False)
