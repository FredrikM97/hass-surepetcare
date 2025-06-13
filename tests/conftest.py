# Shared test helpers for config_flow tests
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from custom_components.surepetcare.entity import SurePetCareBaseEntity
import inspect


class DummyEntry:
    """A dummy config entry with a subentries dict for config flow tests."""

    subentries = {
        "subid": MagicMock(
            data={
                "product_id": "DUAL_SCAN_PET_DOOR",
                "name": "TestDevice",
                "location_inside": "A",
                "location_outside": "B",
            }
        )
    }


class DummySubentry:
    """A dummy subentry for config flow subentry tests."""

    subentry_id = "subid"
    data = {"location_inside": "A", "location_outside": "B"}


@pytest.fixture
def dummy_entry() -> DummyEntry:
    """Fixture for a dummy config entry."""
    return DummyEntry()


@pytest.fixture
def dummy_subentry() -> DummySubentry:
    """Fixture for a dummy subentry."""
    return DummySubentry()


def make_dummy_handler(
    handler_cls: type, entry=None, subentry=None, source: str = "user"
):
    """Create a dummy handler instance with patched source property for config flow tests."""
    handler = handler_cls.__new__(handler_cls)
    handler._entry = entry
    handler._subentry = subentry
    # Patch the source property to return the desired value
    patcher = patch.object(handler_cls, "source", new_callable=PropertyMock)
    mock_source = patcher.start()
    mock_source.return_value = source
    # Attach patcher so test can stop it if needed
    handler._source_patcher = patcher
    return handler


def stop_dummy_handler_patches(handler) -> None:
    """Stop the patcher for a dummy handler's source property."""
    if hasattr(handler, "_source_patcher"):
        handler._source_patcher.stop()


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


class DummyDeviceWithNoneRefresh(DummyDevice):
    """A dummy device whose refresh returns None (for edge case tests)."""
    product_name = "Feeder Connect"
    raw_data = {"status": {"learn_mode": False}}

    async def refresh(self):
        return None


class DummyCoordinator:
    """A dummy coordinator for use in coordinator tests."""

    def __init__(self, device: DummyDevice = None):
        self.data = device or DummyDevice()
        self.device = self.data
        self.COORDINATOR_DICT = {self.data.id: self}
        self.product_id = getattr(self.data, "product_id", "FEEDER_CONNECT")

    # Add a dummy _observe_update for test_coordinator_update
    def _observe_update(self):
        pass


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

    entry_id = "dummy"
    data = {"token": "tok", "client_device_id": "dev"}

    def async_on_unload(self, _):
        pass

    subentries = {}
    state = None  # Added to avoid AttributeError


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


class DummyApi:
    """A dummy API placeholder."""

    pass


class DummyEntity(SurePetCareBaseEntity):
    """A dummy entity for entity tests."""

    def _refresh(self) -> None:
        self.refreshed = True

    def _handle_coordinator_update(self) -> None:
        self.updated = True
        super()._handle_coordinator_update()


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
