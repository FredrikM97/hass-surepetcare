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
from homeassistant.helpers.entity import EntityCategory
from custom_components.surepetcare.helper import build_nested_dict, find_entity_id_by_name, list_attr, map_attr, option_name
from .coordinator import (
    SurePetCareDeviceDataUpdateCoordinator,
)
from .entity import (
    SurePetCareBaseEntity,
    SurePetCareBaseEntityDescription,
    validate_entity_description,
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
    options: list[str] | None = None
    enum_class: type | None = None
    options_fn: Callable | None = None
    command_fn: Callable | None = None



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
            options_fn=lambda device, r: map_attr(
                list_attr(device.status, "devices"),
                lambda d: option_name(r, d.id)
            ),
            command_fn=lambda pet, option, entry_data: (
                pet.set_tag( value, action=ModifyDeviceTag.REMOVE ) 
                if (value := find_entity_id_by_name(entry_data, option)) else None
            ),
        ),
        SurePetCareSelectEntityDescription(
            key="add_assigned_device",
            translation_key="add_assigned_device",
            options_fn=lambda device, r: [
                v.get("name")
                for k, v in r[OPTION_DEVICES].items()
                if v.get("product_id") not in {ProductId.PET, ProductId.HUB}
                and k not in {str(d.id) for d in list_attr(device.status, "devices")}
            ],
            command_fn=lambda pet, option, entry_data: (
                pet.set_tag( value, action=ModifyDeviceTag.REMOVE) 
                if (value := find_entity_id_by_name(entry_data, option)) else None
            ),
        ),
    ),
    ProductId.HUB: (
        SurePetCareSelectEntityDescription(
            key="led_mode",
            translation_key="led_mode",
            field="control.led_mode",
            options=[e.name for e in HubLedMode],
            enum_class=HubLedMode,
            entity_category=EntityCategory.CONFIG,
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

    # Validation
    for descs in SELECTS.values():
        for desc in descs:
            validate_entity_description(desc)
            
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
        # If command then write with it
        if self.entity_description.command_fn is not None:
            command = self.entity_description.command_fn(
                self._device, option, self.coordinator.config_entry.options
            )
            await self.coordinator.client.api(command)
        # If field then write with it
        elif self.entity_description.field:
            await self.coordinator.client.api(
                self._device.set_control(
                    **build_nested_dict(self.entity_description.field, option)
                )
            )
        else:
            raise ValueError("No command or field defined for select entity")
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
        raise ValueError("No options or options_fn defined for select entity")
