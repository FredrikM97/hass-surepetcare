"""TODO."""

from collections.abc import Callable
from dataclasses import dataclass
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
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import COORDINATOR, COORDINATOR_LIST, DOMAIN, KEY_API
from .coordinator import SurePetCareDeviceDataUpdateCoordinator
from .entity import SurePetCareBaseEntity

logger = logging.getLogger(__name__)


def get_feeding_events(device: Any) -> list[dict[str, Any]] | None:
    """Return feeding events as a list of dicts with timestamp and weights for both bowls."""
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

    value: Callable[[Any, dict[str, Any] | None], Any | None]
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
SENSOR_DESCRIPTIONS_PRODUCT: tuple[SurePetCareSensorEntityDescription, ...] = (
    SurePetCareSensorEntityDescription(
        key="info",
        translation_key="info",
        value=lambda device, r: {
            "native": "Up to date",
            "data": {
                "household_id": getattr(device, "household_id", None),
                "product_id": getattr(device, "product_id", None),
                "tag": getattr(device, "tag", None),
                "id": getattr(device, "id", None),
                "parent_device_id": getattr(device, "parent_device_id", None),
            },
        },
        frozen=True,
    ),
)
SENSORS: dict[str, tuple[SurePetCareSensorEntityDescription, ...]] = {
    ProductId.FEEDER_CONNECT: (
        SurePetCareSensorEntityDescription(
            key="consumption",
            translation_key="consumption",
            state_class=SensorStateClass.MEASUREMENT,
            value=lambda device, r: cast(int, 5),
        ),
        *SENSOR_DESCRIPTIONS_PRODUCT,
        *SENSOR_DESCRIPTIONS_BATTERY,
    ),
    ProductId.DUAL_SCAN_PET_DOOR: (
        *SENSOR_DESCRIPTIONS_PRODUCT,
        *SENSOR_DESCRIPTIONS_BATTERY,
        SurePetCareSensorEntityDescription(
            key="location",
            translation_key="location",
            value=lambda device, r: get_location(device, r),
        ),
    ),
    ProductId.HUB: (*SENSOR_DESCRIPTIONS_PRODUCT,),
    ProductId.PET: (
        SurePetCareSensorEntityDescription(
            key="feeding",
            translation_key="feeding",
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement="g",
            value=lambda device, r: get_feeding_events(device),
        ),
        *SENSOR_DESCRIPTIONS_PRODUCT,
    ),
}


def build_device_config_map(config_entry: ConfigEntry) -> dict[str, dict[str, Any]]:
    """Build a mapping from device ID to subentry config data."""
    return {
        str(subentry.data.get("id")): subentry.data
        for subentry in config_entry.subentries.values()
        if "id" in subentry.data
    }


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up SurePetCare sensors for each matching subentry device."""
    coordinator_data = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR]
    client = coordinator_data[KEY_API]
    coordinators_by_id = {
        str(coordinator.device.id): coordinator
        for coordinator in coordinator_data[COORDINATOR_LIST]
    }
    # Expose subentry data to all sensors since some depends on each other
    subentry_data = build_device_config_map(config_entry)
    for subentry_id, subentry in config_entry.subentries.items():
        device_id = subentry.data.get("id")
        if not device_id:
            continue

        if coordinator := coordinators_by_id.get(device_id):
            descriptions = SENSORS.get(coordinator.device.product_id, ())
            if not descriptions:
                continue
            entities = []
            for description in descriptions:
                entities.append(
                    SurePetCareSensor(
                        coordinator,
                        client,
                        description=description,
                        subentry_data=subentry_data,
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
        subentry_data: dict[str, Any] = None,
    ) -> None:
        """Initialize a Surepetcare sensor."""
        super().__init__(
            device_coordinator=device_coordinator,
            client=client,
        )
        self.subentry_data = subentry_data
        self.entity_description = description
        self._attr_unique_id = f"{self._attr_unique_id}-{description.key}"
        self._refresh()  # Set initial state

    def _refresh(self) -> None:
        """Refresh the device."""
        if (
            getattr(self.entity_description, "frozen", False)
            and self._attr_native_value is not None
        ):
            # If the sensor is frozen, do not update its value
            return
        value = self.entity_description.value(
            self.coordinator.data,
            self.subentry_data,
        )
        if value is None:
            # Just skip and continue without changing
            return
        if isinstance(value, dict):
            # Just temporarily hack so it does not show up as unknown
            self.native_value = value.get("native", "Unknown native value")
            self.extra_state_attributes = value.get("data", "Unknown data")
            return

        self._attr_native_value = value
