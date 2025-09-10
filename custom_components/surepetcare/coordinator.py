from datetime import timedelta
import logging
from typing import Any

from surepcio.client import SurePetcareClient
from surepcio.devices.device import SurePetCareBase

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
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
        device: SurePetCareBase,
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
        self._exception: Exception | None = None

    async def _async_update_data(self) -> Any:
        """Fetch data from the api for a specific device."""
        return await self.client.api(self._device.refresh())
