import copy
from datetime import timedelta
import logging
from types import MappingProxyType
from typing import Any

from surepetcare.client import SurePetcareClient
from surepetcare.devices.device import SurepyDevice

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

logger = logging.getLogger(__name__)

SCAN_INTERVAL = 300


class SurePetCareDeviceDataUpdateCoordinator(DataUpdateCoordinator[Any]):
    """Coordinator to manage data for a specific SurePetCare device."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: SurePetcareClient,
        device: SurepyDevice,
    ) -> None:
        """Initialize device coordinator."""
        super().__init__(
            hass,
            logger,
            config_entry=config_entry,
            name=f"Update coordinator for {device}",
            update_interval=timedelta(seconds=SCAN_INTERVAL),
        )
        self.product_id = device.product_id
        self.client = client
        self._device = device
        self._photo: str | None = None
        self._exception: Exception | None = None

    async def _async_setup(self):
        """Set up the coordinator."""
        self._photo = self._device._data.get("photo", {}).get("location")

    async def _async_update_data(self) -> Any:
        """Fetch data from the api for a specific device."""
        return await self.client.api(self._device.refresh())
