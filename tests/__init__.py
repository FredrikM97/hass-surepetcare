from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from unittest.mock import patch
from surepcio import SurePetcareClient

DEVICE_MOCKS = ["feeder_connect", "dual_scan_connect", "hub"]
PET_MOCKS = [
    "pet",
]


async def initialize_entry(
    hass: HomeAssistant,
    mock_client: SurePetcareClient,
    mock_config_entry: MockConfigEntry,
) -> None:
    mock_config_entry.add_to_hass(hass)
    with patch(
        "custom_components.surepetcare.SurePetcareClient", return_value=mock_client
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
