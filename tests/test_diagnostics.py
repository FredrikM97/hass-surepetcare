import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
    get_diagnostics_for_device,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator
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

from . import initialize_entry


@pytest.mark.parametrize("mock_device_name", ["feeder_connect"])
@pytest.mark.usefixtures("enable_custom_integrations")
async def test_entry_diagnostics(
    hass: HomeAssistant,
    mock_client: SurePetcareClient,
    mock_config_entry: MockConfigEntry,
    mock_device: list[DeviceBase],
    mock_pet: list[PetBase],
    hass_client: ClientSessionGenerator,
    snapshot: SnapshotAssertion,
) -> None:
    """Test config entry diagnostics."""
    await initialize_entry(hass, mock_client, mock_config_entry, mock_device, mock_pet)

    result = await get_diagnostics_for_config_entry(
        hass, hass_client, mock_config_entry
    )

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
    hass_client: ClientSessionGenerator,
    device_registry: dr.DeviceRegistry,
    snapshot: SnapshotAssertion,
) -> None:
    """Test device diagnostics."""
    await initialize_entry(hass, mock_client, mock_config_entry, mock_device, mock_pet)

    device = device_registry.async_get_device(
        identifiers={(DOMAIN, f"{mock_device[0].id}")}
    )
    assert device, repr(device_registry.devices)

    result = await get_diagnostics_for_device(
        hass, hass_client, mock_config_entry, device
    )

    # Device diagnostics includes entry options, so validate the same contract here.
    assert MANUAL_PROPERTIES not in result["options"][OPTION_DEVICES]
    assert OPTION_PROPERTIES in result["options"]
    assert isinstance(result["options"][OPTION_PROPERTIES], dict)

    assert result == snapshot(
        exclude=props("last_changed", "last_reported", "last_updated")
    )
