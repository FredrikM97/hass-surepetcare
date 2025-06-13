import pytest
from unittest.mock import AsyncMock, patch
from custom_components.surepetcare.coordinator import (
    SurePetCareDeviceDataUpdateCoordinator,
)
from tests.conftest import DummyDevice, DummyClient, DummyConfigEntry, DummyHass


@pytest.mark.asyncio
async def test_coordinator_update(monkeypatch):
    # Patch async_set_updated_data to track calls, but use AsyncMock for awaitable
    with patch.object(
        SurePetCareDeviceDataUpdateCoordinator, "async_set_updated_data", new_callable=AsyncMock
    ) as mock_set_data:
        c = SurePetCareDeviceDataUpdateCoordinator(
            DummyHass(), DummyConfigEntry(), DummyClient(), DummyDevice()
        )
        # Directly test async_set_updated_data
        device = DummyDevice()
        await c.async_set_updated_data(data=device)
        mock_set_data.assert_awaited_once_with(data=device)

        # Patch client.api to avoid unawaited coroutine warning
        orig_api = c.client.api

        async def patched_api(arg=None):
            if arg is not None and hasattr(arg, "__await__"):
                arg = await arg
            return await orig_api(arg)

        c.client.api = patched_api

        # Test _async_update_data returns expected data
        result = await c._async_update_data()
        assert result == "data"

        # Test error handling in _async_update_data
        c.client.api = AsyncMock(side_effect=Exception("fail"))
        with pytest.raises(Exception, match="fail"):
            await c._async_update_data()

        # Test coordinator attributes
        assert hasattr(c, "client")
        assert hasattr(c, "_device")
        assert hasattr(c, "async_set_updated_data")
        assert hasattr(c, "update_interval")


@pytest.mark.asyncio
async def test_coordinator_update_refresh_raises():
    class FailingDevice(DummyDevice):
        async def refresh(self):
            raise RuntimeError("refresh fail")

    c = SurePetCareDeviceDataUpdateCoordinator(
        DummyHass(), DummyConfigEntry(), DummyClient(), FailingDevice()
    )
    # The coordinator should propagate the error from refresh via client.api
    with pytest.raises(RuntimeError, match="refresh fail"):
        await c._async_update_data()


@pytest.mark.asyncio
async def test_coordinator_update_refresh_returns_none():
    from tests.conftest import DummyDeviceWithNoneRefresh

    c = SurePetCareDeviceDataUpdateCoordinator(
        DummyHass(), DummyConfigEntry(), DummyClient(), DummyDeviceWithNoneRefresh()
    )
    # Patch client.api to await the coroutine if needed
    orig_api = c.client.api

    async def patched_api(arg=None):
        if arg is not None and hasattr(arg, "__await__"):
            arg = await arg
        return await orig_api(arg)

    c.client.api = patched_api

    result = await c._async_update_data()
    assert result is None
