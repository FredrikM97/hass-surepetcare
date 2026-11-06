from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
from surepcio import Household, SurePetcareClient, TimelineEvent
from surepcio.devices.device import DeviceBase, PetBase

from .support import MockConfigEntry, load_json_value_fixture

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
    *,
    history: list[TimelineEvent] | None = None,
) -> None:
    if not isinstance(mock_devices, list):
        mock_devices = [mock_devices]
    if not isinstance(mock_pets, list):
        mock_pets = [mock_pets]
    if history is None:
        pet_ids = {pet.id for pet in mock_pets}
        device_ids = {device.id for device in mock_devices}
        history = [
            event
            for event in (
                TimelineEvent(**item)
                for item in load_json_value_fixture("platform_history.json")
            )
            if any(pet.id in pet_ids for pet in event.pets)
            or any(device.id in device_ids for device in event.devices)
        ]
    mock_config_entry.add_to_hass(hass)

    def api_side_effect(cmd):
        """Return different data based on cmd.endpoint."""
        if hasattr(cmd, "endpoint") and "timeline" in cmd.endpoint:
            return history
        if hasattr(cmd, "endpoint") and "household" in cmd.endpoint:
            household = MagicMock()
            household.id = 12345
            household.data = {"id": 12345, "name": "Test Household"}
            household.get_devices.return_value = mock_devices
            household.get_pets.return_value = mock_pets
            household.get_timeline.side_effect = Household({"id": 12345}).get_timeline
            return [household]
        return cmd

    mock_client.api = AsyncMock(side_effect=api_side_effect)
    with patch(
        "custom_components.surepcha.SurePetcareClient", return_value=mock_client
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
