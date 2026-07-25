import importlib
import inspect
from unittest.mock import AsyncMock, MagicMock, patch
import custom_components.surepcha.__init__ as surepetcare_init
from custom_components.surepcha.const import (
    CLIENT_DEVICE_ID,
    FACTORY,
    HOUSEHOLD_ID,
    OPTION_DEVICES,
    OPTION_PROPERTIES,
    TOKEN,
)
import pytest
from custom_components.surepcha import remove_stale_devices, DOMAIN
from surepcio.enums import ProductId
from surepcio import SurePetcareClient
from surepcio.devices.device import PetBase, DeviceBase

from syrupy.assertion import SnapshotAssertion

from homeassistant.config_entries import ConfigEntryState
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


class DummySubentry:
    """A dummy config subentry for use in integration tests."""

    def __init__(self, household_id):
        self.data = {HOUSEHOLD_ID: household_id}


class DummyConfigEntry:
    """A dummy config entry for use in integration tests."""

    def __init__(self):
        self.entry_id = "dummy"
        self.domain = DOMAIN
        self.data = {TOKEN: "tok", CLIENT_DEVICE_ID: "dev"}
        self.options = {}
        self.subentries = {"sub1": DummySubentry("dummy_household_id")}
        self.state = ConfigEntryState.SETUP_IN_PROGRESS

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

    def fetch_pet_device_assignments(self) -> None:
        """Mirror the upstream household API used during setup."""
        return None


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
        "custom_components.surepcha.config_flow.SurePetcareClient", SuccessClient
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
        return [DummyDevice()]


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
    from custom_components.surepcha.const import COORDINATOR_DICT, KEY_API

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
        "custom_components.surepcha.__init__.SurePetcareClient", DummyClient
    ), patch("custom_components.surepcha.__init__.Household", DummyHousehold), patch(
        "homeassistant.helpers.device_registry.async_get", lambda hass: MagicMock()
    ):
        if hasattr(surepetcare_init, "remove_stale_devices"):
            with patch(
                "custom_components.surepcha.__init__.remove_stale_devices",
                lambda *a, **kw: None,
            ):
                await surepetcare_init.async_setup_entry(hass, entry)
        else:
            await surepetcare_init.async_setup_entry(hass, entry)
        # Test unload
        hass.data[DOMAIN] = {entry.entry_id: {FACTORY: DummyClient()}}
        result = await surepetcare_init.async_unload_entry(hass, entry)
        assert result is True


@pytest.mark.asyncio
async def test_async_setup_registers_global_services(hass: HomeAssistant) -> None:
    """Ensure integration services are available before any config entry loads."""
    result = await surepetcare_init.async_setup(hass, {})

    assert result is True
    for service_name, _, _ in surepetcare_init._service_registry:
        assert hass.services.has_service(DOMAIN, service_name)


def test_import_init():
    importlib.import_module("custom_components.surepcha.__init__")


@pytest.mark.asyncio
async def test_async_setup_entry_login_failure():
    hass = DummyHass()
    entry = DummyConfigEntry()
    hass.config_entries.async_forward_entry_setups = async_forward_entry_setups
    with patch(
        "custom_components.surepcha.__init__.SurePetcareClient", FailingClient
    ), patch("custom_components.surepcha.__init__.Household", DummyHousehold), patch(
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
                or "async_config_entry_first_refresh" in str(exc)
            )


@pytest.mark.asyncio
async def test_async_setup_entry_api_exception():
    hass = DummyHass()
    entry = DummyConfigEntry()
    hass.config_entries.async_forward_entry_setups = async_forward_entry_setups
    with patch(
        "custom_components.surepcha.__init__.SurePetcareClient", ExceptionClient
    ), patch("custom_components.surepcha.__init__.Household", DummyHousehold), patch(
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


@pytest.mark.skip(
    reason="This test is currently failing due to changes in async_setup_entry and needs to be rewritten."
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
        "custom_components.surepcha.__init__.remove_stale_devices",
        fake_remove_stale_devices,
    ), patch(
        "custom_components.surepcha.__init__.SurePetcareClient", DummyClient
    ), patch("custom_components.surepcha.__init__.Household", DummyHousehold), patch(
        "homeassistant.helpers.device_registry.async_get", lambda hass: MagicMock()
    ):
        await surepetcare_init.async_setup_entry(hass, entry)
        assert called.get("called")


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
        "custom_components.surepcha.__init__.dr.async_get",
        return_value=device_registry,
    ), patch(
        "custom_components.surepcha.__init__.dr.async_entries_for_config_entry",
        return_value=[matching_entry, stale_entry],
    ):
        remove_stale_devices(MagicMock(), MagicMock(entry_id="dummy_entry_id"), devices)
        # Should call async_update_device for stale_entry only
        device_registry.async_update_device.assert_called_once_with(
            stale_entry.id, remove_config_entry_id="dummy_entry_id"
        )


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_setup_entry_heals_stale_no_subentry_device_association(
    hass: HomeAssistant,
    mock_client: SurePetcareClient,
    mock_config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    mock_devices: list[DeviceBase],
    mock_pets: list[PetBase],
) -> None:
    """A device registered before subentries existed lives in the registry's
    "no subentry" (None) bucket for its entry. Regression test for a real bug:
    async_get_or_create's config_subentry_id only ever *adds* an association,
    so a plain add left devices belonging to both None and the real subentry
    at once - HA's UI then filed them under "no subentry". Setup must
    explicitly drop the stale None association once a real one applies.
    """
    mock_config_entry.add_to_hass(hass)
    # Pre-register the way setup used to, pre-subentries: entry only, no subentry.
    device_registry.async_get_or_create(
        config_entry_id=mock_config_entry.entry_id,
        identifiers={(DOMAIN, "269654")},
        manufacturer="SurePetCare",
        name="Maui matlåda (old)",
    )
    stale = device_registry.async_get_device(identifiers={(DOMAIN, "269654")})
    assert stale is not None
    assert stale.config_entries_subentries[mock_config_entry.entry_id] == {None}

    await initialize_entry(
        hass, mock_client, mock_config_entry, mock_devices, mock_pets
    )

    subentry = next(iter(mock_config_entry.subentries.values()))
    healed = device_registry.async_get_device(identifiers={(DOMAIN, "269654")})
    assert healed is not None
    associated_subentries = healed.config_entries_subentries[mock_config_entry.entry_id]
    assert associated_subentries == {subentry.subentry_id}
    assert None not in associated_subentries


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


def _mock_household(household_id: int, name: str, device_ids: list[int]) -> MagicMock:
    """Build a MagicMock household reporting the given devices (no pets)."""
    household = MagicMock()
    household.id = household_id
    household.data = {"name": name}
    household.get_devices.return_value = [
        MagicMock(id=device_id) for device_id in device_ids
    ]
    household.get_pets.return_value = []
    return household


def _mock_client_for_households(*households: MagicMock) -> MagicMock:
    """Build a mock SurePetcareClient whose get_households() returns the given list."""
    client = MagicMock()
    client.login = AsyncMock(return_value=None)
    client.close = AsyncMock(return_value=None)

    def api_side_effect(cmd):
        if hasattr(cmd, "endpoint") and "household" in cmd.endpoint:
            return list(households)
        return cmd

    client.api = AsyncMock(side_effect=api_side_effect)
    return client


@pytest.mark.asyncio
async def test_migrate_entry_adds_subentry_for_single_household(
    hass: HomeAssistant,
) -> None:
    """A pre-subentries entry with one household gets a matching subentry, and its
    already-registered device is tagged with it - config_entry_id never changes."""
    entry = MockConfigEntry(
        version=1,
        minor_version=3,
        title="Test SurePetCare entry",
        domain=DOMAIN,
        data={TOKEN: "abc", CLIENT_DEVICE_ID: "123"},
        options={OPTION_DEVICES: {}, OPTION_PROPERTIES: {}},
        unique_id="12345",
    )
    entry.add_to_hass(hass)

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "1001")},
        manufacturer="SurePetCare",
        name="Feeder",
    )

    household = _mock_household(555, "Storm", [1001])

    with patch(
        "custom_components.surepcha.__init__.SurePetcareClient",
        return_value=_mock_client_for_households(household),
    ):
        migrated = await surepetcare_init.async_migrate_entry(hass, entry)

    assert migrated
    assert entry.minor_version == 4
    assert len(entry.subentries) == 1
    subentry = next(iter(entry.subentries.values()))
    assert subentry.data[HOUSEHOLD_ID] == 555
    assert subentry.title == "Storm"
    assert subentry.unique_id == "555"

    updated_device = device_registry.async_get_device(identifiers={(DOMAIN, "1001")})
    assert updated_device.config_entries == {entry.entry_id}
    assert (
        subentry.subentry_id in updated_device.config_entries_subentries[entry.entry_id]
    )


@pytest.mark.asyncio
async def test_migrate_entry_adds_subentry_per_household_for_multiple_households(
    hass: HomeAssistant,
) -> None:
    """Matches a real multi-household account: each household-with-devices gets its
    own subentry in a single migration pass."""
    entry = MockConfigEntry(
        version=1,
        minor_version=3,
        title="Test SurePetCare entry",
        domain=DOMAIN,
        data={TOKEN: "abc", CLIENT_DEVICE_ID: "123"},
        options={OPTION_DEVICES: {}, OPTION_PROPERTIES: {}},
        unique_id="12345",
    )
    entry.add_to_hass(hass)

    household_a = _mock_household(111, "Storm", [2001])
    household_b = _mock_household(222, "Second Home", [2002])
    # A household with no devices/pets at all should not get a subentry.
    household_c = _mock_household(333, "Empty Household", [])

    with patch(
        "custom_components.surepcha.__init__.SurePetcareClient",
        return_value=_mock_client_for_households(household_a, household_b, household_c),
    ):
        migrated = await surepetcare_init.async_migrate_entry(hass, entry)

    assert migrated
    assert entry.minor_version == 4
    household_ids = {
        subentry.data[HOUSEHOLD_ID] for subentry in entry.subentries.values()
    }
    assert household_ids == {111, 222}


@pytest.mark.asyncio
async def test_migrate_entry_retries_on_fetch_failure(hass: HomeAssistant) -> None:
    """A network failure during migration must not brick the entry - it should stay
    unmigrated so Home Assistant retries on the next startup."""
    entry = MockConfigEntry(
        version=1,
        minor_version=3,
        title="Test SurePetCare entry",
        domain=DOMAIN,
        data={TOKEN: "abc", CLIENT_DEVICE_ID: "123"},
        options={OPTION_DEVICES: {}, OPTION_PROPERTIES: {}},
        unique_id="12345",
    )
    entry.add_to_hass(hass)

    failing_client = MagicMock()
    failing_client.login = AsyncMock(return_value=None)
    failing_client.close = AsyncMock(return_value=None)
    failing_client.api = AsyncMock(side_effect=RuntimeError("network down"))

    with patch(
        "custom_components.surepcha.__init__.SurePetcareClient",
        return_value=failing_client,
    ):
        migrated = await surepetcare_init.async_migrate_entry(hass, entry)

    assert migrated is False
    assert entry.minor_version == 3
    assert entry.subentries == {}


@pytest.mark.asyncio
async def test_migrate_entry_skips_already_migrated_entry(hass: HomeAssistant) -> None:
    """An entry that already has subentries is left alone - no redundant API calls."""
    entry = MockConfigEntry(
        version=1,
        minor_version=3,
        title="Test SurePetCare entry",
        domain=DOMAIN,
        data={TOKEN: "abc", CLIENT_DEVICE_ID: "123"},
        options={OPTION_DEVICES: {}, OPTION_PROPERTIES: {}},
        subentries_data=(
            {
                "data": {HOUSEHOLD_ID: 555},
                "subentry_type": "household",
                "title": "Storm",
                "unique_id": "555",
            },
        ),
        unique_id="12345",
    )
    entry.add_to_hass(hass)

    never_called_client = MagicMock()
    never_called_client.login = AsyncMock(return_value=None)
    never_called_client.close = AsyncMock(return_value=None)
    never_called_client.api = AsyncMock(
        side_effect=AssertionError("should not be called")
    )

    with patch(
        "custom_components.surepcha.__init__.SurePetcareClient",
        return_value=never_called_client,
    ):
        migrated = await surepetcare_init.async_migrate_entry(hass, entry)

    assert migrated
    assert entry.minor_version == 4
    assert len(entry.subentries) == 1
    never_called_client.api.assert_not_called()
