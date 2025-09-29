from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from custom_components.surepetcare.const import (
    DOMAIN,
    LOCATION_INSIDE,
    LOCATION_OUTSIDE,
    OPTION_DEVICES,
)
from . import DEVICE_MOCKS, PET_MOCKS
from surepcio import SurePetcareClient
from surepcio.enums import ProductId
from surepcio.devices.device import DeviceBase, PetBase
from homeassistant.core import HomeAssistant
from surepcio.devices import load_device_class
from pytest_homeassistant_custom_component.syrupy import HomeAssistantSnapshotExtension
from pytest_homeassistant_custom_component.common import (
    load_json_value_fixture,
    MockConfigEntry,
)
from syrupy.assertion import SnapshotAssertion


@pytest.fixture
def snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Return snapshot assertion fixture with the Home Assistant extension. Required by package"""
    return snapshot.use_extension(HomeAssistantSnapshotExtension)


@pytest.fixture
def mock_client():
    """Mock SurePetcareClient. Workaround is to use side_effect to return different data based on cmd.endpoint."""
    """Caused by the __init__ which calls multiple endpoints."""
    client = SurePetcareClient()
    client.login = AsyncMock(return_value=None)
    return client


@pytest.fixture(autouse=True)
def mock_coordinator_update_data():
    """Mock the coordinator update method to return the device data immediately."""
    """Prevents refresh to be called and empty entities being created."""

    async def return_device_data(self):
        # Return the current status/control or whatever your entities expect
        return self._device

    with patch(
        "custom_components.surepetcare.coordinator.SurePetCareDeviceDataUpdateCoordinator._async_update_data",
        new=return_device_data,
    ):
        yield

def _create_entity(details):
    entity = load_device_class(details["entity_info"]["product_id"])(
        details["entity_info"], timezone="utc"
    )
    entity.status = entity.statusCls(**details["status"])
    entity.control = entity.controlCls(**details["control"])
    return entity

async def _create_device(mock_device_name: str) -> list[DeviceBase]:
    """Load a device or pet entity from a fixture file."""
    details = load_json_value_fixture(f"{mock_device_name}.json")
    

    if isinstance(details, list):
        return [_create_entity(item) for item in details]
    else:
        return [_create_entity(details)]

@pytest.fixture
async def mock_device(mock_device_name: str) -> list[DeviceBase]:
    """Return mock device object(s) as a list."""
    return await _create_device(mock_device_name)

@pytest.fixture
async def mock_pet(mock_device_name: str) -> list[DeviceBase]:
    """Return mock pet object(s) as a list."""
    return await _create_device(mock_device_name)

@pytest.fixture
async def mock_devices() -> list[DeviceBase]:
    """Return flat list of mock device objects."""
    devices = []
    for device in DEVICE_MOCKS:
        devices.extend(await _create_device(device))
    return devices



@pytest.fixture
async def mock_pets() -> list[PetBase]:
    """Return flat list of mock pet objects."""
    pets = []
    for pet in PET_MOCKS:
        pets.extend(await _create_device(pet))
    return pets


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Mock a config entry."""
    return MockConfigEntry(
        title="Test SurePetCare entry",
        domain=DOMAIN,
        data={"token": "abc", "client_device_id": "123"},
        options={
            OPTION_DEVICES: {
                "1299453": {
                    "name": "DualScanConnect door",
                    "product_id": ProductId.DUAL_SCAN_CONNECT,
                    LOCATION_INSIDE: "Home",
                    LOCATION_OUTSIDE: "Away",
                },
                "269654": {
                    "name": "Feeder",
                    "product_id": ProductId.FEEDER_CONNECT,
                },
                "727608": {
                    "name": "PetDoor",
                    "product_id": ProductId.PET_DOOR,
                },
            }
        },
        unique_id="12345",
    )


@pytest.fixture
def mock_config_entry_missing_entities() -> MockConfigEntry:
    """Mock a config entry with missing entities."""
    return MockConfigEntry(
        title="Test SurePetCare entry",
        domain=DOMAIN,
        data={"token": "abc", "client_device_id": "123"},
        options={OPTION_DEVICES: {}},
        unique_id="12345",
    )


@pytest.fixture
async def mock_loaded_entry(
    hass: HomeAssistant, mock_client, mock_config_entry: MockConfigEntry
) -> MockConfigEntry:
    """Mock a config entry that has been added and set up in Home Assistant."""

    mock_config_entry.add_to_hass(hass)

    # Initialize the component
    with (
        patch(
            "custom_components.surepetcare.SurePetcareClient", return_value=mock_client
        ),
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    return mock_config_entry


@pytest.fixture
def mock_setup_entry(monkeypatch):
    """Mock setting up a config entry."""
    monkeypatch.setattr(
        "custom_components.surepetcare.async_setup_entry", lambda *a, **kw: True
    )
    yield


@pytest.fixture
def entity_registry_enabled_default() -> Generator[AsyncMock, None, None]:
    """Test fixture that ensures all entities are enabled in the registry."""
    """Can't find this fixture so created it for now"""
    with patch(
        "homeassistant.helpers.entity.Entity.entity_registry_enabled_default",
        return_value=True,
    ) as mock_entity_registry_enabled_by_default:
        yield mock_entity_registry_enabled_by_default


@pytest.fixture
def mock_device_name() -> str:
    """Fixture to parametrize the type of the mock device.

    To set a configuration, tests can be marked with:
    @pytest.mark.parametrize("mock_device_name", ["device_name_1", "device_name_2"])
    """
    return None


@pytest.fixture
async def mock_surepetcare_login_control(
    mock_pets,
    mock_devices,
) -> Generator[MagicMock, None, None]:
    """Return a mocked SurePetcareClient for config_flow login."""
    with patch(
        "custom_components.surepetcare.config_flow.SurePetcareClient", autospec=True
    ) as client_mock:
        instance = client_mock.return_value
        instance.login = AsyncMock(return_value=True)
        # Mock token and device_id attributes
        instance.token = "mocked_token"
        instance.device_id = "mocked_device_id"
        instance.api = AsyncMock(return_value=[])

        def api_side_effect(cmd):
            """Return different data based on cmd.endpoint."""
            if hasattr(cmd, "endpoint") and "household" in cmd.endpoint:
                household = MagicMock()
                household.get_devices.return_value = mock_devices
                household.get_pets.return_value = mock_pets
                return [household]
            return cmd

        instance.api = AsyncMock(side_effect=api_side_effect)
        yield client_mock
