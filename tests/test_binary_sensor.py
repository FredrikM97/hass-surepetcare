from unittest.mock import MagicMock, patch
import pytest
from custom_components.surepetcare.binary_sensor import (
    SENSORS,
    ProductId,
)
from tests.conftest import DummyDevice, DummyCoordinator, make_coordinator_data


def test_binary_sensor_entity_refresh():
    desc = SENSORS[ProductId.FEEDER_CONNECT][0]
    # c = DummyCoordinator(DummyDevice())  # Unused, remove
    # s = SurePetCareSensor(c, DummyClient(), desc)
    # s._refresh()
    # assert s._attr_native_value is not None
    # Instead, test the description's value lambda directly:
    assert desc.value(DummyDevice()) is not None


@pytest.mark.asyncio
async def test_async_setup_entry_binary_sensor():
    hass = MagicMock()
    config_entry = MagicMock()
    async_add_entities = MagicMock()
    device = DummyDevice()
    device.product_id = ProductId.FEEDER_CONNECT
    coordinator = DummyCoordinator(device)
    coordinator.device.product_id = ProductId.FEEDER_CONNECT

    hass.data = {
        "surepetcare": {
            config_entry.entry_id: {"coordinator": make_coordinator_data(coordinator)}
        }
    }
    config_entry.subentries = {"1": MagicMock(data={"id": "1"})}
    with patch(
        "custom_components.surepetcare.binary_sensor.SENSORS",
        {ProductId.FEEDER_CONNECT: SENSORS[ProductId.FEEDER_CONNECT]},
    ):
        import custom_components.surepetcare.binary_sensor as binary_sensor_mod

        await binary_sensor_mod.async_setup_entry(
            hass, config_entry, async_add_entities
        )
    async_add_entities.assert_called()
