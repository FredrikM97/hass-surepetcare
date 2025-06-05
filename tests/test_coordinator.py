import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from custom_components.surepetcare.coordinator import SurePetCareDeviceDataUpdateCoordinator
from tests.conftest import DummyDevice, DummyClient, DummyConfigEntry, DummyHass

@pytest.mark.asyncio
async def test_coordinator_update(monkeypatch):
    # Patch async_set_updated_data to track calls
    with patch.object(SurePetCareDeviceDataUpdateCoordinator, "async_set_updated_data") as mock_set_data:
        c = SurePetCareDeviceDataUpdateCoordinator(
            DummyHass(),
            DummyConfigEntry(),
            DummyClient(),
            DummyDevice()
        )
        # Test _observe_update triggers async_set_updated_data
        device = DummyDevice()
        c._observe_update(device)
        mock_set_data.assert_called_once_with(data=device)

        # Test _async_update_data returns expected data
        result = await c._async_update_data()
        assert result == "data"

        # Test error handling in _async_update_data
        c.client.api = AsyncMock(side_effect=Exception("fail"))
        with pytest.raises(Exception, match="fail"):
            await c._async_update_data()

        # Test coordinator attributes
        assert hasattr(c, "client")
        assert hasattr(c, "device")
        assert hasattr(c, "async_set_updated_data")
        assert hasattr(c, "update_interval")

@pytest.mark.asyncio
async def test_coordinator_update_refresh_raises():
    class FailingDevice(DummyDevice):
        async def refresh(self):
            raise RuntimeError("refresh fail")
    c = SurePetCareDeviceDataUpdateCoordinator(
        DummyHass(),
        DummyConfigEntry(),
        DummyClient(),
        FailingDevice()
    )
    # The coordinator should propagate the error from refresh via client.api
    with pytest.raises(RuntimeError, match="refresh fail"):
        await c._async_update_data()

@pytest.mark.asyncio
async def test_coordinator_update_refresh_returns_none():
    from tests.conftest import DummyDeviceWithNoneRefresh
    c = SurePetCareDeviceDataUpdateCoordinator(
        DummyHass(),
        DummyConfigEntry(),
        DummyClient(),
        DummyDeviceWithNoneRefresh()
    )
    result = await c._async_update_data()
    assert result is None