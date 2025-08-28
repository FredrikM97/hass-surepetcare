import pytest
from unittest.mock import MagicMock
from pytest_homeassistant_custom_component.common import MockConfigEntry
from homeassistant.helpers import device_registry as dr
from custom_components.surepetcare.diagnostics import (
    async_get_config_entry_diagnostics,
    async_get_device_diagnostics,
)
from custom_components.surepetcare.const import DOMAIN


@pytest.mark.asyncio
async def test_async_get_config_entry_diagnostics():
    hass = MagicMock()
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"token": "test_token", "client_device_id": "device123"},
        options={"device1": {"location_inside": "kitchen"}},
    )

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["entry_data"]["token"] == "test_token"
    assert result["entry_data"]["client_device_id"] == "device123"
    assert result["options"]["device1"]["location_inside"] == "kitchen"


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
