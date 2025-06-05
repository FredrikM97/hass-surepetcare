from unittest.mock import MagicMock, patch
import pytest
from custom_components.surepetcare import binary_sensor
from custom_components.surepetcare.binary_sensor import SurePetCareSensor, SENSORS, ProductId
from tests.conftest import DummyDevice, DummyCoordinator, DummyClient


def test_binary_sensor_entity_refresh():
    desc = SENSORS[ProductId.FEEDER_CONNECT][0]
    c = DummyCoordinator(DummyDevice())
    s = SurePetCareSensor(c, DummyClient(), desc)
    s._refresh()
    assert s._attr_native_value is not None

@pytest.mark.asyncio
async def test_async_setup_entry_binary_sensor():
    hass = MagicMock()
    config_entry = MagicMock()
    async_add_entities = MagicMock()
    device = DummyDevice()
    coordinator = DummyCoordinator(device)
    coordinator.device.product_id = ProductId.FEEDER_CONNECT
    from custom_components.surepetcare.const import KEY_API, COORDINATOR_LIST
    hass.data = {"surepetcare": {config_entry.entry_id: {"coordinator": {KEY_API: DummyClient(), COORDINATOR_LIST: [coordinator]}}}}
    config_entry.subentries = {"1": MagicMock(data={"id": "1"})}
    with patch("custom_components.surepetcare.binary_sensor.SENSORS", {ProductId.FEEDER_CONNECT: SENSORS[ProductId.FEEDER_CONNECT]}):
        await binary_sensor.async_setup_entry(hass, config_entry, async_add_entities)
    async_add_entities.assert_called()
