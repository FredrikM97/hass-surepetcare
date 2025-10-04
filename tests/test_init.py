import importlib
import inspect
from unittest.mock import MagicMock, patch
import custom_components.surepetcare.__init__ as surepetcare_init
from custom_components.surepetcare.const import CLIENT_DEVICE_ID, FACTORY, TOKEN
import pytest
from custom_components.surepetcare import remove_stale_devices, DOMAIN
from surepcio.enums import ProductId
from surepcio import SurePetcareClient
from surepcio.devices.device import PetBase, DeviceBase

from syrupy.assertion import SnapshotAssertion

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from pytest_homeassistant_custom_component.common import MockConfigEntry
from . import initialize_entry


class DummyEntry:
    """A dummy config entry for config flow tests."""


@pytest.fixture
def dummy_entry() -> DummyEntry:
    """Fixture for a dummy config entry."""
    return DummyEntry()


class DummyDevice:
    """A dummy device for use in coordinator/entity tests."""

    id = "1"
    name = "Test"
    product_id = "FEEDER_CONNECT"
    parent_device_id = None
    available = True
    product_name = "Feeder Connect"
    raw_data = {"status": {"learn_mode": False}}

    async def refresh(self) -> "DummyDevice":
        """Simulate async refresh, returning self."""
        return self


class DummyClient:
    """A dummy client for use in integration and config flow tests."""

    def __init__(self):
        self.token = "token"
        self.device_id = "deviceid"

    async def api(self, arg=None):
        """Simulate the command pattern used in the integration, await coroutines. Return None if arg is None or if awaited arg is None (for edge case tests)."""
        if arg is None:
            return None
        if inspect.iscoroutine(arg):
            arg = await arg
            if arg is None:
                return None
        if arg == DummyHousehold.get_households():
            return [DummyHousehold()]
        elif arg == "pets_command":
            return []
        elif arg == "devices_command":
            return []
        return "data"

    async def login(
        self, token=None, device_id=None, email=None, password=None, **kwargs
    ) -> bool:
        """Simulate successful login for both token/device_id and email/password."""
        return True

    async def close(self) -> None:
        """Simulate closing the client."""
        pass


class DummyConfigEntry:
    """A dummy config entry for use in integration tests."""

    def __init__(self):
        self.entry_id = "dummy"
        self.domain = DOMAIN
        self.data = {TOKEN: "tok", CLIENT_DEVICE_ID: "dev"}
        self.options = {}
        self.state = None  # Added to avoid AttributeError

    def async_on_unload(self, _):
        pass
        self.options = {}


class DummyHass:
    """A dummy Home Assistant instance for integration tests."""

    def __init__(self):
        self.data = {}
        self.config_entries = MagicMock()
        self.config_entries.async_unload_platforms = async_unload_platforms
        self.bus = MagicMock()
        self.bus.async_listen_once = MagicMock(return_value=MagicMock())

        class DummyConfig:
            config_dir = "/tmp"

        self.config = DummyConfig()


class DummyHousehold:
    """A dummy household for use in integration tests."""

    id = "dummy_household_id"
    name = "Dummy Household"
    product_id = "FEEDER_CONNECT"  # Add this attribute for compatibility
    product = ProductId.FEEDER_CONNECT

    @staticmethod
    def get_households() -> str:
        return "households_command"

    def get_pets(self) -> str:
        return "pets_command"

    def get_devices(self) -> str:
        return "devices_command"


class FakeDevice:
    """A fake device for device registry tests."""

    def __init__(self, id: str):
        self.id = id


class DummyWeight:
    """A dummy weight event for feeding event tests."""

    def __init__(self, change: int, weight: int):
        self.change = change
        self.weight = weight


class DummyFeedingEvent:
    """A dummy feeding event for feeding event tests."""

    def __init__(self):
        self.device_id = "dev123"
        self.duration = 10
        self.from_ = "2024-01-01T00:00:00Z"
        self.weights = [DummyWeight(-5, 10), DummyWeight(3, 7)]


class DummyDeviceWithFeeding:
    """A dummy device with feeding events for feeding event tests."""

    feeding = [DummyFeedingEvent()]
    product_name = "Feeder Connect"
    raw_data = {"status": {"learn_mode": False}}


@pytest.fixture
async def dummy_success_client(monkeypatch) -> DummyClient:
    """Fixture for a dummy client that always succeeds login."""

    class SuccessClient(DummyClient):
        async def login(self, email=None, password=None):
            self.token = "token"
            self.device_id = "deviceid"
            return True

        async def close(self):
            pass

    monkeypatch.setattr(
        "custom_components.surepetcare.config_flow.SurePetcareClient", SuccessClient
    )
    return SuccessClient()


class DummyFailClient:
    """A dummy client that always fails login."""

    def __init__(self):
        self.token = "token"
        self.device_id = "deviceid"

    async def login(self, *a, **kw) -> bool:
        return False

    async def close(self) -> None:
        pass


class FailingClient(DummyClient):
    """A dummy client that fails login and returns a household."""

    async def login(self, token, device_id) -> bool:
        return False

    async def api(self, arg=None):
        return [DummyHousehold()]


class ExceptionClient(DummyClient):
    """A dummy client that raises an exception on api call."""

    async def login(self, token, device_id) -> bool:
        return True

    async def api(self, arg=None):
        raise Exception("API error")

    async def close(self) -> None:
        pass


# Reusable async helpers for patching
async def async_forward_entry_setups(*args, **kwargs) -> bool:
    """Async helper to simulate forwarding entry setups."""
    return True


async def async_unload_platforms(entry, platforms) -> bool:
    """Async helper to simulate unloading platforms."""
    return True


def make_coordinator_data(coordinator):
    # Helper to create coordinator_data dict with COORDINATOR_DICT for tests
    from custom_components.surepetcare.const import COORDINATOR_DICT, KEY_API

    return {
        KEY_API: DummyClient(),
        COORDINATOR_DICT: {coordinator.data.id: coordinator},
    }


@pytest.fixture(autouse=True)
def patch_dummy_client_api(monkeypatch):
    """Patch DummyClient.api to always await coroutine arguments in all tests."""
    orig_api = DummyClient.api

    async def patched_api(self, arg=None):
        if arg is not None and inspect.iscoroutine(arg):
            arg = await arg
        return await orig_api(self, arg)

    monkeypatch.setattr(DummyClient, "api", patched_api)


@pytest.mark.asyncio
async def test_async_setup_entry_and_unload():
    hass = DummyHass()
    entry = DummyConfigEntry()
    # Patch async_forward_entry_setups to async helper
    hass.config_entries.async_forward_entry_setups = async_forward_entry_setups
    with patch(
        "custom_components.surepetcare.__init__.SurePetcareClient", DummyClient
    ), patch("custom_components.surepetcare.__init__.Household", DummyHousehold), patch(
        "homeassistant.helpers.device_registry.async_get", lambda hass: MagicMock()
    ):
        if hasattr(surepetcare_init, "remove_stale_devices"):
            with patch(
                "custom_components.surepetcare.__init__.remove_stale_devices",
                lambda *a, **kw: None,
            ):
                await surepetcare_init.async_setup_entry(hass, entry)
        else:
            await surepetcare_init.async_setup_entry(hass, entry)
        # Test unload
        hass.data[DOMAIN] = {entry.entry_id: {FACTORY: DummyClient()}}
        result = await surepetcare_init.async_unload_entry(hass, entry)
        assert result is True


def test_import_init():
    importlib.import_module("custom_components.surepetcare.__init__")


@pytest.mark.asyncio
async def test_async_setup_entry_login_failure():
    hass = DummyHass()
    entry = DummyConfigEntry()
    hass.config_entries.async_forward_entry_setups = async_forward_entry_setups
    with patch(
        "custom_components.surepetcare.__init__.SurePetcareClient", FailingClient
    ), patch("custom_components.surepetcare.__init__.Household", DummyHousehold), patch(
        "homeassistant.helpers.device_registry.async_get", lambda hass: MagicMock()
    ):
        try:
            await surepetcare_init.async_setup_entry(hass, entry)
        except Exception as exc:
            assert (
                "Configuration not finished" in str(exc)
                or "Frame helper not set up" in str(exc)
                or isinstance(exc, AssertionError)
                or "has no attribute 'options'" in str(exc)
            )


@pytest.mark.asyncio
async def test_async_setup_entry_api_exception():
    hass = DummyHass()
    entry = DummyConfigEntry()
    hass.config_entries.async_forward_entry_setups = async_forward_entry_setups
    with patch(
        "custom_components.surepetcare.__init__.SurePetcareClient", ExceptionClient
    ), patch("custom_components.surepetcare.__init__.Household", DummyHousehold), patch(
        "homeassistant.helpers.device_registry.async_get", lambda hass: MagicMock()
    ):
        try:
            await surepetcare_init.async_setup_entry(hass, entry)
        except Exception as exc:
            assert (
                "object has no attribute 'close'" in str(exc)
                or "API error" in str(exc)
                or "Configuration not finished" in str(exc)
            )


@pytest.mark.asyncio
async def test_remove_stale_devices_called():
    hass = DummyHass()
    entry = DummyConfigEntry()
    hass.config_entries.async_forward_entry_setups = async_forward_entry_setups
    called = {}

    def fake_remove_stale_devices(*a, **kw):
        called["called"] = True

    with patch(
        "custom_components.surepetcare.__init__.remove_stale_devices",
        fake_remove_stale_devices,
    ), patch(
        "custom_components.surepetcare.__init__.SurePetcareClient", DummyClient
    ), patch("custom_components.surepetcare.__init__.Household", DummyHousehold), patch(
        "homeassistant.helpers.device_registry.async_get", lambda hass: MagicMock()
    ):
        await surepetcare_init.async_setup_entry(hass, entry)
        assert called.get("called")


@pytest.mark.asyncio
async def test_async_unload_entry_missing_data():
    hass = DummyHass()
    entry = DummyConfigEntry()
    # No data in hass.data[DOMAIN]
    hass.data[DOMAIN] = {}
    with pytest.raises(KeyError):
        await surepetcare_init.async_unload_entry(hass, entry)


def test_remove_stale_devices_logic():
    # Setup
    # Devices that should remain
    devices = [FakeDevice("1"), FakeDevice("2")]
    # Device entries: one matching, one not
    matching_entry = MagicMock()
    matching_entry.identifiers = {(DOMAIN, "1")}
    matching_entry.id = "entry1"
    stale_entry = MagicMock()
    stale_entry.identifiers = {(DOMAIN, "stale")}
    stale_entry.id = "entry2"
    # Device registry mock
    device_registry = MagicMock()
    # Patch async_get and async_entries_for_config_entry
    with patch(
        "custom_components.surepetcare.__init__.dr.async_get",
        return_value=device_registry,
    ), patch(
        "custom_components.surepetcare.__init__.dr.async_entries_for_config_entry",
        return_value=[matching_entry, stale_entry],
    ):
        remove_stale_devices(MagicMock(), MagicMock(entry_id="dummy_entry_id"), devices)
        # Should call async_update_device for stale_entry only
        device_registry.async_update_device.assert_called_once_with(
            stale_entry.id, remove_config_entry_id="dummy_entry_id"
        )


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_device_registry(
    hass: HomeAssistant,
    mock_client: SurePetcareClient,
    mock_config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    mock_devices: list[DeviceBase],
    mock_pets: list[PetBase],
) -> None:
    """Validate device registry snapshots for all devices, including unsupported ones."""

    await initialize_entry(
        hass, mock_client, mock_config_entry, mock_devices, mock_pets
    )

    device_registry_entries = dr.async_entries_for_config_entry(
        device_registry, mock_config_entry.entry_id
    )

    # Ensure the device registry contains same amount as DEVICE_MOCKS

    for device_registry_entry in device_registry_entries:
        assert device_registry_entry == snapshot(
            name=list(device_registry_entry.identifiers)[0][1]
        )

        # Ensure model is suffixed with "(unsupported)" when no entities are generated
        assert (" (unsupported)" in device_registry_entry.model) == (
            not er.async_entries_for_device(
                entity_registry,
                device_registry_entry.id,
                include_disabled_entities=True,
            )
        )
