"""Select platform for SurePetCare integration."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Callable
from surepcio.enums import (
    ProductId,
    CloseDelay,
    FeederTrainingMode,
    FlapLocking,
    HubLedMode,
    HubPairMode,
    ModifyDeviceTag,
    BowlTypeOptions,
)
from surepcio import SurePetcareClient

from custom_components.surepetcare.entity_path import build_nested_dict
from .coordinator import (
    SurePetCareDeviceDataUpdateCoordinator,
)
from .entity import (
    SurePetCareBaseEntity,
    SurePetCareBaseEntityDescription,
    find_entity_id_by_name,
    option_name,
)
from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import COORDINATOR, COORDINATOR_DICT, DOMAIN, KEY_API, OPTION_DEVICES


@dataclass(frozen=True, kw_only=True)
class SurePetCareSelectEntityDescription(
    SurePetCareBaseEntityDescription, SelectEntityDescription
):
    """Describes SurePetCare select entity."""

    enum_class: type | None = None
    options_fn: Callable | None = None
    command_fn: Callable | None = None


def device_tag_command(action: ModifyDeviceTag):
    """Return a command function for modifying device tags."""

    def command(pet, option: str, entry_data: dict) -> object | None:
        entity_id = find_entity_id_by_name(entry_data, option)
        return pet.set_tag(entity_id, action=action) if entity_id else None

    return command


SELECTS: dict[str, tuple[SurePetCareSelectEntityDescription, ...]] = {
    ProductId.FEEDER_CONNECT: (
        SurePetCareSelectEntityDescription(
            key="lid",
            translation_key="lid",
            field="control.lid.close_delay",
            options=[e.name for e in CloseDelay],
            enum_class=CloseDelay,
        ),
        SurePetCareSelectEntityDescription(
            key="training_mode",
            translation_key="training_mode",
            field="control.training_mode",
            options=[e.name for e in FeederTrainingMode],
            enum_class=FeederTrainingMode,
        ),
        SurePetCareSelectEntityDescription(
            key="bowls_type",
            translation_key="bowls_type",
            field_fn=lambda device, r: device.get_bowl_type_option(),
            options=[e.name for e in BowlTypeOptions],
            command_fn=lambda device, option, r: device.set_bowl_type(
                BowlTypeOptions[option]
            ),
        ),
    ),
    ProductId.DUAL_SCAN_CONNECT: (
        SurePetCareSelectEntityDescription(
            key="locking",
            translation_key="locking",
            field="control.locking",
            options=[e.name for e in FlapLocking],
            enum_class=FlapLocking,
        ),
    ),
    ProductId.PET: (
        SurePetCareSelectEntityDescription(
            key="remove_assigned_device",
            translation_key="remove_assigned_device",
            options_fn=lambda device, r: [
                option_name(r, d.id)
                for d in getattr(device.status, "devices", []) or []
            ],
            command_fn=device_tag_command(ModifyDeviceTag.REMOVE),
        ),
        SurePetCareSelectEntityDescription(
            key="add_assigned_device",
            translation_key="add_assigned_device",
            options_fn=lambda device, r: [
                v.get("name")
                for k, v in r[OPTION_DEVICES].items()
                if v.get("product_id") not in (ProductId.PET, ProductId.HUB)
                and k
                not in {str(d.id) for d in getattr(device.status, "devices", []) or []}
            ],
            command_fn=device_tag_command(ModifyDeviceTag.ADD),
        ),
    ),
    ProductId.HUB: (
        SurePetCareSelectEntityDescription(
            key="led_mode",
            translation_key="led_mode",
            field="control.led_mode",
            options=[e.name for e in HubLedMode],
            enum_class=HubLedMode,
        ),
        SurePetCareSelectEntityDescription(
            key="pairing_mode",
            translation_key="pairing_mode",
            field="control.pairing_mode",
            options=[e.name for e in HubPairMode],
            enum_class=HubPairMode,
        ),
    ),
    ProductId.PET_DOOR: (
        SurePetCareSelectEntityDescription(
            key="locking",
            translation_key="locking",
            field="control.locking",
            options=[e.name for e in FlapLocking],
            enum_class=FlapLocking,
        ),
        SurePetCareSelectEntityDescription(
            key="curfew_enabled",
            translation_key="curfew_enabled",
            field="control.curfew.enabled",
            options=[True, False],
        ),
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SurePetCare select for each matching device."""
    coordinator_data = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR]
    client = coordinator_data[KEY_API]

    entities = []
    for device_id, device_coordinator in coordinator_data[COORDINATOR_DICT].items():
        descriptions = SELECTS.get(device_coordinator.product_id, ())
        for description in descriptions:
            entities.append(
                SurePetCareSelect(
                    device_coordinator,
                    client,
                    description=description,
                )
            )
    async_add_entities(entities, update_before_add=True)


class SurePetCareSelect(SurePetCareBaseEntity, SelectEntity):
    """The platform class required by Home Assistant."""

    entity_description: SurePetCareSelectEntityDescription

    def __init__(
        self,
        device_coordinator: SurePetCareDeviceDataUpdateCoordinator,
        client: SurePetcareClient,
        description: SurePetCareSelectEntityDescription,
    ) -> None:
        """Initialize a Surepetcare sensor."""
        super().__init__(
            device_coordinator=device_coordinator,
            client=client,
        )
        self.entity_description = description
        self._attr_unique_id: str = f"{self._attr_unique_id}-{description.key}"
        self._attr_options = self.entity_description.options

    @property
    def current_option(self) -> str | None:
        return self.native_value

    async def async_select_option(self, option: str) -> None:
        if self.entity_description.enum_class is not None:
            option = getattr(self.entity_description.enum_class, option)
        if self.entity_description.command_fn is not None:
            command = self.entity_description.command_fn(
                self._device, option, self.coordinator.config_entry.options
            )
            if command is None:
                return None
            await self.coordinator.client.api(command)
        elif self.entity_description.field:
            await self.coordinator.client.api(
                self._device.set_control(
                    **build_nested_dict(self.entity_description.field, option)
                )
            )
        else:
            return None
        await self.coordinator.async_request_refresh()

    @property
    def options(self) -> list[str]:
        """Return a set of selectable options."""
        desc = self.entity_description
        # Use options_fn if present, passing device and config entry data
        if desc.options_fn is not None:
            return (
                desc.options_fn(self._device, self.coordinator.config_entry.options)
                or []
            )

        # Fallback to static options if present
        if desc.options is not None:
            return desc.options
        return []
