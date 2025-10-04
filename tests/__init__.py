from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from unittest.mock import AsyncMock, MagicMock, patch
from surepcio import SurePetcareClient
from surepcio.devices.device import DeviceBase, PetBase

DEVICE_MOCKS = [
    "feeder_connect",
    "dual_scan_connect",
    "hub",
    "pet_door",
    "poseidon_connect",
]
PET_MOCKS = [
    "pet",
]


async def initialize_entry(
    hass: HomeAssistant,
    mock_client: SurePetcareClient,
    mock_config_entry: MockConfigEntry,
    mock_devices: DeviceBase,
    mock_pets: PetBase,
) -> None:
    if not isinstance(mock_devices, list):
        mock_devices = [mock_devices]
    if not isinstance(mock_pets, list):
        mock_pets = [mock_pets]
    mock_config_entry.add_to_hass(hass)

    def api_side_effect(cmd):
        """Return different data based on cmd.endpoint."""
        if hasattr(cmd, "endpoint") and "household" in cmd.endpoint:
            household = MagicMock()
            household.get_devices.return_value = mock_devices
            household.get_pets.return_value = mock_pets
            return [household]
        return cmd

    mock_client.api = AsyncMock(side_effect=api_side_effect)
    with patch(
        "custom_components.surepetcare.SurePetcareClient", return_value=mock_client
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
