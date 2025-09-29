import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from homeassistant.helpers import device_registry as dr
from syrupy.filters import props
from surepcio.devices.device import DeviceBase, PetBase
from . import initialize_entry
from surepcio import SurePetcareClient
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_device,
    get_diagnostics_for_config_entry,
)
from custom_components.surepetcare.const import DOMAIN
from syrupy.assertion import SnapshotAssertion
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator


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
        identifiers={(DOMAIN, str(mock_device[0].id))}
    )
    assert device, repr(device_registry.devices)

    result = await get_diagnostics_for_device(
        hass, hass_client, mock_config_entry, device
    )
    assert result == snapshot(
        exclude=props("last_changed", "last_reported", "last_updated")
    )
