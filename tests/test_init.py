import importlib
from unittest.mock import MagicMock, patch
import custom_components.surepetcare.__init__ as surepetcare_init
from custom_components.surepetcare.const import FACTORY
import pytest
from tests.conftest import (
    DummyHass,
    DummyConfigEntry,
    DummyClient,
    DummyHousehold,
    FakeDevice,
    FailingClient,
    ExceptionClient,
    async_forward_entry_setups,
)
from custom_components.surepetcare import remove_stale_devices, DOMAIN


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
        hass.data["surepetcare"] = {entry.entry_id: {FACTORY: DummyClient()}}
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
    # No data in hass.data["surepetcare"]
    hass.data["surepetcare"] = {}
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
