"""TODO."""

from collections.abc import Callable
from dataclasses import asdict, dataclass
import logging
from typing import Any, cast

from surepetcare.client import SurePetcareClient
from surepetcare.enums import ProductId

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfMass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.entity import EntityCategory

from .const import COORDINATOR, COORDINATOR_DICT, DOMAIN, KEY_API
from .coordinator import SurePetCareDeviceDataUpdateCoordinator
from .entity import SurePetCareBaseEntity

logger = logging.getLogger(__name__)


def get_feeding_events(device: Any) -> dict[str, Any] | None:
    """Return feeding events as a dict with timestamp and weights for both bowls."""
    feeding_event = getattr(device, "feeding", None)
    if feeding_event:
        first_feeding_event = feeding_event[-1]
        return {
            "native": abs(first_feeding_event.weights[0].change)
            + abs(first_feeding_event.weights[1].change),
            "data": {
                "device_id": first_feeding_event.device_id,
                "duration": first_feeding_event.duration,
                "timestamp": first_feeding_event.from_,
                "bowl_1": {
                    "change": first_feeding_event.weights[0].change,
                    "weight": first_feeding_event.weights[0].weight,
                },
                "bowl_2": {
                    "change": first_feeding_event.weights[1].change,
                    "weight": first_feeding_event.weights[1].weight,
                },
            },
        }
    return None


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
class SurePetCareSensorEntityDescription(SensorEntityDescription):
    """Describes SurePetCare sensor entity."""

    value: Callable[[Any, dict[str, Any] | None], Any | None] = None
    frozen: bool = False


SENSOR_DESCRIPTIONS_BATTERY: tuple[SurePetCareSensorEntityDescription, ...] = (
    SurePetCareSensorEntityDescription(
        key="battery_level",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        value=lambda device, r: cast(int, device.battery_level),
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
            value=lambda device, r: {
                "native": device.bowls[0].current_weight,
                "data": asdict(device.bowls[0]),
            }
            if len(device.bowls) > 0
            else None,
        ),
        SurePetCareSensorEntityDescription(
            key="bowl_2_weight",
            translation_key="bowl_2_weight",
            state_class=SensorStateClass.MEASUREMENT,
            device_class=SensorDeviceClass.WEIGHT,
            native_unit_of_measurement=UnitOfMass.GRAMS,
            value=lambda device, r: {
                "native": device.bowls[1].current_weight,
                "data": asdict(device.bowls[1]),
            }
            if len(device.bowls) > 1
            else None,
        ),
        SurePetCareSensorEntityDescription(
            key="weight_capacity",
            translation_key="weight_capacity",
            state_class=SensorStateClass.MEASUREMENT,
            value=lambda device, r: {
                "native": sum([w.full_weight for w in device.bowl_targets]),
                "data": {"target": device.bowl_targets},
            },
        ),
        SurePetCareSensorEntityDescription(
            key="tare",
            translation_key="tare",
            value=lambda device, r: {
                "native": device.raw_data["control"].get("tare"),
                "data": None,
            },
            entity_registry_enabled_default=False,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        SurePetCareSensorEntityDescription(
            key="lid_delay",
            translation_key="lid_delay",
            value=lambda device, r: {
                "native": device.lid_delay,
                "data": None,
            },
            entity_registry_enabled_default=False,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        SurePetCareSensorEntityDescription(
            key="training_mode",
            translation_key="training_mode",
            value=lambda device, r: {
                "native": device.raw_data["control"]["training_mode"],
                "data": None,
            },
            entity_registry_enabled_default=False,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        SurePetCareSensorEntityDescription(
            key="rssi",
            translation_key="rssi",
            value=lambda device, r: {
                "native": device.raw_data["status"]["signal"]["device_rssi"],
                "data": None,
            },
        ),
        *SENSOR_DESCRIPTIONS_BATTERY,
    ),
    ProductId.DUAL_SCAN_PET_DOOR: (
        *SENSOR_DESCRIPTIONS_BATTERY,
        SurePetCareSensorEntityDescription(
            key="location",
            translation_key="location",
            value=lambda device, r: get_location(device, r),
        ),
    ),
    ProductId.HUB: (),
    ProductId.PET: (
        SurePetCareSensorEntityDescription(
            key="feeding",
            translation_key="feeding",
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfMass.GRAMS,
            value=lambda device, r: get_feeding_events(device),
        ),
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
            entities.append(SurePetCareMainSensor(device_coordinator, client))
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
    _attr_native_value: Any = None

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
    def native_value(self) -> Any:
        """Return the sensor value."""
        value = self.entity_description.value(self.coordinator.data, self.subentry_data)
        if isinstance(value, dict):
            return value.get("native")
        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra state attributes."""
        value = self.entity_description.value(self.coordinator.data, self.subentry_data)
        if isinstance(value, dict):
            return value.get("data")
        return None


class SurePetCareMainSensor(SurePetCareBaseEntity, SensorEntity):
    # Just a placeholder for the main sensor entity. Should contain only static data

    entity_description: SurePetCareSensorEntityDescription
    _attr_native_value: Any = None

    def __init__(
        self,
        device_coordinator: SurePetCareDeviceDataUpdateCoordinator,
        client: SurePetcareClient,
    ) -> None:
        """Initialize a Surepetcare sensor."""
        super().__init__(
            device_coordinator=device_coordinator,
            client=client,
        )

        self.entity_description = SurePetCareSensorEntityDescription(
            key="entity_information", translation_key="entity_information"
        )

        self._attr_unique_id = f"{self._attr_unique_id}-{self.entity_description.key}"

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        return self.coordinator.data.name

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra state attributes."""
        device = self.coordinator.data
        return {
            "household_id": getattr(device, "household_id", None),
            "product_id": getattr(device, "product_id", None),
            "tag": getattr(device, "tag", None),
            "id": getattr(device, "id", None),
            "parent_device_id": getattr(device, "parent_device_id", None),
        }

    @property
    def entity_picture(self) -> str | None:
        """Return the entity picture URL."""
        return self.coordinator._photo  # Or wherever your photo URL is stored
