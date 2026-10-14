from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
from surepcio import SurePetcareClient
from surepcio.devices.device import DeviceBase, PetBase
from surepcio.timeline import TimelineEvent

from custom_components.surepcha.const import HOUSEHOLD_ID

from .support import MockConfigEntry

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
    timeline_event_responses: tuple[list[TimelineEvent], ...] | None = None,
) -> None:
    if not isinstance(mock_devices, list):
        mock_devices = [mock_devices]
    if not isinstance(mock_pets, list):
        mock_pets = [mock_pets]
    mock_config_entry.add_to_hass(hass)

    timeline_command = MagicMock()
    timeline_responses = iter(timeline_event_responses or ())

    def api_side_effect(cmd):
        """Return different data based on cmd.endpoint."""
        if cmd is timeline_command:
            return next(timeline_responses, [])
        if hasattr(cmd, "endpoint") and "household" in cmd.endpoint:
            household = MagicMock()
            household_id = mock_config_entry.data[HOUSEHOLD_ID]
            household.id = household_id
            household.data = {"id": household_id, "name": "Test Household"}
            household.get_devices.return_value = mock_devices
            household.get_pets.return_value = mock_pets
            household.get_timeline.return_value = timeline_command
            return [household]
        return cmd

    mock_client.api = AsyncMock(side_effect=api_side_effect)
    with patch(
        "custom_components.surepcha.SurePetcareClient", return_value=mock_client
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
        if timeline_event_responses and len(timeline_event_responses) > 1:
            for coordinator in mock_config_entry.runtime_data.timeline_coordinators:
                await coordinator.async_request_refresh()
            await hass.async_block_till_done()
