"""Present library choice interactions."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from surepcio.enums import (
    BowlTypeOptions,
    CloseDelay,
    FeederTrainingMode,
    FlapLocking,
    HubLedMode,
    ModifyDeviceTag,
    ProductId,
    Tare,
)

from .coordinator import SurePetcareConfigEntry
from .entity import SurePetCareBaseEntity
from .field_helpers import _assignment_options
from .fields import FieldOption, SurePetCareDescriptionMixin


@dataclass(frozen=True, kw_only=True)
class SurePetCareSelectEntityDescription(
    SelectEntityDescription, SurePetCareDescriptionMixin
):
    """Native select metadata and SurePetCare API behavior."""

    choices: type[Enum] | None = None
    options_fn: Callable[[Any], tuple[FieldOption, ...]] | None = None

    def get_options(
        self,
        entity: SurePetCareBaseEntity,
    ) -> tuple[FieldOption, ...]:
        """Resolve current API choices or the native static options."""
        if self.options_fn is not None:
            return self.options_fn(entity)
        if self.choices is not None:
            values = tuple(value.name.lower() for value in self.choices)
        elif self.options:
            values = tuple(self.options)
        else:
            raise ValueError(f"Field {self.key!r} does not provide choices")
        return tuple(FieldOption(value, value) for value in values)

    def normalize_value(self, value: Any, entity: SurePetCareBaseEntity) -> str | None:
        options = self.get_options(entity)
        if value is None:
            return None
        native = value.name.lower() if isinstance(value, Enum) else value
        matches = [
            option.label
            for option in options
            if (
                self.choices[option.value.upper()] == value
                if self.choices is not None
                else option.value == native
            )
        ]
        return matches[0] if len(matches) == 1 else None

    def prepare_command_value(self, value: Any, entity: SurePetCareBaseEntity) -> Any:
        options = self.get_options(entity)
        matches = [option.value for option in options if option.label == value]
        if len(matches) != 1:
            raise ValueError(f"Choice {value!r} is unavailable for {self.key!r}")
        value = matches[0]
        if self.choices is not None:
            try:
                value = self.choices[value.upper()]
            except KeyError as error:
                raise ValueError(
                    f"Choice {value!r} is not valid for {self.key!r}"
                ) from error
        return value


_locking_mode = SurePetCareSelectEntityDescription(
    key="locking",
    device_class=SensorDeviceClass.ENUM,
    entity_category=EntityCategory.CONFIG,
    value="control.locking",
    command=lambda entity, value: entity.device.set_locking(value),
    choices=FlapLocking,
)
SELECT_FIELDS: dict[ProductId, tuple[SurePetCareSelectEntityDescription, ...]] = {
    ProductId.HUB: (
        SurePetCareSelectEntityDescription(
            key="led_mode",
            icon="mdi:led-variant-on",
            device_class=SensorDeviceClass.ENUM,
            entity_category=EntityCategory.CONFIG,
            value="control.led_mode",
            command=lambda entity, value: entity.device.set_led_mode(value),
            choices=HubLedMode,
        ),
    ),
    ProductId.FEEDER_CONNECT: (
        SurePetCareSelectEntityDescription(
            key="lid",
            icon="mdi:timer-sand",
            device_class=SensorDeviceClass.ENUM,
            entity_category=EntityCategory.CONFIG,
            value="control.lid.close_delay",
            command=lambda entity, value: entity.device.set_lid(value),
            choices=CloseDelay,
        ),
        SurePetCareSelectEntityDescription(
            key="training_mode",
            icon="mdi:school",
            entity_category=EntityCategory.CONFIG,
            value="control.training_mode",
            command=lambda entity, value: entity.device.set_training_mode(value),
            choices=FeederTrainingMode,
        ),
        SurePetCareSelectEntityDescription(
            key="bowls_type",
            icon="mdi:bowl-mix",
            device_class=SensorDeviceClass.ENUM,
            entity_category=EntityCategory.CONFIG,
            value=lambda entity: (
                BowlTypeOptions[option]
                if (option := entity.device.get_bowl_type_option()) is not None
                else None
            ),
            command=lambda entity, value: entity.device.set_bowl_type(value),
            choices=BowlTypeOptions,
        ),
        SurePetCareSelectEntityDescription(
            key="tare",
            value="control.tare",
            icon="mdi:restart",
            entity_category=EntityCategory.CONFIG,
            command=lambda entity, value: entity.device.set_tare(value),
            choices=Tare,
            options_fn=lambda entity: tuple(
                FieldOption(value, value)
                for value in entity.device.status.tare_options or ()
            ),
        ),
    ),
    ProductId.PET_DOOR: (_locking_mode,),
    ProductId.DUAL_SCAN_CONNECT: (_locking_mode,),
    ProductId.PET: (
        SurePetCareSelectEntityDescription(
            key="remove_assigned_device",
            icon="mdi:link-variant-off",
            device_class=SensorDeviceClass.ENUM,
            options_fn=lambda entity: _assignment_options(
                entity, ModifyDeviceTag.REMOVE
            ),
            command=lambda entity, value: entity.device.set_tag(
                int(value), ModifyDeviceTag.REMOVE
            ),
        ),
        SurePetCareSelectEntityDescription(
            key="add_assigned_device",
            icon="mdi:link-variant",
            device_class=SensorDeviceClass.ENUM,
            options_fn=lambda entity: _assignment_options(
                entity, ModifyDeviceTag.ADD
            ),
            command=lambda entity, value: entity.device.set_tag(
                int(value), ModifyDeviceTag.ADD
            ),
        ),
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SurePetcareConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        SurePetCareSelect(coordinator, device, description)
        for device in coordinator.devices.values()
        for description in SELECT_FIELDS.get(device.product, ())
    )


class SurePetCareSelect(SurePetCareBaseEntity, SelectEntity):
    """A library-provided choice control."""

    entity_description: SurePetCareSelectEntityDescription

    def _set_value(self, value: Any) -> None:
        self._attr_current_option = value

    @property
    def current_option(self) -> str | None:
        return self._attr_current_option

    @property
    def options(self) -> list[str]:
        return [option.label for option in self.entity_description.get_options(self)]

    async def async_select_option(self, option: str) -> None:
        await self.send_command(option)
