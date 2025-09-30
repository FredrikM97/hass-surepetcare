"""Switch platform for SurePetCare integration."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, cast
from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.surepetcare.helper import build_nested_dict, list_attr, option_product_id
from .coordinator import SurePetCareDeviceDataUpdateCoordinator
from .entity import (
    SurePetCareBaseEntity,
    SurePetCareBaseEntityDescription,
    validate_entity_description,
)
from homeassistant.helpers.entity import EntityCategory
from surepcio.command import Command
from surepcio.devices import Pet
from surepcio.enums import ProductId, PetDeviceLocationProfile, HubPairMode
from .const import COORDINATOR, COORDINATOR_DICT, DOMAIN, KEY_API, OPTION_DEVICES
import logging

logger = logging.getLogger(__name__)


def profile_is_indoor(device: Pet, entry_data: dict) -> bool | None:
    """Return True if all flap device profiles are indoor only."""
    devices = list_attr(device, "status", "devices")
    if not devices:
        return False
    valid_products = {
        ProductId.PET_DOOR,
        ProductId.DUAL_SCAN_PET_DOOR,
        ProductId.DUAL_SCAN_CONNECT,
    }
    profiles = {
        d.profile
        for d in devices
        if option_product_id(entry_data, d.id) in valid_products
    }
    if len(profiles) > 1:
        logger.warning(f"Flap device profiles are not uniform: {profiles}")
    if len(profiles) == 0:
        return None
    return profiles == {PetDeviceLocationProfile.INDOOR_ONLY}


def set_profile(
    device: Pet, config: dict, profile: PetDeviceLocationProfile
) -> list[Command]:
    """Set all flap devices to the given profile and return the results."""
    if not getattr(device, "status", None):
        return []

    valid_products = {ProductId.PET_DOOR, ProductId.DUAL_SCAN_PET_DOOR}

    return [
        device.set_profile(d.id, profile)
        for d in list_attr(device.status, "devices")
        if option_product_id(config, d.id) in valid_products
    ]

@dataclass(frozen=True, kw_only=True)
class SurePetCareSwitchEntityDescription(
    SurePetCareBaseEntityDescription, SwitchEntityDescription
):
    """Describes SurePetCare switch entity."""

    command_fn: Callable | None = None


# Example: Add your switch entity descriptions here
SWITCHES: dict[str, tuple[SurePetCareSwitchEntityDescription, ...]] = {
    ProductId.PET: (
        SurePetCareSwitchEntityDescription(
            key="indoor_only",
            translation_key="indoor_only",
            field_fn=profile_is_indoor,
            command_fn=lambda device, entry_data, state: set_profile(
                device,
                entry_data,
                PetDeviceLocationProfile.INDOOR_ONLY if state else PetDeviceLocationProfile.NO_RESTRICTION,
            ),
            icon="mdi:door",
        ),
    ),
    ProductId.HUB: (
        SurePetCareSwitchEntityDescription(
            key="pairing_mode",
            translation_key="pairing_mode",
            field="control.pairing_mode",
            #options=[e.name for e in HubPairMode],
            #enum_class=HubPairMode,
            entity_category=EntityCategory.CONFIG,
        ),
    ),
    ProductId.PET_DOOR: (
          SurePetCareSwitchEntityDescription(
            key="curfew_enabled",
            translation_key="curfew_enabled",
            field="control.curfew.enabled",
            #options=[True, False],
        ),
    )
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SurePetCare switch for each matching device."""
    coordinator_data = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR]
    client = coordinator_data[KEY_API]

     # Validation
    for descs in SWITCHES.values():
        for desc in descs:
            validate_entity_description(desc)
            
    entities = []
    for device_id, device_coordinator in coordinator_data[COORDINATOR_DICT].items():
        descriptions = SWITCHES.get(device_coordinator.product_id, ())
        for description in descriptions:
            entities.append(
                SurePetCareSwitch(
                    device_coordinator,
                    client,
                    description=description,
                )
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
        return self._convert_value() is True

    @property
    def available(self) -> bool:
        return (
            cast(bool, self._device.available)
            and super().available
            and self._convert_value() in (True, False)
        )

    async def async_turn_on(self, **kwargs):
        
        # If command then write with it
        if self.entity_description.command_fn is not None:
            
            command = self.entity_description.command_fn(
                self._device, self.coordinator.config_entry.options, True
            )
            await self.coordinator.client.api(command)
        # If field then write with it
        elif self.entity_description.field:
            await self.coordinator.client.api(
                self._device.set_control(
                    **build_nested_dict(self.entity_description.field, True)
                )
            )
        else:
            raise ValueError("No command or field defined for select entity")
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        # If command then write with it
        if self.entity_description.command_fn is not None:
            
            command = self.entity_description.command_fn(
                self._device, self.coordinator.config_entry.options, False
            )
            await self.coordinator.client.api(command)
        # If field then write with it
        elif self.entity_description.field:
            await self.coordinator.client.api(
                self._device.set_control(
                    **build_nested_dict(self.entity_description.field, False)
                )
            )
        else:
            raise ValueError("No command or field defined for select entity")
        await self.coordinator.async_request_refresh()