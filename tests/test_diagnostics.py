import pytest
from unittest.mock import MagicMock
from pytest_homeassistant_custom_component.common import MockConfigEntry
from homeassistant.helpers import device_registry as dr
from custom_components.surepetcare.diagnostics import (
    async_get_config_entry_diagnostics,
    async_get_device_diagnostics,
)
from syrupy.filters import props
from surepcio.devices.device import DeviceBase, PetBase
from . import initialize_entry
from surepcio import SurePetcareClient
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_device,
    get_diagnostics_for_config_entry,
)
from custom_components.surepetcare.const import DOMAIN, LOCATION_INSIDE
from syrupy.assertion import SnapshotAssertion
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator


@pytest.mark.asyncio
async def test_async_get_config_entry_diagnostics():
    hass = MagicMock()
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"token": "test_token", "client_device_id": "device123"},
        options={"device1": {LOCATION_INSIDE: "kitchen"}},
    )

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["entry_data"]["token"] == "test_token"
    assert result["entry_data"]["client_device_id"] == "device123"
    assert result["options"]["device1"][LOCATION_INSIDE] == "kitchen"


@pytest.mark.asyncio
async def test_async_get_device_diagnostics(hass):
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)

    device = MagicMock(spec=dr.DeviceEntry)
    device.identifiers = {(DOMAIN, "device123")}

    mock_data = MagicMock()
    mock_data.entity_info.dict.return_value = {"id": "device123", "name": "Test Device"}
    mock_data.status.dict.return_value = {"battery": 85, "online": True}
    mock_data.control.dict.return_value = {"locked": False}

    mock_coordinator = MagicMock()
    mock_coordinator.data = mock_data

    hass.data = {
        DOMAIN: {
            entry.entry_id: {
                "coordinator": {"coordinator_dict": {"device123": mock_coordinator}}
            }
        }
    }

    result = await async_get_device_diagnostics(hass, entry, device)

    assert result["entity_info"]["id"] == "device123"
    assert result["status"]["battery"] == 85
    assert result["control"]["locked"] is False


@pytest.mark.asyncio
async def test_async_get_device_diagnostics_no_data():
    hass = MagicMock()
    hass.data = {}
    entry = MockConfigEntry(domain=DOMAIN)
    device = MagicMock(spec=dr.DeviceEntry)
    device.identifiers = {(DOMAIN, "device123")}

    result = await async_get_device_diagnostics(hass, entry, device)

    assert result == {}


@pytest.mark.parametrize("mock_device_name", ["feeder_connect"])
@pytest.mark.usefixtures("enable_custom_integrations")
async def test_entry_diagnostics(
    hass: HomeAssistant,
    mock_client: SurePetcareClient,
    mock_config_entry: MockConfigEntry,
    mock_device: DeviceBase,
    mock_pet: PetBase,
    hass_client: ClientSessionGenerator,
    snapshot: SnapshotAssertion,
) -> None:
    """Test config entry diagnostics."""
    await initialize_entry(hass, mock_client, mock_config_entry, mock_device, mock_pet)

    result = await get_diagnostics_for_config_entry(
        hass, hass_client, mock_config_entry
    )

    assert result == snapshot(
        exclude=props("last_changed", "last_reported", "last_updated")
    )


@pytest.mark.parametrize("mock_device_name", ["feeder_connect"])
@pytest.mark.usefixtures("enable_custom_integrations")
async def test_device_diagnostics(
    hass: HomeAssistant,
    mock_client: SurePetcareClient,
    mock_config_entry: MockConfigEntry,
    mock_device: DeviceBase,
    mock_pet: PetBase,
    hass_client: ClientSessionGenerator,
    device_registry: dr.DeviceRegistry,
    snapshot: SnapshotAssertion,
) -> None:
    """Test device diagnostics."""
    await initialize_entry(hass, mock_client, mock_config_entry, mock_device, mock_pet)

    device = device_registry.async_get_device(
        identifiers={(DOMAIN, str(mock_device.id))}
    )
    assert device, repr(device_registry.devices)

    result = await get_diagnostics_for_device(
        hass, hass_client, mock_config_entry, device
    )
    assert result == snapshot(
        exclude=props("last_changed", "last_reported", "last_updated")
    )
