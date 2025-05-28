import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from surepetcare.client import SurePetcareClient

logger = logging.getLogger(__name__)


class SurePetcareCoordinator(DataUpdateCoordinator):
    """Coordinator for SurePetcare devices."""

    def __init__(self, hass: HomeAssistant, data) -> None:
        """TODO."""
        super().__init__(
            hass,
            logger=logger,
            name="SurePetcare Coordinator",
            update_interval=None,
        )
        self.token = data["token"]
        self.device_id = data["client_device_id"]
        self.client = SurePetcareClient()
        self.devices = {}

    async def _async_setup(self) -> None:
        await self.client.login(token=self.token, device_id=self.device_id)
        household_ids = [
            household["id"] for household in (await self.client.get_households())
        ]
        self.devices = await self.client.get_devices(household_ids)
        await self.client.close()

    async def _async_update_data(self):
        # Fetch and update device data here
        # for device in self.devices.values():
        #    await device.async_update()
        # Optionally, return a summary dict for all devices
        return {device.id: device for device in self.devices}
