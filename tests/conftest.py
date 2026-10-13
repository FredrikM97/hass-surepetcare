import logging
from collections.abc import AsyncGenerator, Generator
from enum import Enum
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import surepcio.enums
from homeassistant import loader
from homeassistant.config_entries import ConfigEntries, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    area_registry as area_registry_module,
)
from homeassistant.helpers import (
    device_registry as device_registry_module,
)
from homeassistant.helpers import (
    entity,
    frame,
)
from homeassistant.helpers import (
    entity_registry as entity_registry_module,
)
from surepcio import SurePetcareClient
from surepcio.devices import load_device_class
from surepcio.devices.device import DeviceBase, PetBase
from surepcio.enums import ProductId
from surepcio.timeline import TimelineEvent
from syrupy.assertion import SnapshotAssertion

from custom_components.surepcha.const import (
    CLIENT_DEVICE_ID,
    DOMAIN,
    HOUSEHOLD_ID,
    LOCATION_INSIDE,
    LOCATION_OUTSIDE,
    MANUAL_PROPERTIES,
    NAME,
    OPTION_DEVICES,
    OPTION_PROPERTIES,
    PRODUCT_ID,
    TOKEN,
)

from . import DEVICE_MOCKS, PET_MOCKS
from .support import (
    HomeAssistantSnapshotExtension,
    MockConfigEntry,
    load_json_value_fixture,
)

# Auto-detect common enum fields by importing all enums from surepcio
_KNOWN_ENUMS = {
    name: obj
    for name, obj in vars(surepcio.enums).items()
    if isinstance(obj, type) and issubclass(obj, Enum) and obj is not Enum
}


@pytest.fixture
async def hass(tmp_path: Path) -> AsyncGenerator[HomeAssistant]:
    """Create a minimal Home Assistant instance for integration tests."""
    instance = HomeAssistant(str(tmp_path))
    instance.data[loader.DATA_CUSTOM_COMPONENTS] = {}
    instance.config_entries = ConfigEntries(instance, {"_": "test"})
    await instance.config_entries.async_initialize()
    entity.async_setup(instance)
    loader.async_setup(instance)
    device_registry_module.async_setup(instance)
    await device_registry_module.async_get(instance).async_load()
    await entity_registry_module.async_get(instance).async_load()
    await area_registry_module.async_get(instance).async_load()
    frame.async_setup(instance)
    await instance.async_start()
    logging.getLogger("custom_components.surepcha").setLevel(logging.INFO)
    logging.getLogger("surepcio").setLevel(logging.INFO)
    try:
        yield instance
    finally:
        for entry in instance.config_entries.async_entries():
            if entry.state is ConfigEntryState.LOADED:
                await instance.config_entries.async_unload(entry.entry_id)
        await instance.async_stop(force=True)
        await instance.async_block_till_done()


@pytest.fixture
def snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Return snapshot assertion fixture with the Home Assistant extension. Required by package"""
    return snapshot.use_extension(HomeAssistantSnapshotExtension)


@pytest.fixture
def enable_custom_integrations(hass: HomeAssistant) -> None:
    """Ensure the test Home Assistant instance allows local integrations."""
    hass.data.pop(loader.DATA_CUSTOM_COMPONENTS, None)


@pytest.fixture
def device_registry(
    hass: HomeAssistant,
) -> device_registry_module.DeviceRegistry:
    return device_registry_module.async_get(hass)


@pytest.fixture
def entity_registry(
    hass: HomeAssistant,
) -> entity_registry_module.EntityRegistry:
    return entity_registry_module.async_get(hass)


@pytest.fixture
def area_registry(hass: HomeAssistant) -> area_registry_module.AreaRegistry:
    return area_registry_module.async_get(hass)


@pytest.fixture
def mock_client():
    """Mock SurePetcareClient. Workaround is to use side_effect to return different data based on cmd.endpoint."""
    """Caused by the __init__ which calls multiple endpoints."""
    client = SurePetcareClient()
    client.login = AsyncMock(return_value=client)
    return client


@pytest.fixture(autouse=True)
def mock_coordinator_update_data():
    """Mock the coordinator update method to return the device data immediately."""
    """Prevents refresh to be called and empty entities being created."""

    async def return_device_data(self):
        # Return the current status/control or whatever your entities expect
        return self._device

    with patch(
        "custom_components.surepcha.coordinator.SurePetCareDeviceDataUpdateCoordinator._async_update_data",
        new=return_device_data,
    ):
        yield


def _create_entity(details):
    entity = load_device_class(details["entity_info"][PRODUCT_ID])(
        details["entity_info"], timezone="utc"
    )
    entity.status = entity.statusCls(**details["status"])
    entity.control = entity.controlCls(**details["control"])
    return entity


async def _create_device(mock_device_name: str) -> list[DeviceBase]:
    """Load a device or pet entity from a fixture file."""
    details = load_json_value_fixture(f"{mock_device_name}.json")
    details = convert_enum_names(details)

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
def timeline_scenarios() -> dict[str, list[TimelineEvent]]:
    """Load all representative timeline scenarios as backend event models."""
    return {
        scenario: [TimelineEvent.model_validate(event) for event in events]
        for scenario, events in load_json_value_fixture("timeline.json").items()
    }


@pytest.fixture
def timeline_events(
    timeline_scenarios: dict[str, list[TimelineEvent]],
) -> list[TimelineEvent]:
    """Return all representative timeline events."""
    return [event for events in timeline_scenarios.values() for event in events]


@pytest.fixture
def movement_timeline_events(
    timeline_scenarios: dict[str, list[TimelineEvent]],
) -> list[TimelineEvent]:
    """Return representative movement timeline events."""
    return timeline_scenarios["movement"]


@pytest.fixture
def feeding_timeline_events(
    timeline_scenarios: dict[str, list[TimelineEvent]],
) -> list[TimelineEvent]:
    """Return representative feeding timeline events."""
    return timeline_scenarios["feeding"]


@pytest.fixture
def feeding_timeline_event(
    feeding_timeline_events: list[TimelineEvent],
) -> TimelineEvent:
    """Return the representative feeding timeline event with pet data."""
    return feeding_timeline_events[0]


@pytest.fixture
def feeding_timeline_event_without_frames(
    feeding_timeline_events: list[TimelineEvent],
) -> TimelineEvent:
    """Return a representative feeding event without captured frames."""
    return next(
        event for event in feeding_timeline_events if not event.weights[0].frames
    )


@pytest.fixture
def movement_timeline_event(
    request: pytest.FixtureRequest,
    movement_timeline_events: list[TimelineEvent],
) -> TimelineEvent | None:
    """Return the parameterized representative movement timeline event."""
    return (
        movement_timeline_events[request.param] if request.param is not None else None
    )


@pytest.fixture
def pet_timeline_event_responses(
    request: pytest.FixtureRequest,
    timeline_events: list[TimelineEvent],
    movement_timeline_events: list[TimelineEvent],
    mock_pets: list[PetBase],
    mock_config_entry: MockConfigEntry,
) -> tuple[list[TimelineEvent], list[TimelineEvent]]:
    """Return full timeline responses with one aligned movement event arriving."""
    pet = mock_pets[0]
    pet.entity_info.household_id = mock_config_entry.data[HOUSEHOLD_ID]
    target_id = movement_timeline_events[getattr(request, "param", 1)].id
    events = [event.model_copy(deep=True) for event in timeline_events]
    target_event = next(event for event in events if event.id == target_id)
    target_event.pets = [
        participant.model_copy(update={"id": pet.id})
        for participant in target_event.pets
    ]
    target_event.movements = [
        movement.model_copy(
            update={
                "device_id": pet.status.activity.device_id,
                "tag_id": pet.entity_info.tag_id,
            }
        )
        for movement in target_event.movements
    ]
    return [event for event in events if event.id != target_id], events


@pytest.fixture
def pet_and_feeder_timeline_event_responses(
    timeline_events: list[TimelineEvent],
    movement_timeline_events: list[TimelineEvent],
    feeding_timeline_event: TimelineEvent,
    mock_devices: list[DeviceBase],
    mock_pets: list[PetBase],
    mock_config_entry: MockConfigEntry,
) -> tuple[list[TimelineEvent], list[TimelineEvent]]:
    """Return full responses with aligned pet movement and feeder frame events."""
    pet = mock_pets[0]
    feeder = next(
        device
        for device in mock_devices
        if device.product_id == ProductId.FEEDER_CONNECT
    )
    household_id = mock_config_entry.data[HOUSEHOLD_ID]
    pet.entity_info.household_id = household_id
    feeder.entity_info.household_id = household_id
    events = [event.model_copy(deep=True) for event in timeline_events]

    movement_event = next(
        event for event in events if event.id == movement_timeline_events[1].id
    )
    movement_event.pets = [
        participant.model_copy(update={"id": pet.id})
        for participant in movement_event.pets
    ]
    movement_event.movements = [
        movement.model_copy(
            update={
                "device_id": pet.status.activity.device_id,
                "tag_id": pet.entity_info.tag_id,
            }
        )
        for movement in movement_event.movements
    ]

    feeder_event = next(
        event for event in events if event.id == feeding_timeline_event.id
    )
    feeder_event.devices[0] = feeder_event.devices[0].model_copy(
        update={"id": feeder.id}
    )
    feeder_event.weights = [
        weight.model_copy(update={"device_id": feeder.id})
        for weight in feeder_event.weights
    ]

    target_ids = {movement_event.id, feeder_event.id}
    return [event for event in events if event.id not in target_ids], events


@pytest.fixture
def second_feeder_timeline_event(
    feeding_timeline_events: list[TimelineEvent],
) -> TimelineEvent:
    """Return the feeding event captured for the second feeder fixture."""
    return next(
        event
        for event in feeding_timeline_events
        if event.weights[0].device_id == 22222
    )


@pytest.fixture
def pet_and_two_feeder_timeline_event_responses(
    pet_and_feeder_timeline_event_responses: tuple[
        list[TimelineEvent], list[TimelineEvent]
    ],
    second_feeder_timeline_event: TimelineEvent,
    mock_devices: list[DeviceBase],
    mock_pets: list[PetBase],
    mock_config_entry: MockConfigEntry,
    timeline_events: list[TimelineEvent],
) -> tuple[list[TimelineEvent], list[TimelineEvent]]:
    """Deliver both feeders' representative events after the initial baseline."""
    baseline, events = pet_and_feeder_timeline_event_responses
    second_feeder = next(
        device
        for device in mock_devices
        if device.id == second_feeder_timeline_event.weights[0].device_id
    )
    second_feeder.entity_info.household_id = mock_config_entry.data[HOUSEHOLD_ID]
    last_activity_event = next(
        event for event in timeline_events if event.id == 18125028437
    )
    pet = next(pet for pet in mock_pets if pet.id == last_activity_event.pets[0].id)
    pet.entity_info.household_id = mock_config_entry.data[HOUSEHOLD_ID]
    return (
        [
            event
            for event in baseline
            if event.id not in {second_feeder_timeline_event.id, last_activity_event.id}
        ],
        events,
    )


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Mock a config entry."""
    return MockConfigEntry(
        title="Test SurePetCare entry",
        domain=DOMAIN,
        data={TOKEN: "abc", CLIENT_DEVICE_ID: "123", HOUSEHOLD_ID: 12345},
        options={
            OPTION_DEVICES: {
                "1299453": {
                    NAME: "DualScanConnect door",
                    PRODUCT_ID: ProductId.DUAL_SCAN_CONNECT,
                    LOCATION_INSIDE: "Home",
                    LOCATION_OUTSIDE: "Away",
                },
                "269654": {
                    NAME: "Feeder",
                    PRODUCT_ID: ProductId.FEEDER_CONNECT,
                },
                "727608": {
                    NAME: "PetDoor",
                    PRODUCT_ID: ProductId.PET_DOOR,
                },
            },
            OPTION_PROPERTIES: {
                MANUAL_PROPERTIES: {
                    LOCATION_INSIDE: "Home",
                    LOCATION_OUTSIDE: "Away",
                }
            },
        },
        unique_id="12345",
    )


@pytest.fixture
def mock_config_entry_missing_entities() -> MockConfigEntry:
    """Mock a config entry with missing entities."""
    return MockConfigEntry(
        title="Test SurePetCare entry",
        domain=DOMAIN,
        data={TOKEN: "abc", CLIENT_DEVICE_ID: "123", HOUSEHOLD_ID: 12345},
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
        patch("custom_components.surepcha.SurePetcareClient", return_value=mock_client),
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    return mock_config_entry


@pytest.fixture
def mock_setup_entry(monkeypatch):
    """Mock setting up a config entry."""
    monkeypatch.setattr(
        "custom_components.surepcha.async_setup_entry", lambda *a, **kw: True
    )
    yield


@pytest.fixture
def entity_registry_enabled_default() -> Generator[AsyncMock]:
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
) -> AsyncGenerator[MagicMock]:
    """Return a mocked SurePetcareClient for config_flow login."""
    with (
        patch(
            "custom_components.surepcha.config_flow.SurePetcareClient", autospec=True
        ) as client_mock,
        patch(
            "custom_components.surepcha.SurePetcareClient", autospec=True
        ) as setup_mock,
    ):
        instance = client_mock.return_value
        setup_mock.return_value = instance
        instance.login = AsyncMock(return_value=True)
        # Mock token and device_id attributes
        instance.token = "mocked_token"
        instance.device_id = "mocked_device_id"
        instance.api = AsyncMock(return_value=[])

        def api_side_effect(cmd):
            """Return different data based on cmd.endpoint."""
            if hasattr(cmd, "endpoint") and "household" in cmd.endpoint:
                household = MagicMock()
                household.id = 12345
                household.data = {"id": 12345, "name": "Test Household"}
                household.get_devices.return_value = mock_devices
                household.get_pets.return_value = mock_pets
                return [household]
            return cmd

        instance.api = AsyncMock(side_effect=api_side_effect)
        yield client_mock


def convert_enum_names(data):
    """Convert enum names in test fixture data to their actual values.

    Automatically detects enum values by trying all known enums from surepcio.enums.
    If a string value matches an enum member name, it's converted to the enum's value.

    Example:
        convert_enum_names({"product_id": "DUAL_SCAN_CONNECT"})
        # Returns: {"product_id": 6}
    """
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                # Try to find matching enum
                converted = False
                for enum_class in _KNOWN_ENUMS.values():
                    try:
                        result[key] = getattr(enum_class, value).value
                        converted = True
                        break
                    except AttributeError, KeyError:
                        continue
                if not converted:
                    result[key] = convert_enum_names(value)
            else:
                result[key] = convert_enum_names(value)
        return result
    elif isinstance(data, list):
        return [convert_enum_names(item) for item in data]
    else:
        return data
