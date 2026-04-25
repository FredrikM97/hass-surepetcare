"""Support for Sure Petcare sensors."""

from dataclasses import dataclass
import logging
from types import MappingProxyType
from typing import Any

from surepcio import SurePetcareClient
from surepcio.enums import ProductId, PetLocation
from surepcio.devices import Pet
from surepcio.devices.pet import PetPositionResource
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.helpers.entity import EntityCategory
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfMass, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from custom_components.surepcha.method_field import MethodField

from .const import (
    COORDINATOR,
    COORDINATOR_DICT,
    DOMAIN,
    KEY_API,
    LOCATION_INSIDE,
    LOCATION_OUTSIDE,
    MANUAL_PROPERTIES,
    NAME,
    OPTION_DEVICES,
    PRODUCT_ID,
    OPTION_PROPERTIES,
)
from .coordinator import SurePetCareDeviceDataUpdateCoordinator
from .entity import (
    SurePetCareBaseEntity,
    SurePetCareBaseEntityDescription,
)
from .helper import (
    abs_sum_attr,
    avg_attr,
    index_attr,
    option_name,
    stringify,
)

logger = logging.getLogger(__name__)


def get_device_location(entry_options, position, key, default):
    """Return reconfigured location for device, or default."""
    return (
        entry_options[OPTION_DEVICES].get(str(position.device_id), {}).get(key, default)
    )


def get_manual_location(entry_options, position):
    """Return reconfigured manual location name for device, or default."""
    return (
        entry_options[OPTION_PROPERTIES]
        .get(MANUAL_PROPERTIES, {})
        .get(position.where.name.lower(), position.where.name.lower())
    )


def get_location(
    device: Pet, entry_options: MappingProxyType[str, Any]
) -> PetLocation | str | None:
    """Return PetLocation, or None if unknown.

    Uses reconfigured values for location_inside/location_outside if available.
    """
    position: PetPositionResource = getattr(device.status, "activity", None)

    if position is not None:
        if position.where == PetLocation.INSIDE:
            return get_device_location(
                entry_options,
                position,
                LOCATION_INSIDE,
                get_manual_location(entry_options, position),
            )
        elif position.where == PetLocation.OUTSIDE:
            return get_device_location(
                entry_options,
                position,
                LOCATION_OUTSIDE,
                get_manual_location(entry_options, position),
            )
    return None


@dataclass(frozen=True, kw_only=True)
class SurePetCareSensorEntityDescription(
    SurePetCareBaseEntityDescription, SensorEntityDescription
):
    """Describes SurePetCare sensor entity."""


SENSOR_DESCRIPTIONS_BATTERY: tuple[SurePetCareSensorEntityDescription, ...] = (
    SurePetCareSensorEntityDescription(
        key="battery_level",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        field=MethodField(path="battery_level"),
    ),
)

SENSOR_DESCRIPTIONS_DEVICE_INFORMATION: tuple[
    SurePetCareSensorEntityDescription, ...
] = (
    SurePetCareSensorEntityDescription(
        key="entity_information",
        translation_key="entity_information",
        icon="mdi:information",
        field=MethodField(
            path=NAME,
            get_extra_fn=lambda ctx: {
                "household_id": str(ctx.device.household_id),
                "id": str(ctx.device.id),
                "parent_device_id": stringify(ctx.device.entity_info.parent_device_id),
                "photo": ctx.device.photo,
            },
            entity_picture="photo",
        ),
    ),
)

SENSOR_DESCRIPTIONS_RSSI: tuple[SurePetCareSensorEntityDescription, ...] = (
    SurePetCareSensorEntityDescription(
        key="rssi",
        translation_key="rssi",
        native_unit_of_measurement="dBm",
        field=MethodField(
            get_fn=lambda ctx: ctx.device.status.signal.device_rssi,
        ),
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)

SENSOR_DESCRIPTIONS_PET_INFORMATION: tuple[SurePetCareSensorEntityDescription, ...] = (
    SurePetCareSensorEntityDescription(
        key="entity_information",
        translation_key="entity_information",
        icon="mdi:information",
        field=MethodField(
            path=NAME,
            get_extra_fn=lambda ctx: {
                "household_id": str(ctx.device.household_id),
                PRODUCT_ID: ctx.device.product_id,
                "tag": str(ctx.device.tag),
                "id": str(ctx.device.id),
                "parent_device_id": stringify(ctx.device.entity_info.parent_device_id),
                "photo": ctx.device.photo,
            },
            entity_picture="photo",
        ),
    ),
)

SENSORS: dict[str, tuple[SurePetCareSensorEntityDescription, ...]] = {
    ProductId.FEEDER_CONNECT: (
        SurePetCareSensorEntityDescription(
            key="bowl_0_weight",
            translation_key="bowl_weight",
            translation_placeholders={"bowl": "One"},
            state_class=SensorStateClass.MEASUREMENT,
            device_class=SensorDeviceClass.WEIGHT,
            native_unit_of_measurement=UnitOfMass.GRAMS,
            field=MethodField(
                path="status.bowl_status[0].current_weight",
                get_extra_fn=lambda ctx: {
                    "position": ctx.device.status.bowl_status[0].position.name.lower(),
                    "food_type": ctx.device.control.bowls.settings[
                        0
                    ].food_type.name.lower(),
                    "last_filled_at": ctx.device.status.bowl_status[0].last_filled_at,
                    "last_zeroed_at": ctx.device.status.bowl_status[0].last_zeroed_at,
                    "last_fill_weight": ctx.device.status.bowl_status[
                        0
                    ].last_fill_weight,
                },
            ),
        ),
        SurePetCareSensorEntityDescription(
            key="bowl_1_weight",
            translation_key="bowl_weight",
            translation_placeholders={"bowl": "Two"},
            state_class=SensorStateClass.MEASUREMENT,
            device_class=SensorDeviceClass.WEIGHT,
            native_unit_of_measurement=UnitOfMass.GRAMS,
            field=MethodField(
                path="status.bowl_status[1].current_weight",
                get_extra_fn=lambda ctx: {
                    "position": ctx.device.status.bowl_status[1].position.name.lower(),
                    "food_type": ctx.device.control.bowls.settings[
                        1
                    ].food_type.name.lower(),
                    "substance_type": ctx.device.status.bowl_status[1].substance_type,
                    "last_filled_at": ctx.device.status.bowl_status[1].last_filled_at,
                    "last_zeroed_at": ctx.device.status.bowl_status[1].last_zeroed_at,
                    "last_fill_weight": ctx.device.status.bowl_status[
                        1
                    ].last_fill_weight,
                },
            ),
        ),
        SurePetCareSensorEntityDescription(
            key="fill_percent",
            translation_key="fill_percent",
            icon="mdi:percent-outline",
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=PERCENTAGE,
            suggested_display_precision=1,
            field=MethodField(
                path="status.fill_percentages.total",
                get_extra_fn=lambda ctx: (
                    {
                        f"bowl_{i}_fill_percent": percent
                        for i, percent in (
                            ctx.device.status.fill_percentages.get("per_bowl", {}) or {}
                        ).items()
                    }
                    if ctx.device.status.fill_percentages
                    else {}
                ),
            ),
        ),
        SurePetCareSensorEntityDescription(
            key="weight_capacity",
            translation_key="weight_capacity",
            state_class=SensorStateClass.MEASUREMENT,
            device_class=SensorDeviceClass.WEIGHT,
            native_unit_of_measurement=UnitOfMass.GRAMS,
            field=MethodField(
                get_fn=lambda ctx: sum(
                    w.target
                    for w in getattr(
                        getattr(getattr(ctx.device, "control"), "bowls"), "settings", []
                    )
                ),
                get_extra_fn=lambda ctx: {
                    "bowls_0_target": index_attr(
                        ctx.device.control.bowls.settings, 0, attr="target"
                    ),
                    "bowls_1_target": index_attr(
                        ctx.device.control.bowls.settings, 1, attr="target"
                    ),
                },
            ),
        ),
        *SENSOR_DESCRIPTIONS_RSSI,
        *SENSOR_DESCRIPTIONS_BATTERY,
        *SENSOR_DESCRIPTIONS_DEVICE_INFORMATION,
    ),
    ProductId.DUAL_SCAN_PET_DOOR: (
        *SENSOR_DESCRIPTIONS_RSSI,
        *SENSOR_DESCRIPTIONS_BATTERY,
        *SENSOR_DESCRIPTIONS_DEVICE_INFORMATION,
    ),
    ProductId.DUAL_SCAN_CONNECT: (
        *SENSOR_DESCRIPTIONS_RSSI,
        *SENSOR_DESCRIPTIONS_BATTERY,
        *SENSOR_DESCRIPTIONS_DEVICE_INFORMATION,
    ),
    ProductId.PET_DOOR: (
        *SENSOR_DESCRIPTIONS_RSSI,
        *SENSOR_DESCRIPTIONS_BATTERY,
        *SENSOR_DESCRIPTIONS_DEVICE_INFORMATION,
    ),
    ProductId.POSEIDON_CONNECT: (
        SurePetCareSensorEntityDescription(
            key="bowl_volume",
            translation_key="bowl_volume",
            translation_placeholders={"bowl": ""},
            device_class=SensorDeviceClass.VOLUME_STORAGE,
            native_unit_of_measurement=UnitOfVolume.MILLILITERS,
            field=MethodField(
                path="status.bowl_status[0].current_weight",
                get_extra_fn=lambda ctx: {
                    "last_filled_at": ctx.device.status.bowl_status[0].last_filled_at,
                    "last_zeroed_at": ctx.device.status.bowl_status[0].last_zeroed_at,
                    "last_fill_weight": ctx.device.status.bowl_status[
                        0
                    ].last_fill_weight,
                },
            ),
        ),
        SurePetCareSensorEntityDescription(
            key="fill_percent",
            translation_key="fill_percent",
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=PERCENTAGE,
            field=MethodField(
                get_fn=lambda ctx: avg_attr(
                    getattr(ctx.device.status, "bowl_status", []), "fill_percent"
                ),
            ),
        ),
        *SENSOR_DESCRIPTIONS_RSSI,
        *SENSOR_DESCRIPTIONS_BATTERY,
        *SENSOR_DESCRIPTIONS_DEVICE_INFORMATION,
    ),
    ProductId.HUB: (),
    ProductId.PET: (
        SurePetCareSensorEntityDescription(
            key="feeding",
            translation_key="feeding",
            icon="mdi:food-drumstick",
            device_class=SensorDeviceClass.WEIGHT,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfMass.GRAMS,
            entity_registry_enabled_default=False,
            field=MethodField(
                get_fn=lambda ctx: abs_sum_attr(ctx.device.status.feeding, "change"),
                get_extra_fn=lambda ctx: {
                    "device_id": str(ctx.device.status.feeding.device_id),
                    "id": str(ctx.device.status.feeding.id),
                    "at": ctx.device.status.feeding.at,
                    "tag_id": str(ctx.device.status.feeding.tag_id),
                    "change_0": abs(
                        index_attr(ctx.device.status.feeding.change, 0, default=0)
                    ),
                    "change_1": abs(
                        index_attr(ctx.device.status.feeding.change, 1, default=0)
                    ),
                },
            ),
        ),
        SurePetCareSensorEntityDescription(
            key="position",
            translation_key="position",
            icon="mdi:map-marker",
            entity_registry_enabled_default=False,
            field=MethodField(
                get_fn=lambda ctx: get_location(ctx.device, ctx.options),
                get_extra_fn=lambda ctx: {
                    "device_id": str(ctx.device.status.activity.device_id),
                    "id": str(ctx.device.status.activity.id),
                    "since": ctx.device.status.activity.since,
                    "where": ctx.device.status.activity.where,
                    "tag_id": str(ctx.device.status.activity.tag_id),
                },
            ),
        ),
        SurePetCareSensorEntityDescription(
            key="drinking",
            translation_key="drinking",
            icon="mdi:water",
            state_class=SensorStateClass.MEASUREMENT,
            device_class=SensorDeviceClass.VOLUME,
            native_unit_of_measurement=UnitOfVolume.MILLILITERS,
            entity_registry_enabled_default=False,
            field=MethodField(
                get_fn=lambda ctx: abs_sum_attr(ctx.device.status.drinking, "change"),
                get_extra_fn=lambda ctx: {
                    "device_id": str(ctx.device.status.drinking.device_id),
                    "id": str(ctx.device.status.drinking.id),
                    "at": ctx.device.status.drinking.at,
                    "tag_id": str(ctx.device.status.drinking.tag_id),
                    "change_0": abs(
                        index_attr(ctx.device.status.drinking.change, 0, default=0)
                    ),
                    "change_1": abs(
                        index_attr(ctx.device.status.drinking.change, 1, default=0)
                    ),
                },
            ),
        ),
        SurePetCareSensorEntityDescription(
            key="devices",
            translation_key="devices",
            icon="mdi:devices",
            native_unit_of_measurement="pcs",
            field=MethodField(
                path="status.devices.count",
                get_extra_fn=lambda ctx: {
                    "devices": [
                        str(item.id) for item in ctx.device.status.devices.items
                    ]
                },
            ),
        ),
        SurePetCareSensorEntityDescription(
            key="last_activity",
            translation_key="last_activity",
            icon="mdi:history",
            entity_registry_enabled_default=False,
            field=MethodField(
                get_fn=lambda ctx: (
                    option_name(ctx.options, ctx.device.status.last_activity.device_id)
                    if ctx.device.status.last_activity
                    else None
                ),
                get_extra_fn=lambda ctx: (
                    {"device": str(ctx.device.status.last_activity.device_id)}
                    if ctx.device.status.last_activity
                    else {}
                ),
            ),
        ),
        *SENSOR_DESCRIPTIONS_PET_INFORMATION,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up SurePetCare sensors for each matching device."""
    coordinator_data = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR]
    client = coordinator_data[KEY_API]

    entities = []
    for device_coordinator in coordinator_data[COORDINATOR_DICT].values():
        descriptions = SENSORS.get(device_coordinator.product_id, ())
        entities.extend(
            [
                SurePetCareSensor(
                    device_coordinator,
                    client,
                    description=description,
                )
                for description in descriptions
            ]
        )
    async_add_entities(entities, update_before_add=True)


class SurePetCareSensor(SurePetCareBaseEntity, SensorEntity):
    """The platform class required by Home Assistant."""

    entity_description: SurePetCareSensorEntityDescription

    def __init__(
        self,
        device_coordinator: SurePetCareDeviceDataUpdateCoordinator,
        client: SurePetcareClient,
        description: SurePetCareSensorEntityDescription,
    ) -> None:
        """Initialize a Surepetcare sensor."""
        super().__init__(
            device_coordinator=device_coordinator,
            client=client,
        )
        self.entity_description = description
        self._attr_unique_id = f"{self._attr_unique_id}-{description.key}"

    @property
    def entity_picture(self) -> str | None:
        """Return the entity picture URL to use for the entity."""
        if entity_picture := self.entity_description.field.get_entity_picture(
            self._device
        ):
            return entity_picture
        return None
