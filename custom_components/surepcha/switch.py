"""Switch platform for SurePetCare integration."""

from __future__ import annotations
from dataclasses import dataclass
from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.surepcha.helper import (
    list_attr,
    option_product_id,
)
from custom_components.surepcha.method_field import SwitchMethodField
from .coordinator import SurePetCareDeviceDataUpdateCoordinator, SurePetcareConfigEntry
from .entity import (
    SurePetCareBaseEntity,
    SurePetCareBaseEntityDescription,
)
from surepcio.command import Command
from surepcio.enums import ProductId, PetDeviceLocationProfile, PetLocation
from .const import FLAP_PRODUCTS
import logging

logger = logging.getLogger(__name__)


def profile_is_indoor(ctx) -> bool | None:
    """Return True if all flap device profiles are indoor only."""
    devices = list_attr(ctx.device, "status", "devices", "items")
    if not devices:
        return None
    profiles = {
        d.profile
        for d in devices
        if option_product_id(ctx.options, d.id) in FLAP_PRODUCTS
    }
    if len(profiles) > 1:
        logger.warning(f"Flap device profiles are not uniform: {profiles}")
    if len(profiles) == 0:
        logger.debug(f"No flap devices found for pet {ctx.device.name}")
        return None
    return profiles == {PetDeviceLocationProfile.INDOOR_ONLY}


def set_profile(ctx, value) -> list[Command]:
    """Set all flap devices to the given profile and return the results."""
    pet = ctx.device
    if not getattr(pet, "status", None):
        return []

    return [
        pet.set_profile(d.id, value)
        for d in list_attr(pet.status, "devices", "items")
        if option_product_id(ctx.options, d.id) in FLAP_PRODUCTS
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
                get_extra_fn=lambda ctx: {
                    "flap_devices": [
                        str(d.id)
                        for d in list_attr(ctx.device.status, "devices", "items")
                        if option_product_id(ctx.options, d.id) in FLAP_PRODUCTS
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
                set_fn=lambda ctx, value: ctx.device.set_position(value),
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
    entry: SurePetcareConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SurePetCare switch for each matching device."""
    coordinators = entry.runtime_data

    entities = [
        SurePetCareSwitch(
            coordinator,
            description=description,
        )
        for coordinator in coordinators
        for description in SWITCHES.get(coordinator.product_id, ())
    ]
    async_add_entities(entities)


class SurePetCareSwitch(SurePetCareBaseEntity, SwitchEntity):
    """Switch entity for SurePetCare device."""

    entity_description: SurePetCareSwitchEntityDescription

    def __init__(
        self,
        coordinator: SurePetCareDeviceDataUpdateCoordinator,
        description: SurePetCareSwitchEntityDescription,
    ) -> None:
        super().__init__(coordinator=coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator._device.id}-{description.key}"

    @property
    def is_on(self) -> bool:
        return self.native_value is True

    async def async_turn_on(self, **kwargs):
        await self.send_command(True)

    async def async_turn_off(self, **kwargs):
        await self.send_command(False)
