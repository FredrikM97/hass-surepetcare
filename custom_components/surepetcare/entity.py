from abc import abstractmethod

from surepetcare.client import SurePetcareClient
from surepetcare.devices.device import SurepyDevice

from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SurePetCareDeviceDataUpdateCoordinator


class SurePetCareBaseEntity(CoordinatorEntity[SurePetCareDeviceDataUpdateCoordinator]):
    """Base SurePetCare device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        device_coordinator: SurePetCareDeviceDataUpdateCoordinator,
        client: SurePetcareClient,
    ) -> None:
        """Initialize a device."""
        super().__init__(device_coordinator)

        self._device: SurepyDevice = device_coordinator.data
        self._client = client

        device_info = {
            "identifiers": {(DOMAIN, f"{self._device.id}")},
            "manufacturer": "SurePetCare",
            "model": self._device.product_name,
            "name": self._device.name,
        }
        if self._device.parent_device_id is not None:
            device_info["via_device"] = (DOMAIN, str(self._device.parent_device_id))
        self._attr_device_info = DeviceInfo(**device_info)
        self._attr_unique_id = f"{self._device.id}"

    @abstractmethod
    @callback
    def _refresh(self) -> None:
        """Refresh device data."""

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator.

        Tests fails without this method.
        """
        self._refresh()
        super()._handle_coordinator_update()

    # This causes issue for pet..
    # @property
    # def available(self) -> bool:
    #    """Return if entity is available."""
    #    return cast(bool, self._device.available) and super().available
