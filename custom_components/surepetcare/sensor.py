"""TODO."""

import re
from config.custom_components.surepetcare.const import DOMAIN
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from surepetcare.enums import ProductId


def _sanitize_id(value: str) -> str:
    """Sanitize a string to be used as an ID (alphanumeric, dash, underscore)."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", value)


class SurePetcareBaseSensor(SensorEntity):
    """Base class for SurePetcare sensors with device_info."""

    def __init__(self, coordinator, data) -> None:
        """TODO."""
        self.coordinator = coordinator
        self.device = coordinator.data.get(data["id"], {})
        self.sensor_name = data["name"]

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.device.id)},
            name=self.device.name,
            manufacturer="Sure Petcare",
            model_id=self.device.product_id,
            via_device=(DOMAIN, self.device.id),
        )

    @property
    def unique_id(self) -> str:
        """Return a unique ID for this sensor."""
        return f"{_sanitize_id(str(self.device.id))}_{_sanitize_id(self.sensor_name)}"

    @property
    def name(self):
        """TODO."""
        return f"{self.sensor_name}"


class PetLocationSensor(SurePetcareBaseSensor):
    """Representation of a pet's location sensor."""

    @property
    def state(self):
        """TODO."""
        return 20  # Placeholder for location state

    @property
    def extra_state_attributes(self):
        """TODO."""
        # Todo: Map to data values
        return {
            "location_inside": "test1",
            "location_outside": "test2",
        }

    @property
    def unit_of_measurement(self):
        """TODO."""
        return "Location"


class PetLastFedSensor(SurePetcareBaseSensor):
    """Representation of a pet's last fed sensor."""

    @property
    def state(self):
        """TODO."""
        return 5  # Placeholder for last fed time

    @property
    def unit_of_measurement(self):
        """TODO."""
        return "Time"


class BatterySensor(SurePetcareBaseSensor):
    """Representation of a Device's battery sensor."""

    @property
    def state(self):
        """TODO."""
        return self.device.battery_level  # Placeholder for battery percentage

    @property
    def unit_of_measurement(self):
        """TODO."""
        return "%"


# Map product IDs to their sensors
PRODUCT_SENSOR_MAPPINGS = {
    ProductId.FEEDER_CONNECT: {
        "consumption": PetLastFedSensor,
        "battery": BatterySensor,
    },
    ProductId.DUAL_SCAN_PET_DOOR: {
        "location": PetLocationSensor,
        "battery": BatterySensor,
    },
}


# Main entry: devices is a list
async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
):
    coordinator = hass.data[DOMAIN]["coordinator"]
    entities: list = []

    # Add sensors for all devices managed by the coordinator
    for device in coordinator.devices:
        product_id = device.product_id

        sensor_map = PRODUCT_SENSOR_MAPPINGS.get(product_id, {})
        entities.extend(
            [
                sensor_cls(coordinator, {"id": device.id, "name": name})
                for name, sensor_cls in sensor_map.items()
            ]
        )

    async_add_entities(entities, update_before_add=True)
