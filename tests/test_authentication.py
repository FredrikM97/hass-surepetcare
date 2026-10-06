"""Regression tests for expired Sure Petcare credentials."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from surepcio.security.exceptions import ApiError, AuthenticationError

from custom_components.surepcha import setup_devices
from custom_components.surepcha.coordinator import (
    SurePetCareDeviceDataUpdateCoordinator,
    SurePetCareHouseholdTimelineCoordinator,
)

from .support import MockConfigEntry


@pytest.fixture
def mock_coordinator_update_data() -> Generator[None]:
    """Exercise real coordinator polling rather than the global polling mock."""
    yield


@pytest.mark.parametrize(
    ("status", "expected"),
    [(401, ConfigEntryAuthFailed), (500, ConfigEntryNotReady)],
)
async def test_setup_http_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    status: int,
    expected: type[Exception],
) -> None:
    """Only unauthorized API responses require new credentials."""
    client = MagicMock()
    client.login = AsyncMock(return_value=True)
    client.api = AsyncMock(side_effect=ApiError("get", "household", status, "Error"))
    client.close = AsyncMock()
    with (
        patch("custom_components.surepcha.SurePetcareClient", return_value=client),
        pytest.raises(expected),
    ):
        await setup_devices(hass, mock_config_entry)

    client.close.assert_awaited_once()


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (AuthenticationError("Invalid token"), ConfigEntryAuthFailed),
        (TimeoutError(), ConfigEntryNotReady),
    ],
)
async def test_setup_login_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    error: Exception,
    expected: type[Exception],
) -> None:
    """Login failures close the session and distinguish auth from connectivity."""
    client = MagicMock()
    client.login = AsyncMock(side_effect=error)
    client.close = AsyncMock()

    with (
        patch("custom_components.surepcha.SurePetcareClient", return_value=client),
        pytest.raises(expected),
    ):
        await setup_devices(hass, mock_config_entry)

    client.close.assert_awaited_once()


@pytest.mark.parametrize("method", ["_async_setup", "_async_update_data"])
@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ApiError("get", "device", 401, "Unauthorized"), ConfigEntryAuthFailed),
        (ApiError("get", "device", 500, "Server error"), ApiError),
        (AuthenticationError("Missing token"), ConfigEntryAuthFailed),
    ],
)
async def test_device_auth_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    method: str,
    error: Exception,
    expected: type[Exception],
) -> None:
    """Device initialization and polling surface authentication failures."""
    client = MagicMock()
    client.api = AsyncMock(side_effect=error)
    coordinator = SurePetCareDeviceDataUpdateCoordinator(
        hass, mock_config_entry, client, MagicMock()
    )

    with pytest.raises(expected):
        await getattr(coordinator, method)()


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ApiError("get", "timeline", 401, "Unauthorized"), ConfigEntryAuthFailed),
        (ApiError("get", "timeline", 500, "Server error"), ApiError),
        (AuthenticationError("Missing token"), ConfigEntryAuthFailed),
    ],
)
async def test_timeline_auth_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    error: Exception,
    expected: type[Exception],
) -> None:
    """Timeline polling triggers reauth without changing the event cursor."""
    client = MagicMock()
    client.api = AsyncMock(side_effect=error)
    coordinator = SurePetCareHouseholdTimelineCoordinator(
        hass, mock_config_entry, client, MagicMock()
    )

    with pytest.raises(expected):
        await coordinator._async_update_data()

    assert coordinator._cursor is None
    assert not coordinator._seen_ids


@pytest.mark.parametrize(
    "coordinator_type",
    [SurePetCareDeviceDataUpdateCoordinator, SurePetCareHouseholdTimelineCoordinator],
)
@pytest.mark.usefixtures("enable_custom_integrations")
async def test_polling_starts_reauth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    coordinator_type: type[
        SurePetCareDeviceDataUpdateCoordinator | SurePetCareHouseholdTimelineCoordinator
    ],
) -> None:
    """Home Assistant starts reauthentication when a live poll receives a 401."""
    mock_config_entry.add_to_hass(hass)
    client = MagicMock()
    client.api = AsyncMock(side_effect=ApiError("get", "resource", 401, "Unauthorized"))
    coordinator = coordinator_type(hass, mock_config_entry, client, MagicMock())

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress()
    assert len(flows) == 1
    assert flows[0]["step_id"] == "reauth_confirm"
    assert flows[0]["context"]["entry_id"] == mock_config_entry.entry_id
    assert not coordinator.last_update_success
