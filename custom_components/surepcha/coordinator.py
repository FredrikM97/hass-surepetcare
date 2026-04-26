from datetime import timedelta
import logging
from typing import Any, TypeAlias, TypeVar

from surepcio import SurePetcareClient
from surepcio.devices.device import SurePetCareBase


from .const import OPTION_DEVICES, POLLING_SPEED, SCAN_INTERVAL
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

logger = logging.getLogger(__name__)


SurePetcareConfigEntry: TypeAlias = ConfigEntry[
    list["SurePetCareDeviceDataUpdateCoordinator"]
]
T = TypeVar("T", bound=SurePetCareBase)


class SurePetCareDeviceDataUpdateCoordinator(DataUpdateCoordinator[T]):
    """Coordinator to manage data for a specific SurePetCare device."""

    config_entry: SurePetcareConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: SurePetcareConfigEntry,
        client: SurePetcareClient,
        device: SurePetCareBase,
    ) -> None:
        """Initialize device coordinator."""
        super().__init__(
            hass,
            logger,
            config_entry=entry,
            name=f"{device.name}",
            update_interval=timedelta(
                seconds=entry.options.get(OPTION_DEVICES, {})
                .get(str(device.id), {})
                .get(POLLING_SPEED, SCAN_INTERVAL)
            ),
        )
        self._device = device
        self.product_id = self._device.product_id
        self.client = client
        self._exception: Exception | None = None

    async def _async_setup(self):
        """Fetch initial data for the device."""
        await self.client.api(self._device.refresh())

    async def _async_update_data(self) -> Any:
        """Fetch data from the api for a specific device."""
        logger.debug(
            "Fetching data for device %s (id=%s)", self._device.name, self._device.id
        )
        await self.client.api(self._device.refresh())
        return self._device
