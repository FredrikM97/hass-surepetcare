from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    load_json_value_fixture,
)
from surepcio import SurePetcareClient
from surepcio.devices.device import DeviceBase, PetBase
from surepcio.timeline import TimelineEvent

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

# feeding_timeline_frames.json events to serve each household, matching
# pet.json's household_id per pet (Maui -> 222527, Ajax -> 245684).
_TIMELINE_EVENT_NAMES_BY_HOUSEHOLD = {
    222527: ("feeding_wet_and_dry", "bowl_filled"),
    245684: ("feeding_wet_only",),
}


def _load_timeline_events_by_household() -> dict[int, list[TimelineEvent]]:
    """Build real TimelineEvent objects per household from feeding_timeline_frames.json."""
    raw = load_json_value_fixture("feeding_timeline_frames.json")
    return {
        household_id: [TimelineEvent(**raw[name]) for name in names]
        for household_id, names in _TIMELINE_EVENT_NAMES_BY_HOUSEHOLD.items()
    }


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

    timeline_events_by_household = _load_timeline_events_by_household()

    def api_side_effect(cmd):
        """Return different data based on cmd.endpoint."""
        endpoint = getattr(cmd, "endpoint", "")
        if not endpoint or "household" not in endpoint:
            return cmd

        if endpoint.rsplit("/", 1)[-1] == "household":
            # Household.get_households(): discovers households/devices/pets at setup.
            household = MagicMock()
            household.id = 12345
            household.data = {"id": 12345, "name": "Test Household"}
            household.get_devices.return_value = mock_devices
            household.get_pets.return_value = mock_pets
            return [household]

        if "/timeline/household/" in endpoint:
            # Only the first page (no before_id yet) returns events; later
            # pages must empty out so backward paging terminates.
            if getattr(cmd, "params", {}).get("before_id") is not None:
                return []
            household_id = int(endpoint.rsplit("/", 1)[-1])
            return timeline_events_by_household.get(household_id, [])

        # Household detail lookup. Names must differ per household, or their
        # entity_ids collide.
        household_id = int(endpoint.rsplit("/", 1)[-1])
        household_detail = MagicMock()
        household_detail.data = {"name": f"Test Household {household_id}"}
        return household_detail

    mock_client.api = AsyncMock(side_effect=api_side_effect)
    with patch(
        "custom_components.surepcha.SurePetcareClient", return_value=mock_client
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
