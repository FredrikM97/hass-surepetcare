"""TODO."""

import logging
from .const import DOMAIN
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from surepetcare.enums import ProductId
from .entity import SurePetcareBaseEntity

logger = logging.getLogger(__name__)


class OnlineSensor(SurePetcareBaseEntity, BinarySensorEntity):
    """Representation of a pet's location sensor."""

    def __init__(self, coordinator, data) -> None:
        """Initialize the online sensor."""
        super().__init__(coordinator, data)
        self._attr_is_on = coordinator.data[data["id"]].online


# Map product IDs to their sensors
PRODUCT_SENSOR_MAPPINGS = {
    ProductId.HUB: {"online": OnlineSensor},
    ProductId.FEEDER_CONNECT: {"online": OnlineSensor},
    ProductId.DUAL_SCAN_PET_DOOR: {"online": OnlineSensor},
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

        if product_id not in PRODUCT_SENSOR_MAPPINGS:
            continue
        sensor_map = PRODUCT_SENSOR_MAPPINGS.get(product_id, {})
        entities.extend(
            [
                sensor_cls(coordinator, {"id": device.id, "name": name})
                for name, sensor_cls in sensor_map.items()
            ]
        )

    async_add_entities(entities, update_before_add=True)
