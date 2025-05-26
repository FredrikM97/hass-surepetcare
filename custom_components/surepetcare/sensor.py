from homeassistant.components.sensor import (
    SensorEntity,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from surepetcare.enums import ProductId

class SurePetcareBaseSensor(SensorEntity):
    """Base class for SurePetcare sensors with device_info."""

    def __init__(self, coordinator, device, data):
        self.coordinator = coordinator
        self.device = device

    @property
    def device_info(self):
        return {
            "identifiers": {("surepetcare", self.device["id"])},
            "name": self.device.get("name"),
            "manufacturer": "Sure Petcare",
            "model": self.device.get("product_id"),
        }

class PetLocationSensor(SensorEntity):
    """Representation of a pet's location sensor."""

    def __init__(self, coordinator, flow, data):
        self.coordinator = coordinator
        self.flow = flow
        self._data = data

    @property
    def name(self):
        return f"sensor.{self.data['id']}_location"

    @property
    def state(self):
        return self.coordinator.data["location"]

    @property
    def extra_state_attributes(self):
        # Todo: Map to data values
        return {
            "location_inside": self.flow.get("location_inside"),
            "location_outside": self.flow.get("location_outside"),
        }
    
    @property
    def unit_of_measurement(self):
        return "Location"

    async def async_update(self):
        """Fetch new data from the API."""
        await self.coordinator.async_request_refresh()


class PetLastFedSensor(SensorEntity):
    """Representation of a pet's last fed sensor."""

    def __init__(self, coordinator, flow, data):
        self.coordinator = coordinator
        self.flow = flow
        self._data = data

    @property
    def name(self):
        return f"sensor.{self.data['id']}_last_fed"

    @property
    def state(self):
        return self.coordinator.data["last_fed"]

    @property
    def unit_of_measurement(self):
        return "Time"

    async def async_update(self):
        """Fetch new data from the API."""
        await self.coordinator.async_request_refresh()


class BatterySensor(SensorEntity):
    """Representation of a Device's battery sensor."""

    def __init__(self, coordinator, device, data):
        self.coordinator = coordinator
        self.device = device

    @property
    def name(self):
        return f"sensor.{self.data['id']}_battery"

    @property
    def state(self):
        return self.coordinator.data.get("battery")

    @property
    def unit_of_measurement(self):
        return "%"

    async def async_update(self):
        """Fetch new data from the API."""
        await self.coordinator.async_request_refresh()


# Map product IDs to their sensors
PRODUCT_SENSOR_MAPPINGS = {
    ProductId.FEEDER_CONNECT: {
        "last_fed": PetLastFedSensor,
    },
    ProductId.DUAL_SCAN_PET_DOOR: {
        "location": PetLocationSensor,
        "battery": BatterySensor,
    },
}

 # Main entry: devices is a list
async def async_setup_entry(hass, entry, async_add_entities: AddEntitiesCallback):
    coordinator = hass.data.get("surepetcare_coordinator")
    entities = []
    
    for subentry in entry.subentries.values():
        product_id = subentry.data['product_id']
        for device_id, device_data in subentry.data['device'].items():
            sensor_map = PRODUCT_SENSOR_MAPPINGS.get(product_id, {})
            data = find_device_by_id(entry.data['devices'], device_id)
            for sensor_cls in sensor_map.values():
                entities.append(sensor_cls(coordinator, device_data, data))

    async_add_entities(entities)

def find_device_by_id(devices, device_id):
    return next((d for d in devices if str(d['id']) == device_id), None)
