"""Present library measurements and status values."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.components.sensor.const import UNIT_CONVERTERS
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfMass,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from surepcio.entities.bowl import bowl_weights
from surepcio.entities.pet import (
    consumption_reading,
    last_activity_reading,
    movement_reading,
)
from surepcio.enums import PetLocation, ProductId, TimelineEventType
from surepcio.timeline import TimelineEvent

from .const import (
    LOCATION_INSIDE,
    LOCATION_OUTSIDE,
    MANUAL_PROPERTIES,
    NAME,
    OPTION_PROPERTIES,
)
from .coordinator import SurePetcareConfigEntry
from .entity import (
    ACTIVITY_PRODUCTS,
    FLAP_PRODUCTS,
    SurePetCareBaseEntity,
    SurePetCareDescriptionMixin,
)
from .helper import bowl_target, get_device_options, has_second_bowl, serialize

logger = logging.getLogger(__name__)


def sum_targets(device: Any) -> float | None:
    settings = getattr(getattr(device.control, "bowls", None), "settings", None) or []
    targets = [
        setting.target for setting in settings if setting and setting.target is not None
    ]
    return sum(targets) if targets else None


def _bowl_extra(
    device: Any, index: int, *, include_substance: bool = False
) -> dict[str, Any]:
    statuses = getattr(device.status, "bowl_status", None) or []
    settings = getattr(getattr(device.control, "bowls", None), "settings", None) or []
    if index >= len(statuses):
        return {}
    status = statuses[index]
    setting = settings[index] if index < len(settings) else None
    result: dict[str, Any] = {
        "position": (
            status.position.name.lower() if status.position is not None else None
        ),
        "food_type": (
            setting.food_type.name.lower()
            if setting is not None and setting.food_type is not None
            else None
        ),
        "last_filled_at": status.last_filled_at,
        "last_zeroed_at": status.last_zeroed_at,
        "last_fill_weight": status.last_fill_weight,
    }
    if include_substance:
        result["substance_type"] = status.substance_type
    return result


def _event_weights(device: Any, event: TimelineEvent) -> dict[int, float]:
    return bowl_weights(
        event,
        device_id=device.id,
        indices=(0, 1) if has_second_bowl(device) else (0,),
    )


def weight_reading(
    device: Any, event: TimelineEvent, index: int
) -> tuple[float, dict[str, Any]] | None:
    weights = _event_weights(device, event)
    if index not in weights:
        return None
    return (weights[index], _bowl_extra(device, index, include_substance=index == 1))


def fill_reading(
    device: Any, event: TimelineEvent
) -> tuple[float | None, dict[str, Any]] | None:
    weights = _event_weights(device, event)
    if not weights:
        return None
    total_weight = total_target = 0.0
    attributes: dict[str, Any] = {}
    for index, weight in weights.items():
        target = bowl_target(device, index)
        percent = None
        if target is not None and target > 0:
            clamped = max(weight, 0)
            percent = clamped / target * 100
            total_weight += clamped
            total_target += target
        attributes[f"bowl_{index}_fill_percent"] = percent
    return (total_weight / total_target * 100 if total_target > 0 else None, attributes)


def weight_capacity_extra(device: Any) -> dict[str, Any]:
    bowls = getattr(getattr(device.control, "bowls", None), "settings", None) or []
    return {
        f"bowls_{index}_target": (
            bowls[index].target if index < len(bowls) and bowls[index] else None
        )
        for index in range(2)
    }


def poseidon_bowl_value(device: Any, attribute: str) -> Any:
    bowls = device.status.bowl_status
    return getattr(bowls[0], attribute) if bowls else None


def _poseidon_extra(device: Any) -> dict[str, Any]:
    statuses = getattr(device.status, "bowl_status", None) or []
    if not statuses:
        return {}
    status = statuses[0]
    return {
        "last_filled_at": status.last_filled_at,
        "last_zeroed_at": status.last_zeroed_at,
        "last_fill_weight": status.last_fill_weight,
    }


def poseidon_volume(
    device: Any, event: TimelineEvent
) -> tuple[float, dict[str, Any]] | None:
    weights = bowl_weights(event, device_id=device.id, indices=(0,))
    return (weights[0], _poseidon_extra(device)) if 0 in weights else None


@dataclass(frozen=True, kw_only=True)
class SurePetCareSensorEntityDescription(
    SensorEntityDescription, SurePetCareDescriptionMixin
):
    """Native sensor metadata and SurePetCare API behavior."""

    format_value: Callable[[SurePetCareSensor], Any] | None = None
    picture: Callable[[Any], str | None] | None = None


def _activity_label(entity: SurePetCareSensor) -> str | None:
    value = entity._attr_native_value
    if isinstance(value, str):
        return value
    return (
        get_device_options(entity.hass, entity.coordinator.config_entry)
        .get(str(value), {})
        .get(NAME)
    )


def _position_label(entity: SurePetCareSensor) -> str:
    value = entity._attr_native_value
    if isinstance(value, str):
        return value
    key = LOCATION_INSIDE if value == PetLocation.INSIDE else LOCATION_OUTSIDE
    attributes = entity.extra_state_attributes or {}
    device_id = str(attributes["device_id"])
    entry = entity.coordinator.config_entry
    options = get_device_options(entity.hass, entry)
    manual = entry.options.get(OPTION_PROPERTIES, {}).get(MANUAL_PROPERTIES, {})
    return options.get(device_id, {}).get(key) or manual.get(
        key, "inside" if key == LOCATION_INSIDE else "outside"
    )


_device_fields = (
    SurePetCareSensorEntityDescription(
        key="entity_information",
        translation_key="entity_information",
        icon="mdi:information",
        value="name",
        picture=lambda device: device.photo,
        attributes=lambda entity: {
            "household_id": entity.device.household_id,
            "id": entity.device.id,
            "parent_device_id": entity.device.entity_info.parent_device_id,
            "photo": entity.device.photo,
        },
    ),
    SurePetCareSensorEntityDescription(
        key="battery_level",
        value="battery_level",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="%",
    ),
    SurePetCareSensorEntityDescription(
        key="rssi",
        translation_key="rssi",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        entity_category=EntityCategory.DIAGNOSTIC,
        value="status.signal.device_rssi",
        native_unit_of_measurement="dBm",
    ),
)
_feeder_events = (
    TimelineEventType.FEEDING,
    TimelineEventType.WEIGHT_CHANGED,
    TimelineEventType.WEIGHT_CHANGED_TARGET_MET,
    TimelineEventType.TARE,
)
_poseidon_events = (
    TimelineEventType.POSEIDON_DRINKING,
    TimelineEventType.POSEIDON_WEIGHT_CHANGED,
    TimelineEventType.POSEIDON_TARE,
)
SENSOR_FIELDS: dict[ProductId, tuple[SurePetCareSensorEntityDescription, ...]] = {
    ProductId.FEEDER_CONNECT: (
        *_device_fields,
        SurePetCareSensorEntityDescription(
            key="bowl_0_weight",
            translation_key="bowl_weight",
            translation_placeholders={"bowl": "One"},
            device_class=SensorDeviceClass.WEIGHT,
            state_class=SensorStateClass.MEASUREMENT,
            timeline_events=_feeder_events,
            value=lambda device, event: weight_reading(device, event, 0),
            native_unit_of_measurement=UnitOfMass.GRAMS,
        ),
        SurePetCareSensorEntityDescription(
            key="bowl_1_weight",
            translation_key="bowl_weight",
            translation_placeholders={"bowl": "Two"},
            device_class=SensorDeviceClass.WEIGHT,
            state_class=SensorStateClass.MEASUREMENT,
            timeline_events=_feeder_events,
            value=lambda device, event: weight_reading(device, event, 1),
            supported=has_second_bowl,
            native_unit_of_measurement=UnitOfMass.GRAMS,
        ),
        SurePetCareSensorEntityDescription(
            key="fill_percent",
            translation_key="fill_percent",
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
            icon="mdi:percent-outline",
            timeline_events=_feeder_events,
            value=fill_reading,
            native_unit_of_measurement="%",
        ),
        SurePetCareSensorEntityDescription(
            key="weight_capacity",
            translation_key="weight_capacity",
            device_class=SensorDeviceClass.WEIGHT,
            state_class=SensorStateClass.MEASUREMENT,
            value=lambda entity: sum_targets(entity.device),
            attributes=lambda entity: weight_capacity_extra(entity.device),
            native_unit_of_measurement=UnitOfMass.GRAMS,
        ),
    ),
    ProductId.NO_ID_DOG_BOWL_CONNECT: _device_fields,
    ProductId.PET_DOOR: _device_fields,
    ProductId.DUAL_SCAN_CONNECT: _device_fields,
    ProductId.DUAL_SCAN_PET_DOOR: _device_fields,
    ProductId.POSEIDON_CONNECT: (
        *_device_fields,
        SurePetCareSensorEntityDescription(
            key="bowl_volume",
            translation_key="bowl_volume",
            device_class=SensorDeviceClass.VOLUME_STORAGE,
            timeline_events=_poseidon_events,
            value=poseidon_volume,
            native_unit_of_measurement=UnitOfVolume.MILLILITERS,
        ),
        SurePetCareSensorEntityDescription(
            key="fill_percent",
            translation_key="fill_percent",
            state_class=SensorStateClass.MEASUREMENT,
            value=lambda entity: poseidon_bowl_value(entity.device, "fill_percent"),
            native_unit_of_measurement="%",
        ),
        SurePetCareSensorEntityDescription(
            key="last_filled_at",
            translation_key="last_filled_at",
            name=None,
            value=lambda entity: poseidon_bowl_value(entity.device, "last_filled_at"),
        ),
        SurePetCareSensorEntityDescription(
            key="last_zeroed_at",
            translation_key="last_zeroed_at",
            name=None,
            value=lambda entity: poseidon_bowl_value(entity.device, "last_zeroed_at"),
        ),
    ),
    ProductId.PET: (
        SurePetCareSensorEntityDescription(
            key="entity_information",
            translation_key="entity_information",
            icon="mdi:information",
            value="name",
            picture=lambda pet: pet.photo,
            attributes=lambda entity: {
                "household_id": entity.device.household_id,
                "id": entity.device.id,
                "parent_device_id": entity.device.entity_info.parent_device_id,
                "photo": entity.device.photo,
                "product_id": entity.device.product_id,
                "tag": entity.device.tag,
            },
        ),
        SurePetCareSensorEntityDescription(
            key="feeding",
            translation_key="feeding",
            icon="mdi:food-drumstick",
            device_class=SensorDeviceClass.WEIGHT,
            state_class=SensorStateClass.MEASUREMENT,
            timeline_events=(TimelineEventType.FEEDING,),
            value=lambda _, event: consumption_reading(event),
            native_unit_of_measurement=UnitOfMass.GRAMS,
            supported_products=(ProductId.FEEDER_CONNECT,),
        ),
        SurePetCareSensorEntityDescription(
            key="drinking",
            translation_key="drinking",
            icon="mdi:water",
            device_class=SensorDeviceClass.VOLUME,
            state_class=SensorStateClass.TOTAL,
            timeline_events=(TimelineEventType.POSEIDON_DRINKING,),
            value=lambda _, event: consumption_reading(event),
            native_unit_of_measurement=UnitOfVolume.MILLILITERS,
            supported_products=(ProductId.POSEIDON_CONNECT,),
        ),
        SurePetCareSensorEntityDescription(
            key="position",
            translation_key="position",
            icon="mdi:map-marker",
            timeline_events=(TimelineEventType.MOVEMENT,),
            value=lambda _, event: movement_reading(event),
            format_value=_position_label,
            supported_products=FLAP_PRODUCTS,
        ),
        SurePetCareSensorEntityDescription(
            key="devices",
            translation_key="devices",
            icon="mdi:devices",
            value="status.devices.count",
            attributes=lambda entity: {
                "devices": [item.id for item in entity.device.status.devices.items]
            },
            native_unit_of_measurement="pcs",
        ),
        SurePetCareSensorEntityDescription(
            key="last_activity",
            translation_key="last_activity",
            icon="mdi:history",
            supported_products=ACTIVITY_PRODUCTS,
            value=lambda _, event: last_activity_reading(event),
            format_value=_activity_label,
            timeline_events=(
                TimelineEventType.MOVEMENT,
                TimelineEventType.FEEDING,
                TimelineEventType.POSEIDON_DRINKING,
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
    entities = [
        SurePetCareSensor(coordinator, device, description)
        for device in coordinator.devices.values()
        for description in SENSOR_FIELDS.get(device.product, ())
    ]
    entities = [entity for entity in entities if entity.is_supported]
    async_add_entities(entities)


class SurePetCareSensor(SurePetCareBaseEntity, RestoreSensor):
    """A library-provided measurement or status."""

    entity_description: SurePetCareSensorEntityDescription

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state is not None and state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            data = await self.async_get_last_sensor_data()
            value = data.native_value if data is not None else state.state
            if data is None and (
                self.native_unit_of_measurement is not None
                or self.state_class is not None
            ):
                try:
                    value = float(state.state)
                    saved_unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
                    native_unit = self.native_unit_of_measurement
                    if saved_unit is not None and saved_unit != native_unit:
                        converter = UNIT_CONVERTERS.get(self.device_class)
                        if (
                            converter is None
                            or saved_unit not in converter.VALID_UNITS
                            or native_unit not in converter.VALID_UNITS
                        ):
                            raise ValueError(
                                f"Cannot restore {saved_unit!r} as {native_unit!r}"
                            )
                        value = converter.convert(value, saved_unit, native_unit)
                except ValueError as exc:
                    logger.warning("Cannot restore sensor %s: %s", self.entity_id, exc)
                    return
            self._update_state(value, dict(state.attributes))

    def _set_value(self, value: Any) -> None:
        self._attr_native_value = value

    @property
    def native_value(self) -> Any:
        value = self._attr_native_value
        if value is None:
            return None
        if self.entity_description.format_value is not None:
            return self.entity_description.format_value(self)
        value = serialize(value)
        if self.device_class == SensorDeviceClass.TIMESTAMP:
            return datetime.fromisoformat(value)
        return value

    @property
    def entity_picture(self) -> str | None:
        picture = self.entity_description.picture
        return picture(self.device) if picture is not None else None
