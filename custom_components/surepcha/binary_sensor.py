"""Present library boolean status values."""

from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from surepcio.entities.pet import presence_reading
from surepcio.enums import PetLocation, ProductId, TimelineEventType

from .coordinator import SurePetcareConfigEntry
from .entity import SurePetCareBaseEntity
from .field_helpers import _curfew_active, _curfew_extra
from .fields import FLAP_PRODUCTS, SurePetCareBooleanDescription


@dataclass(frozen=True, kw_only=True)
class SurePetCareBinarySensorEntityDescription(
    BinarySensorEntityDescription, SurePetCareBooleanDescription
):
    """Native binary sensor metadata and SurePetCare API behavior."""


_connectivity = SurePetCareBinarySensorEntityDescription(
    key="connectivity",
    translation_key="connectivity",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    value="available",
)
_learn_mode = SurePetCareBinarySensorEntityDescription(
    key="learn_mode",
    translation_key="learn_mode",
    entity_category=EntityCategory.DIAGNOSTIC,
    value="status.learn_mode",
)
_curfew = SurePetCareBinarySensorEntityDescription(
    key="curfew",
    translation_key="curfew_active",
    value=lambda entity: _curfew_active(entity.device),
    attributes=lambda entity: _curfew_extra(entity.device),
)
BINARY_SENSOR_FIELDS: dict[
    ProductId, tuple[SurePetCareBinarySensorEntityDescription, ...]
] = {
    ProductId.HUB: (_connectivity,),
    ProductId.FEEDER_CONNECT: (
        _connectivity,
        SurePetCareBinarySensorEntityDescription(
            key="learn_mode",
            translation_key="learn_mode",
            entity_category=EntityCategory.DIAGNOSTIC,
            icon="mdi:school",
            value="status.learn_mode",
        ),
    ),
    ProductId.PET_DOOR: (_curfew, _learn_mode),
    ProductId.DUAL_SCAN_CONNECT: (_curfew, _connectivity, _learn_mode),
    ProductId.DUAL_SCAN_PET_DOOR: (_connectivity,),
    ProductId.PET: (
        SurePetCareBinarySensorEntityDescription(
            key="presence",
            translation_key="presence",
            device_class=BinarySensorDeviceClass.PRESENCE,
            supported_products=FLAP_PRODUCTS,
            value=lambda _, event: presence_reading(event),
            timeline_events=(TimelineEventType.MOVEMENT,),
            true_value=PetLocation.INSIDE,
            false_value=PetLocation.OUTSIDE,
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
        SurePetCareBinarySensor(coordinator, device, description)
        for device in coordinator.devices.values()
        for description in BINARY_SENSOR_FIELDS.get(device.product, ())
    ]
    entities = [entity for entity in entities if entity.is_supported]
    async_add_entities(entities)


class SurePetCareBinarySensor(SurePetCareBaseEntity, BinarySensorEntity):
    """A library-provided boolean status."""

    entity_description: SurePetCareBinarySensorEntityDescription

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state is not None and state.state in (STATE_ON, STATE_OFF):
            self._update_state(state.state == STATE_ON, dict(state.attributes))

    @property
    def available(self) -> bool:
        if self.device_class == BinarySensorDeviceClass.CONNECTIVITY:
            return (
                self.device.id not in self.coordinator.device_errors
                and self.coordinator.last_update_success
            )
        return super().available

    def _set_value(self, value: Any) -> None:
        self._attr_is_on = value

    @property
    def is_on(self) -> bool | None:
        return self._attr_is_on
