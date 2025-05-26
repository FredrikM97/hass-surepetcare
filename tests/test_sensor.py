from unittest.mock import AsyncMock
from custom_components.surepetcare.sensor import PetLocationSensor, PetLastFedSensor, BatterySensor
import pytest

@pytest.mark.asyncio
async def test_pet_location_sensor_update_sets_native_value(hass):
    pet = {"id": 1, "name": "Fluffy"}
    coordinator = AsyncMock()
    coordinator.data = {"location": "Inside"}
    sensor = PetLocationSensor(coordinator, pet)
    await sensor.async_update()
    assert sensor.state == "Inside"
    assert sensor.name == "Pet Fluffy Location"
    assert sensor.unit_of_measurement == "Location"

async def test_pet_last_fed_sensor_update_sets_native_value(hass):
    pet = {"id": 2, "name": "Bella"}
    coordinator = AsyncMock()
    coordinator.data = {"last_fed": "2024-06-01T12:00:00Z"}
    sensor = PetLastFedSensor(coordinator, pet)
    await sensor.async_update()
    assert sensor.state == "2024-06-01T12:00:00Z"
    assert sensor.name == "Pet Bella Last Fed"
    assert sensor.unit_of_measurement == "Time"

def test_pet_location_sensor_properties():
    pet = {"id": 3, "name": "Max"}
    coordinator = AsyncMock()
    coordinator.data = {"location": "Outside"}
    sensor = PetLocationSensor(coordinator, pet)
    assert sensor.name == "Pet Max Location"
    assert sensor.unit_of_measurement == "Location"

def test_pet_last_fed_sensor_properties():
    pet = {"id": 4, "name": "Luna"}
    coordinator = AsyncMock()
    coordinator.data = {"last_fed": "2024-06-01T18:30:00Z"}
    sensor = PetLastFedSensor(coordinator, pet)
    assert sensor.name == "Pet Luna Last Fed"
    assert sensor.unit_of_measurement == "Time"

@pytest.mark.asyncio
async def test_battery_sensor_properties_and_update():
    device = {"id": 5, "name": "Rex"}
    coordinator = AsyncMock()
    coordinator.data = {"battery": 85}
    sensor = BatterySensor(coordinator, device)
    await sensor.async_update()
    assert sensor.state == 85
    assert sensor.name == "Rex Battery"
    assert sensor.unit_of_measurement == "%"