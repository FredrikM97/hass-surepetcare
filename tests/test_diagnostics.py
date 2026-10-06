import json
from types import SimpleNamespace

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.json import json_bytes
from surepcio import SurePetcareClient
from surepcio.devices.device import DeviceBase, PetBase
from syrupy.assertion import SnapshotAssertion
from syrupy.filters import props

from custom_components.surepcha.const import (
    DOMAIN,
    MANUAL_PROPERTIES,
    OPTION_DEVICES,
    OPTION_PROPERTIES,
)
from custom_components.surepcha.diagnostics import (
    async_get_config_entry_diagnostics,
    async_get_device_diagnostics,
)

from . import initialize_entry
from .support import MockConfigEntry


@pytest.mark.parametrize("mock_device_name", ["feeder_connect"])
@pytest.mark.usefixtures("enable_custom_integrations")
async def test_entry_diagnostics(
    hass: HomeAssistant,
    mock_client: SurePetcareClient,
    mock_config_entry: MockConfigEntry,
    mock_device: list[DeviceBase],
    mock_pet: list[PetBase],
    snapshot: SnapshotAssertion,
) -> None:
    """Test config entry diagnostics."""
    await initialize_entry(hass, mock_client, mock_config_entry, mock_device, mock_pet)

    result = json_bytes(
        await async_get_config_entry_diagnostics(hass, mock_config_entry)
    )
    result = json.loads(result)

    # Verify sensitive data is redacted
    assert result["entry_data"]["token"] == "**REDACTED**"
    assert result["entry_data"]["client_device_id"] == "**REDACTED**"

    # Legacy manual properties should not be treated as a pseudo-device anymore.
    assert MANUAL_PROPERTIES not in result["options"][OPTION_DEVICES]
    assert OPTION_PROPERTIES in result["options"]
    assert isinstance(result["options"][OPTION_PROPERTIES], dict)

    assert result == snapshot(
        exclude=props("last_changed", "last_reported", "last_updated")
    )


@pytest.mark.parametrize("mock_device_name", ["feeder_connect"])
@pytest.mark.usefixtures("enable_custom_integrations")
async def test_device_diagnostics(
    hass: HomeAssistant,
    mock_client: SurePetcareClient,
    mock_config_entry: MockConfigEntry,
    mock_device: list[DeviceBase],
    mock_pet: list[PetBase],
    device_registry: dr.DeviceRegistry,
    snapshot: SnapshotAssertion,
) -> None:
    """Test device diagnostics."""
    await initialize_entry(hass, mock_client, mock_config_entry, mock_device, mock_pet)

    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, f"{mock_device[0].id}"), mock_config_entry.entry_id
    )
    assert device, repr(device_registry.devices)

    result = json.loads(
        json_bytes(await async_get_device_diagnostics(hass, mock_config_entry, device))
    )

    # Device diagnostics includes entry options, so validate the same contract here.
    assert MANUAL_PROPERTIES not in result["options"][OPTION_DEVICES]
    assert OPTION_PROPERTIES in result["options"]
    assert isinstance(result["options"][OPTION_PROPERTIES], dict)

    assert result == snapshot(
        exclude=props("last_changed", "last_reported", "last_updated")
    )


async def test_device_diagnostics_without_matching_coordinator(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Return no diagnostics when this entry has no coordinator for the device."""
    mock_config_entry.runtime_data = SimpleNamespace(
        device_coordinators=[
            SimpleNamespace(_device=SimpleNamespace(id="other"), data=object())
        ]
    )
    device = SimpleNamespace(identifiers={(DOMAIN, "missing")})

    result = await async_get_device_diagnostics(hass, mock_config_entry, device)

    assert result == {}
