from homeassistant.helpers.entity import BinarySensorEntity


class FeederBatterySensor(BinarySensorEntity):
    """Representation of a battery sensor for a feeder."""

    def __init__(self, coordinator, feeder):
        self.coordinator = coordinator
        self.feeder = feeder

    @property
    def name(self):
        return f"Feeder {self.feeder['name']} Battery"

    @property
    def is_on(self):
        return self.coordinator.data["battery_status"] == "ok"

    async def async_update(self):
        """Fetch new data from the API."""
        await self.coordinator.async_request_refresh()
