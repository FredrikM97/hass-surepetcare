"""TODO."""

from homeassistant.components.binary_sensor import BinarySensorEntity


class FeederBatterySensor(BinarySensorEntity):
    """Representation of a battery sensor for a feeder."""

    def __init__(self, coordinator, feeder) -> None:
        """Initialize the feeder battery sensor."""
        self.coordinator = coordinator
        self.feeder = feeder

    @property
    def name(self):
        """TODO."""
        return f"Feeder {self.feeder['name']} Battery"

    @property
    def is_on(self):
        """TODO."""
        return self.coordinator.data["battery_status"] == "ok"

    async def async_update(self):
        """Fetch new data from the API."""
        await self.coordinator.async_request_refresh()
