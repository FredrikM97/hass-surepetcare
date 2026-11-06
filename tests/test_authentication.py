"""Regression tests for expired Sure Petcare credentials."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.entity_platform import async_get_platforms
from surepcio.security.exceptions import ApiError, AuthenticationError

from custom_components.surepcha import setup_devices
from custom_components.surepcha.coordinator import (
    SurePetCareCoordinator,
)

from . import initialize_entry
from .support import MockConfigEntry


@pytest.fixture
def mock_coordinator_update_data() -> Generator[None]:
    """Exercise real coordinator polling rather than the global polling mock."""
    yield


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.parametrize("auth_failed", [False, True])
async def test_first_refresh_failure_unloads_restored_entities_and_can_retry(
    hass, mock_client, mock_config_entry, mock_devices, mock_pets, auth_failed
):
    failed_coordinators = []
    error = ConfigEntryAuthFailed("Expired token") if auth_failed else TimeoutError()

    async def fail_refresh(coordinator):
        failed_coordinators.append(coordinator)
        assert coordinator._listeners
        assert coordinator._unsub_refresh is None
        assert any(
            state.entity_id.startswith("sensor.") for state in hass.states.async_all()
        )
        raise error

    with (
        patch.object(SurePetCareCoordinator, "_async_update_data", new=fail_refresh),
        patch.object(mock_client, "close", wraps=mock_client.close) as close,
    ):
        await initialize_entry(
            hass, mock_client, mock_config_entry, mock_devices, mock_pets
        )
    assert len(failed_coordinators) == 1
    coordinator = failed_coordinators[0]
    assert coordinator._listeners == {}
    assert coordinator._unsub_refresh is None
    assert coordinator._shutdown_requested
    assert all(
        not platform.entities for platform in async_get_platforms(hass, "surepcha")
    )
    # HA retains unavailable registry placeholders after normal platform unload.
    assert all(
        state.state == "unavailable"
        for state in hass.states.async_all()
        if state.entity_id.startswith(("sensor.", "switch.", "binary_sensor.", "lock."))
    )
    assert close.await_count >= 2
    assert mock_config_entry.state is (
        ConfigEntryState.SETUP_ERROR if auth_failed else ConfigEntryState.SETUP_RETRY
    )
    flows = hass.config_entries.flow.async_progress()
    assert len(flows) == int(auth_failed)
    if auth_failed:
        assert flows[0]["step_id"] == "reauth_confirm"

    with patch(
        "custom_components.surepcha.SurePetcareClient", return_value=mock_client
    ):
        assert await hass.config_entries.async_reload(mock_config_entry.entry_id)
        await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.LOADED
    retried = mock_config_entry.runtime_data.coordinator
    assert retried is not coordinator
    assert retried._unsub_refresh is not None
    assert retried.state.seen_id is not None
    assert coordinator._listeners == {}


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


@pytest.mark.parametrize("initial", [False, True])
@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ApiError("get", "device", 401, "Unauthorized"), ConfigEntryAuthFailed),
        (AuthenticationError("Missing token"), ConfigEntryAuthFailed),
    ],
)
async def test_device_auth_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    initial: bool,
    error: Exception,
    expected: type[Exception],
) -> None:
    """Initial and subsequent refreshes surface authentication failures."""
    client = MagicMock()
    client.api = AsyncMock(side_effect=error)
    if initial:
        mock_config_entry = MockConfigEntry(
            domain=mock_config_entry.domain,
            state=ConfigEntryState.SETUP_IN_PROGRESS,
        )
    device = MagicMock(id=1)
    coordinator = SurePetCareCoordinator(
        hass, mock_config_entry, client, MagicMock(id=1), [device]
    )

    with pytest.raises(expected):
        if initial:
            await coordinator.async_config_entry_first_refresh()
        else:
            coordinator.data = {}
            await coordinator.async_refresh_device(device)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ApiError("get", "timeline", 401, "Unauthorized"), ConfigEntryAuthFailed),
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
    coordinator = SurePetCareCoordinator(
        hass, mock_config_entry, client, MagicMock(id=1), []
    )
    await coordinator._async_setup()

    with pytest.raises(expected):
        await coordinator._async_update_data()

    assert coordinator.state._cursor is None
    assert not coordinator.state._seen_ids


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_polling_starts_reauth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Home Assistant starts reauthentication when a live poll receives a 401."""
    mock_config_entry.add_to_hass(hass)
    client = MagicMock()
    client.api = AsyncMock(side_effect=ApiError("get", "resource", 401, "Unauthorized"))
    coordinator = SurePetCareCoordinator(
        hass, mock_config_entry, client, MagicMock(id=1), []
    )

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress()
    assert len(flows) == 1
    assert flows[0]["step_id"] == "reauth_confirm"
    assert flows[0]["context"]["entry_id"] == mock_config_entry.entry_id
    assert not coordinator.last_update_success


@pytest.mark.parametrize("timeline_fails", [False, True])
async def test_household_isolates_endpoint_failures_and_recovers(
    hass, mock_config_entry, timeline_fails
):
    good, bad = MagicMock(id=1), MagicMock(id=2)
    good.refresh.return_value = "good"
    bad.refresh.return_value = "bad"
    household = MagicMock(id=7777)
    household.get_timeline.return_value = "timeline"
    client = MagicMock()
    failure = ApiError("get", "endpoint", 500, "Server error")

    def respond(command):
        if command == ("timeline" if timeline_fails else "bad"):
            raise failure
        return [] if command == "timeline" else None

    client.api = AsyncMock(side_effect=respond)
    coordinator = SurePetCareCoordinator(
        hass, mock_config_entry, client, household, [good, bad]
    )
    await coordinator._async_setup()
    notifications = []
    coordinator.async_add_listener(
        lambda: notifications.append(dict(coordinator.device_errors))
    )
    await coordinator._async_update_data()
    assert notifications
    if timeline_fails:
        assert coordinator.device_errors == {}
        assert coordinator.state.timeline_error is failure
        assert coordinator.state.seen_id is None
    else:
        assert coordinator.device_errors == {2: failure}
        assert coordinator.state.timeline_error is None
    assert {call.args[0] for call in client.api.await_args_list} == {
        "good",
        "bad",
        "timeline",
    }

    client.api.side_effect = lambda command: [] if command == "timeline" else None
    notifications.clear()
    client.api.reset_mock()
    await coordinator._async_update_data()
    assert notifications
    assert {call.args[0] for call in client.api.await_args_list} == (
        {"timeline"} if timeline_fails else {"bad", "timeline"}
    )
    assert coordinator.device_errors == {}
    assert coordinator.state.timeline_error is None
    assert coordinator.state.seen_id is not None
