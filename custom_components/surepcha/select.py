"""Select platform for SurePetCare integration."""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Callable, cast
from surepcio.enums import (
    ProductId,
    CloseDelay,
    FeederTrainingMode,
    FlapLocking,
    HubLedMode,
    ModifyDeviceTag,
    BowlTypeOptions,
    Tare,
)
from homeassistant.components.sensor import SensorDeviceClass
from surepcio import SurePetcareClient
from homeassistant.helpers.entity import EntityCategory
from custom_components.surepcha.helper import (
    MethodField,
    find_entity_id_by_name,
    list_attr,
    map_attr,
    option_name,
    resolve_select_option_value,
    should_add_entity,
)
from .coordinator import (
    SurePetCareDeviceDataUpdateCoordinator,
)
from .entity import (
    SurePetCareBaseEntity,
    SurePetCareBaseEntityDescription,
)
from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    COORDINATOR,
    COORDINATOR_DICT,
    DEVICES,
    DOMAIN,
    KEY_API,
    NAME,
    OPTION_DEVICES,
    PRODUCT_ID,
)


@dataclass(frozen=True, slots=True)
class SelectMethodField(MethodField):
    """MethodField for switch-like entities, supporting on/off mapping."""

    options_fn: Callable | None = None

    def get(self, device: object, entry_options: MappingProxyType[str, Any]) -> Any:
        if self.get_fn is None and self.path is None and self.options_fn is not None:
            # Bonky solution but this might return multiple values and therefore we just return None.
            return None
        return MethodField.get(self, device, entry_options)

    def set(
        self, device: object, entry_options: MappingProxyType[str, Any], value: Any
    ) -> Any:
        return MethodField.set(self, device, entry_options, value)


@dataclass(frozen=True, kw_only=True)
class SurePetCareSelectEntityDescription(
    SurePetCareBaseEntityDescription, SelectEntityDescription
):
    """Describes SurePetCare select entity."""


SELECTS: dict[str, tuple[SurePetCareSelectEntityDescription, ...]] = {
    ProductId.FEEDER_CONNECT: (
        SurePetCareSelectEntityDescription(
            key="lid",
            translation_key="lid",
            field=SelectMethodField(path="control.lid.close_delay"),
            options=CloseDelay,
            device_class=SensorDeviceClass.ENUM,
            entity_category=EntityCategory.CONFIG,
        ),
        SurePetCareSelectEntityDescription(
            key="training_mode",
            translation_key="training_mode",
            field=SelectMethodField(path="control.training_mode"),
            options=FeederTrainingMode,
            entity_category=EntityCategory.CONFIG,
        ),
        SurePetCareSelectEntityDescription(
            key="bowls_type",
            translation_key="bowls_type",
            field=SelectMethodField(
                get_fn=lambda device, r: device.get_bowl_type_option(),
                set_fn=lambda device, r, option: device.set_bowl_type(
                    BowlTypeOptions(option)
                ),
            ),
            options=BowlTypeOptions,
            device_class=SensorDeviceClass.ENUM,
            entity_category=EntityCategory.CONFIG,
        ),
        SurePetCareSelectEntityDescription(
            key="tare",
            translation_key="tare",
            field=SelectMethodField(path="control.tare"),
            options=Tare,
            entity_category=EntityCategory.CONFIG,
        ),
    ),
    ProductId.DUAL_SCAN_CONNECT: (
        SurePetCareSelectEntityDescription(
            key="locking",
            translation_key="locking",
            field=SelectMethodField(path="control.locking"),
            options=FlapLocking,
            device_class=SensorDeviceClass.ENUM,
            entity_category=EntityCategory.CONFIG,
        ),
    ),
    ProductId.PET: (
        SurePetCareSelectEntityDescription(
            key="remove_assigned_device",
            translation_key="remove_assigned_device",
            device_class=SensorDeviceClass.ENUM,
            field=SelectMethodField(
                set_fn=lambda pet, entry_data, option: (
                    pet.set_tag(value, action=ModifyDeviceTag.REMOVE)
                    if (value := find_entity_id_by_name(entry_data, option))
                    else None
                ),
                options_fn=lambda device, r: list(
                    filter(
                        None,
                        map_attr(
                            list_attr(device.status, DEVICES),
                            lambda d: option_name(r, d.id),
                        ),
                    )
                ),
            ),
        ),
        SurePetCareSelectEntityDescription(
            key="add_assigned_device",
            translation_key="add_assigned_device",
            device_class=SensorDeviceClass.ENUM,
            field=SelectMethodField(
                options_fn=lambda device, r: [
                    v.get(NAME)
                    for k, v in r[OPTION_DEVICES].items()
                    if v.get(PRODUCT_ID) not in {ProductId.PET, ProductId.HUB}
                    and k not in {str(d.id) for d in list_attr(device.status, DEVICES)}
                ],
                set_fn=lambda pet, entry_data, option: (
                    pet.set_tag(value, action=ModifyDeviceTag.ADD)
                    if (value := find_entity_id_by_name(entry_data, option))
                    else None
                ),
            ),
        ),
    ),
    ProductId.HUB: (
        SurePetCareSelectEntityDescription(
            key="led_mode",
            translation_key="led_mode",
            field=SelectMethodField(path="control.led_mode"),
            options=HubLedMode,
            device_class=SensorDeviceClass.ENUM,
            entity_category=EntityCategory.CONFIG,
        ),
    ),
    ProductId.PET_DOOR: (
        SurePetCareSelectEntityDescription(
            key="locking",
            translation_key="locking",
            field=SelectMethodField(path="control.locking"),
            options=FlapLocking,
            device_class=SensorDeviceClass.ENUM,
            entity_category=EntityCategory.CONFIG,
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
    for device_coordinator in coordinator_data[COORDINATOR_DICT].values():
        descriptions = SELECTS.get(device_coordinator.product_id, ())
        entities.extend(
            [
                SurePetCareSelect(
                    device_coordinator,
                    client,
                    description=description,
                )
                for description in descriptions
                if should_add_entity(
                    description, device_coordinator.data, config_entry.options
                )
            ]
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

    @property
    def current_option(self) -> str | None:
        # Convert to lower since translation requires lower case.
        if self.native_value is None:
            return None
        return self.native_value.lower()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return cast(bool, self._device.available)

    async def async_select_option(self, option: str) -> None:
        # If command then write with it
        if option not in self.options:
            raise ValueError(
                f"Invalid option {option} for select entity {self.entity_description}"
            )

        value = resolve_select_option_value(self.entity_description, option)

        await self.send_command(value)

    @property
    def options(self) -> list[str]:
        """Return a set of selectable options."""
        desc = self.entity_description

        # Use options_fn if present
        options_fn = getattr(desc.field, "options_fn", None)
        if options_fn:
            return options_fn(self._device, self.coordinator.config_entry.options)

        # Fallback to static options if present
        opts = desc.options
        if opts is not None:
            if isinstance(opts, type) and issubclass(opts, Enum):
                return [e.name.lower() for e in opts]
            return list(opts)
        raise ValueError(f"No options or options_fn defined for select entity {desc}")
