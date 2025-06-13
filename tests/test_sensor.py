import importlib
import pytest
from unittest.mock import MagicMock, patch
from custom_components.surepetcare import sensor
from custom_components.surepetcare.sensor import (
    SurePetCareSensor,
    SurePetCareSensorEntityDescription,
    get_location,
    get_feeding_events,
    ProductId,
)
from tests.conftest import (
    DummyDevice,
    DummyCoordinator,
    DummyClient,
    DummyDeviceWithFeeding,
    DummyDeviceWithNoneRefresh,
)


def test_get_location():
    reconfig = {"1": {"location_inside": "Home", "location_outside": "Yard"}}
    assert get_location(DummyDevice(), reconfig) in ("Home", "Yard", None)


def test_get_feeding_events():
    # Case: no feeding_event attribute
    result = get_feeding_events(DummyDevice())
    assert result is None or isinstance(result, dict)

    # Case: feeding_event present with weights
    result = get_feeding_events(DummyDeviceWithFeeding())
    assert result["native"] == abs(-5) + abs(3)
    assert result["data"]["device_id"] == "dev123"
    assert result["data"]["duration"] == 10
    assert result["data"]["timestamp"] == "2024-01-01T00:00:00Z"
    assert result["data"]["bowl_1"]["change"] == -5
    assert result["data"]["bowl_1"]["weight"] == 10
    assert result["data"]["bowl_2"]["change"] == 3
    assert result["data"]["bowl_2"]["weight"] == 7


def test_surepetcare_sensor_refresh_and_native_value():
    desc = sensor.SurePetCareSensorEntityDescription(
        key="test",
        value=lambda device, r: 42,
    )
    sensor_entity = SurePetCareSensor(
        DummyCoordinator(), DummyClient(), desc, subentry_data={}
    )
    assert sensor_entity.native_value == 42
    # Test frozen sensor does not update
    desc_frozen = SurePetCareSensorEntityDescription(
        key="test_frozen",
        value=lambda device, r: 99,
        frozen=True,
    )
    sensor_entity_frozen = SurePetCareSensor(
        DummyCoordinator(), DummyClient(), desc_frozen, subentry_data={}
    )
    sensor_entity_frozen._attr_native_value = 1

    _ = sensor_entity_frozen.native_value
    assert sensor_entity_frozen._attr_native_value == 1


def test_surepetcare_sensor_refresh_dict_value():
    desc = SurePetCareSensorEntityDescription(
        key="test_dict",
        value=lambda device, r: {"native": 123, "data": {"foo": "bar"}},
    )
    sensor_entity = SurePetCareSensor(
        DummyCoordinator(), DummyClient(), desc, subentry_data={}
    )
    assert sensor_entity.native_value == 123
    assert sensor_entity.extra_state_attributes == {"foo": "bar"}


def test_get_location_none():
    # No movement
    device = DummyDevice()
    device.movement = None
    assert get_location(device, {}) is None
    # No reconfig for device_id
    device.movement = [type("M", (), {"active": True, "device_id": "1"})()]
    assert get_location(device, {"1": {}}) is True
    device.movement = [type("M", (), {"active": False, "device_id": "1"})()]
    assert get_location(device, {"1": {}}) is False


def test_sensor_entity_refresh_and_frozen():
    desc = sensor.SurePetCareSensorEntityDescription(
        key="battery_level",
        value=lambda device, r: 42,
        frozen=True,
    )
    c = DummyCoordinator()
    s = SurePetCareSensor(c, DummyClient(), desc, subentry_data={})
    s._attr_native_value = 99
    _ = s.native_value
    assert s._attr_native_value == 99
    # Not frozen, should update
    desc2 = sensor.SurePetCareSensorEntityDescription(
        key="battery_level",
        value=lambda device, r: 55,
        frozen=False,
    )
    s2 = SurePetCareSensor(c, DummyClient(), desc2, subentry_data={})
    assert s2.native_value == 55


def test_sensor_entity_refresh_none_value():
    desc = sensor.SurePetCareSensorEntityDescription(
        key="info",
        value=lambda device, r: None,
    )
    c = DummyCoordinator()
    s = SurePetCareSensor(c, DummyClient(), desc, subentry_data={})
    assert s.native_value is None


def test_sensor_import():
    importlib.import_module("custom_components.surepetcare.sensor")


@pytest.mark.asyncio
async def test_async_setup_entry():
    # Patch all dependencies and test async_setup_entry logic
    hass = MagicMock()
    config_entry = MagicMock()
    async_add_entities = MagicMock()
    # Setup fake coordinator data
    device = DummyDevice()
    device.product_id = ProductId.FEEDER_CONNECT
    coordinator = DummyCoordinator(device)
    from tests.conftest import make_coordinator_data

    hass.data = {
        "surepetcare": {
            config_entry.entry_id: {"coordinator": make_coordinator_data(coordinator)}
        }
    }
    config_entry.subentries = {"1": MagicMock(data={"id": "1"})}
    # Patch SENSORS to ensure at least one description is present
    with patch(
        "custom_components.surepetcare.sensor.SENSORS",
        {
            ProductId.FEEDER_CONNECT: (
                sensor.SurePetCareSensorEntityDescription(
                    key="test", value=lambda d, r: 1
                ),
            )
        },
    ):
        await sensor.async_setup_entry(hass, config_entry, async_add_entities)
    async_add_entities.assert_called()


@pytest.mark.asyncio
async def test_async_setup_entry_all_paths():
    hass = MagicMock()
    config_entry = MagicMock()
    from tests.conftest import make_coordinator_data

    device = DummyDevice()
    device.product_id = ProductId.FEEDER_CONNECT
    coordinator = DummyCoordinator(device)
    hass.data = {
        "surepetcare": {
            config_entry.entry_id: {"coordinator": make_coordinator_data(coordinator)}
        }
    }
    # --- Case 1: Normal path ---
    async_add_entities = MagicMock()
    config_entry.subentries = {"1": MagicMock(data={"id": "1"})}
    with patch(
        "custom_components.surepetcare.sensor.SENSORS",
        {
            ProductId.FEEDER_CONNECT: (
                sensor.SurePetCareSensorEntityDescription(
                    key="test", value=lambda d, r: 1
                ),
            )
        },
    ):
        await sensor.async_setup_entry(hass, config_entry, async_add_entities)
    async_add_entities.assert_called()
    # Check that config_subentry_id is passed
    assert any(
        "config_subentry_id" in kwargs
        for args, kwargs in async_add_entities.call_args_list
    )
    # Check that at least one entity is a SurePetCareSensor
    entities = async_add_entities.call_args[0][0]
    assert any(isinstance(e, SurePetCareSensor) for e in entities)
    # --- Case 2: subentry with no device_id (should skip) ---
    async_add_entities.reset_mock()
    config_entry.subentries = {"1": MagicMock(data={})}
    with patch(
        "custom_components.surepetcare.sensor.SENSORS",
        {
            ProductId.FEEDER_CONNECT: (
                sensor.SurePetCareSensorEntityDescription(
                    key="test", value=lambda d, r: 1
                ),
            )
        },
    ):
        await sensor.async_setup_entry(hass, config_entry, async_add_entities)
    async_add_entities.assert_not_called()
    # --- Case 3: SENSORS missing for product (should skip) ---
    async_add_entities.reset_mock()
    config_entry.subentries = {"1": MagicMock(data={"id": "1"})}
    with patch("custom_components.surepetcare.sensor.SENSORS", {}):
        await sensor.async_setup_entry(hass, config_entry, async_add_entities)
    async_add_entities.assert_not_called()


def test_get_location_with_reconfig_inside_outside():
    device = DummyDevice()
    device.movement = [type("M", (), {"active": True, "device_id": "1"})()]
    reconfig = {"1": {"location_inside": "Home", "location_outside": "Yard"}}
    assert get_location(device, reconfig) == "Home"
    device.movement = [type("M", (), {"active": False, "device_id": "1"})()]
    assert get_location(device, reconfig) == "Yard"


def test_get_location_with_missing_reconfig_keys():
    device = DummyDevice()
    device.movement = [type("M", (), {"active": True, "device_id": "1"})()]
    reconfig = {"1": {}}
    assert get_location(device, reconfig) is True
    device.movement = [type("M", (), {"active": False, "device_id": "1"})()]
    assert get_location(device, reconfig) is False


def test_pet_door_location_multiple_devices():
    # Simulate a pet (cat) moving through two pet doors
    # Device 1: bedroom -> kitchen (inside)
    # Device 2: kitchen -> garden (outside)
    from custom_components.surepetcare.sensor import get_location

    class PetDevice:
        id = "cat1"
        name = "Whiskers"
        product_id = "PET"
        movement = [
            type("M", (), {"active": True, "device_id": "door1"})(),
            type("M", (), {"active": True, "device_id": "door2"})(),
        ]

    # Reconfig for both doors
    reconfig = {
        "door1": {"location_inside": "Bedroom", "location_outside": "Kitchen"},
        "door2": {"location_inside": "Kitchen", "location_outside": "Garden"},
    }
    pet = PetDevice()
    # First, test with door1 active (should be 'Bedroom' per current logic)
    pet.movement = [type("M", (), {"active": True, "device_id": "door1"})()]
    assert get_location(pet, reconfig) == "Bedroom"
    # Now, test with door2 active (should be 'Kitchen' per current logic)
    pet.movement = [type("M", (), {"active": True, "device_id": "door2"})()]
    assert get_location(pet, reconfig) == "Kitchen"
    # If both are active, should return the first active found (door1)
    pet.movement = [
        type("M", (), {"active": True, "device_id": "door1"})(),
        type("M", (), {"active": True, "device_id": "door2"})(),
    ]
    assert get_location(pet, reconfig) == "Bedroom"


def test_get_location_with_none_refresh():
    device = DummyDeviceWithNoneRefresh()
    # Should not raise, should return None or fallback
    assert get_location(device, {}) is None


def test_get_location_with_missing_inside_outside():
    device = DummyDevice()
    # Simulate a subentry.data with neither location_inside nor location_outside
    reconfig = {device.id: {}}
    # Should return None or fallback, not raise
    assert get_location(device, reconfig) is None
