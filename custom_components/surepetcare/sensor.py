"""TODO."""

from dataclasses import dataclass
import logging
from typing import Any

from surepetcare.client import SurePetcareClient
from surepetcare.enums import ProductId

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
import dataclasses as dc
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfMass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import COORDINATOR, COORDINATOR_DICT, DOMAIN, KEY_API
from .coordinator import SurePetCareDeviceDataUpdateCoordinator
from .entity import (
    SurePetCareBaseEntity,
    SurePetCareBaseEntityDescription,
)

logger = logging.getLogger(__name__)


def get_location(device: Any, reconfig) -> bool | None:
    """Return True if pet is inside, False if outside, or None if unknown.

    Uses reconfigured values for location_inside/location_outside if available.
    """

    if movement := getattr(device, "movement", []):
        latest = movement[0] if isinstance(movement, list) else movement

        # Get the names of the locations from the reconfiguration data
        location_inside = reconfig.get(latest.device_id).get("location_inside")
        location_outside = reconfig.get(latest.device_id).get("location_outside")

        if getattr(latest, "active", False):
            return location_inside if location_inside is not None else True
        return location_outside if location_outside is not None else False
    return None


@dataclass(frozen=True, kw_only=True)
class SurePetCareSensorEntityDescription(
    SurePetCareBaseEntityDescription, SensorEntityDescription
):
    """Describes SurePetCare sensor entity."""

    extra_field: dict[str, str] = dc.field(default_factory=dict)


SENSOR_DESCRIPTIONS_BATTERY: tuple[SurePetCareSensorEntityDescription, ...] = (
    SurePetCareSensorEntityDescription(
        key="battery_level",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        field="battery_level",
    ),
)

SENSOR_DESCRIPTIONS_DEVICE_INFORMATION: tuple[
    SurePetCareSensorEntityDescription, ...
] = (
    SurePetCareSensorEntityDescription(
        key="entity_information",
        translation_key="entity_information",
        icon="mdi:information",
        field="name",
        extra_field={
            "household_id": "household_id",
            "product_id": "product_id",
            "id": "id",
            "parent_device_id": "parent_device_id",
        },
    ),
)

SENSOR_DESCRIPTIONS_PET_INFORMATION: tuple[SurePetCareSensorEntityDescription, ...] = (
    SurePetCareSensorEntityDescription(
        key="entity_information",
        translation_key="entity_information",
        icon="mdi:information",
        field="name",
        extra_field={
            "household_id": "household_id",
            "product_id": "product_id",
            "tag": "tag",
            "id": "id",
            "parent_device_id": "parent_device_id",
        },
    ),
)

SENSORS: dict[str, tuple[SurePetCareSensorEntityDescription, ...]] = {
    ProductId.FEEDER_CONNECT: (
        SurePetCareSensorEntityDescription(
            key="bowl_1_weight",
            translation_key="bowl_1_weight",
            state_class=SensorStateClass.MEASUREMENT,
            device_class=SensorDeviceClass.WEIGHT,
            native_unit_of_measurement=UnitOfMass.GRAMS,
            field="bowls.0.current_weight",
            extra_field={
                "position": "bowls.0.position",
                "food_type": "bowls.0.food_type",
                "substance_type": "bowls.0.substance_type",
                "current_weight": "bowls.0.current_weight",
                "last_filled_at": "bowls.0.last_filled_at",
                "last_zeroed_at": "bowls.0.last_zeroed_at",
                "last_fill_weight": "bowls.0.last_fill_weight",
                "fill_percentage": "bowls.0.fill_percentage",
            },
        ),
        SurePetCareSensorEntityDescription(
            key="bowl_2_weight",
            translation_key="bowl_2_weight",
            state_class=SensorStateClass.MEASUREMENT,
            device_class=SensorDeviceClass.WEIGHT,
            native_unit_of_measurement=UnitOfMass.GRAMS,
            field="bowls.1.current_weight",
            extra_field={
                "position": "bowls.1.position",
                "food_type": "bowls.1.food_type",
                "substance_type": "bowls.1.substance_type",
                "current_weight": "bowls.1.current_weight",
                "last_filled_at": "bowls.1.last_filled_at",
                "last_zeroed_at": "bowls.1.last_zeroed_at",
                "last_fill_weight": "bowls.1.last_fill_weight",
                "fill_percentage": "bowls.1.fill_percentage",
            },
        ),
        SurePetCareSensorEntityDescription(
            key="weight_capacity",
            translation_key="weight_capacity",
            state_class=SensorStateClass.MEASUREMENT,
            field_fn=lambda device, r: sum(
                w.full_weight for w in getattr(device, "bowl_targets", [])
            ),
            extra_field={
                "food_type": "bowl_targets.0.food_type",
                "full_weight": "bowl_targets.0.full_weight",
            },
        ),
        SurePetCareSensorEntityDescription(
            key="tare",
            translation_key="tare",
            field="raw_data.control.tare",
            entity_registry_enabled_default=False,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        SurePetCareSensorEntityDescription(
            key="lid_delay",
            translation_key="lid_delay",
            field="lid_delay",
            entity_registry_enabled_default=False,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        SurePetCareSensorEntityDescription(
            key="training_mode",
            translation_key="training_mode",
            field="raw_data.control.training_mode",
            entity_registry_enabled_default=False,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        SurePetCareSensorEntityDescription(
            key="rssi",
            translation_key="rssi",
            field="raw_data.status.signal.device_rssi",
        ),
        *SENSOR_DESCRIPTIONS_BATTERY,
        *SENSOR_DESCRIPTIONS_DEVICE_INFORMATION,
    ),
    ProductId.DUAL_SCAN_PET_DOOR: (
        *SENSOR_DESCRIPTIONS_BATTERY,
        SurePetCareSensorEntityDescription(
            key="location",
            translation_key="location",
            field_fn=get_location,
        ),
        *SENSOR_DESCRIPTIONS_DEVICE_INFORMATION,
    ),
    ProductId.HUB: (),
    ProductId.PET: (
        SurePetCareSensorEntityDescription(
            key="feeding",
            translation_key="feeding",
            device_class=SensorDeviceClass.WEIGHT,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfMass.GRAMS,
            field_fn=lambda device, r: abs(sum(
                c
                for c in (
                    getattr(w, "change", 0)
                    for w in getattr(getattr(device, "feeding", [])[-1], "weights", [])
                )
                if c < 0
            ))
            if getattr(device, "feeding", [])
            else 0,
            extra_field={  # Multiple values might be returned but we can only use latest one right now
                "device_id": "feeding.-1.device_id",
                "duration": "feeding.-1.duration",
                "from": "feeding.-1.from_",
                "weight_change_0": "feeding.-1.weights.0.change",
                "weight_change_1": "feeding.-1.weights.1.change",
            },
        ),
        *SENSOR_DESCRIPTIONS_PET_INFORMATION,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up SurePetCare sensors for each matching subentry device."""
    coordinator_data = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR]
    client = coordinator_data[KEY_API]

    for subentry_id, subentry in config_entry.subentries.items():
        device_id = subentry.data.get("id")
        if not device_id:
            continue

        if device_coordinator := coordinator_data[COORDINATOR_DICT].get(device_id):
            descriptions = SENSORS.get(device_coordinator.product_id, ())
            if not descriptions:
                continue
            entities = []
            for description in descriptions:
                entities.append(
                    SurePetCareSensor(
                        device_coordinator,
                        client,
                        description=description,
                        subentry_data=subentry.data,
                    )
                )
            async_add_entities(
                entities,
                update_before_add=True,
                config_subentry_id=subentry_id,
            )


class SurePetCareSensor(SurePetCareBaseEntity, SensorEntity):
    """The platform class required by Home Assistant."""

    entity_description: SurePetCareSensorEntityDescription

    def __init__(
        self,
        device_coordinator: SurePetCareDeviceDataUpdateCoordinator,
        client: SurePetcareClient,
        description: SurePetCareSensorEntityDescription,
        subentry_data: dict[str, Any] | None = None,
    ) -> None:
        """Initialize a Surepetcare sensor."""
        super().__init__(
            device_coordinator=device_coordinator,
            client=client,
        )
        self.subentry_data = subentry_data
        self.entity_description = description
        self._attr_unique_id = f"{self._attr_unique_id}-{description.key}"

    @property
    def entity_picture(self) -> str | None:
        """Return the entity picture URL."""
        if self.entity_description.icon:
            return self.coordinator.data.photo
        return None
