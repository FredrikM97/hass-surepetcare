from config.custom_components.hacs.const import DOMAIN
from config.custom_components.surepetcare.binary_sensor import DeviceInfo
from homeassistant.helpers.entity import Entity
import re


def _sanitize_id(value: str) -> str:
    """Sanitize a string to be used as an ID (alphanumeric, dash, underscore)."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", value)


class SurePetcareBaseEntity(Entity):
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
