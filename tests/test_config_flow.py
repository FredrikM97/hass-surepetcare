import pytest
from syrupy.assertion import SnapshotAssertion
from homeassistant.core import HomeAssistant

from custom_components.surepcha import async_migrate_entry

from homeassistant.helpers.area_registry import async_get as async_get_area_registry


from custom_components.surepcha.const import (
    CLIENT_DEVICE_ID,
    DOMAIN,
    CONF_EMAIL,
    CONF_PASSWORD,
    ENTRY_ID,
    LOCATION_INSIDE,
    LOCATION_OUTSIDE,
    MANUAL_PROPERTIES,
    NAME,
    OPTION_DEVICES,
    OPTION_PROPERTIES,
    POLLING_SPEED,
    PRODUCT_ID,
    TOKEN,
)
from custom_components.surepcha.config_flow import (
    SurePetCareConfigFlow,
    SurePetCareOptionsFlow,
    _device_picker_options,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry

from unittest.mock import patch
from homeassistant.data_entry_flow import FlowResultType
from surepcio import Household


class MockDevice:
    def __init__(self, device_id="123", name="Test Device", product_id=None):
        self.id = device_id
        self.name = name
        self.product_id = product_id


class MockClient:
    def __init__(
        self, login_success=True, token="test_token", device_id="test_device_id"
    ):
        self.token = token if login_success else None
        self.device_id = device_id
        self._login_success = login_success

    async def login(
        self, email: str = None, password: str = None, token=None, device_id: str = None
    ):
        return self._login_success

    async def api(self, command):
        if "household" in command.endpoint:
            return [Household({"id": 1})]
        if "device" in command.endpoint:
            return [MockDevice(device_id=444, product_id=10)]
        if "pet" in command.endpoint:
            return [MockDevice(device_id=111, product_id=1)]

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_setup_complete_flow(hass):
    flow = SurePetCareConfigFlow()
    with patch("custom_components.surepcha.config_flow.SurePetcareClient", MockClient):
        result = await flow.async_step_user(
            {"email": "test@example.com", "password": "password123"}
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY


@pytest.mark.usefixtures("mock_surepetcare_login_control", "enable_custom_integrations")
async def test_options_flow(hass: HomeAssistant, mock_config_entry):
    mock_config_entry.add_to_hass(hass)
    flow = SurePetCareOptionsFlow(mock_config_entry)

    area_registry = async_get_area_registry(hass)
    area_registry.async_get_or_create("Kitchen")  # area1
    area_registry.async_get_or_create("Garden")  # area2

    flow.hass = hass
    result = await flow.async_step_init()
    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "init"
    assert result["menu_options"] == ["manual_properties", "devices"]

    result2 = await flow.async_step_manual_properties()
    assert result2["type"] == FlowResultType.FORM
    assert result2["step_id"] == "manual_properties"
    assert LOCATION_INSIDE in result2["data_schema"].schema
    assert LOCATION_OUTSIDE in result2["data_schema"].schema

    result3 = await flow.async_step_manual_properties(
        {
            LOCATION_INSIDE: "Kitchen",
            LOCATION_OUTSIDE: "Garden",
        }
    )

    assert result3["type"] == FlowResultType.CREATE_ENTRY
    assert flow._options[OPTION_PROPERTIES][MANUAL_PROPERTIES] == {
        LOCATION_INSIDE: "Kitchen",
        LOCATION_OUTSIDE: "Garden",
    }

    flow = SurePetCareOptionsFlow(mock_config_entry)
    flow.hass = hass

    result4 = await flow.async_step_devices()
    assert result4["type"] == FlowResultType.FORM
    assert result4["step_id"] == "devices"
    device_sections = dict(
        _device_picker_options(mock_config_entry.options[OPTION_DEVICES])
    )
    assert device_sections["1299453"] in result4["data_schema"].schema
    assert device_sections["269654"] in result4["data_schema"].schema
    assert device_sections["727608"] in result4["data_schema"].schema

    result5 = await flow.async_step_devices(
        {
            device_sections["1299453"]: {
                POLLING_SPEED: 200,
                LOCATION_INSIDE: "Kitchen",
                LOCATION_OUTSIDE: "Garden",
            },
            device_sections["269654"]: {
                POLLING_SPEED: 300,
            },
        }
    )

    assert result5["type"] == FlowResultType.CREATE_ENTRY
    assert flow._options[OPTION_DEVICES]["1299453"] == {
        NAME: "DualScanConnect door",
        PRODUCT_ID: 6,
        LOCATION_INSIDE: "Kitchen",
        LOCATION_OUTSIDE: "Garden",
        POLLING_SPEED: 200,
    }
    assert flow._options[OPTION_DEVICES]["269654"] == {
        NAME: "Feeder",
        PRODUCT_ID: 4,
        POLLING_SPEED: 300,
    }


@pytest.mark.usefixtures("mock_surepetcare_login_control")
@pytest.mark.usefixtures("enable_custom_integrations")
async def test_user_flow(
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
) -> None:
    """Test the expected path user flow from start to finish."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
    )

    assert result.get("type") is FlowResultType.FORM
    assert result.get("step_id") == "user"

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_EMAIL: "test@example.com", CONF_PASSWORD: "password123"},
    )

    assert result2.get("type") is FlowResultType.CREATE_ENTRY

    assert result2 == snapshot


@pytest.mark.usefixtures("mock_surepetcare_login_control", "enable_custom_integrations")
async def test_reconfiguration_flow(
    hass: HomeAssistant, mock_config_entry, snapshot: SnapshotAssertion
):
    """Test the reconfiguration step updates entities correctly."""

    original_devices = dict(mock_config_entry.options[OPTION_DEVICES])

    mock_config_entry.add_to_hass(hass)
    flow = SurePetCareConfigFlow()
    flow.hass = hass
    flow._config_entry = mock_config_entry
    flow.context = {ENTRY_ID: mock_config_entry.entry_id}
    result = await flow.async_step_reconfigure()

    new_devices = flow._config_entry.options[OPTION_DEVICES]

    diff_keys = set(original_devices.keys()) ^ set(new_devices.keys())

    assert result.get("type") is FlowResultType.ABORT
    assert result.get("reason") == "entities_reconfigured"

    assert diff_keys or original_devices != new_devices
    assert mock_config_entry == snapshot


@pytest.mark.usefixtures("mock_surepetcare_login_control", "enable_custom_integrations")
async def test_options_flow_full(
    mock_config_entry,
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
):
    """Test the full options flow for device selection and configuration."""
    mock_config_entry.add_to_hass(hass)
    flow = SurePetCareOptionsFlow(mock_config_entry)

    area_registry = async_get_area_registry(hass)
    area_registry.async_get_or_create("Kitchen")  # area1
    area_registry.async_get_or_create("Garden")  # area2

    flow.hass = hass
    result = await flow.async_step_init()
    assert result["type"] == "menu"
    assert result["step_id"] == "init"
    assert result["menu_options"] == ["manual_properties", "devices"]

    assert helper_fetch_area_options(area_registry) == [
        {"value": "kitchen", "label": "Kitchen"},
        {"value": "garden", "label": "Garden"},
    ]

    result2 = await flow.async_step_devices()
    assert result2["type"] == "form"
    assert result2["step_id"] == "devices"

    device_sections = dict(
        _device_picker_options(mock_config_entry.options[OPTION_DEVICES])
    )

    result3 = await flow.async_step_devices(
        {
            device_sections["1299453"]: {
                LOCATION_INSIDE: "Kitchen",
                LOCATION_OUTSIDE: "Garden",
                POLLING_SPEED: 120,
            }
        }
    )

    assert result3["type"] == "create_entry"
    assert result3 == snapshot
    assert mock_config_entry == snapshot


@pytest.mark.asyncio
async def test_async_migrate_entry_adds_manual_properties(
    hass: HomeAssistant, snapshot: SnapshotAssertion
):
    # Simulate an old config entry with legacy manual properties at top level.
    options = {
        OPTION_DEVICES: {
            "12345": {
                NAME: "Test Device",
                PRODUCT_ID: 1,
            }
        },
        MANUAL_PROPERTIES: {
            LOCATION_INSIDE: "Home",
            LOCATION_OUTSIDE: "Away",
        },
    }
    entry = MockConfigEntry(
        version=1,
        minor_version=1,
        title="Test SurePetCare entry",
        domain=DOMAIN,
        data={TOKEN: "abc", CLIENT_DEVICE_ID: "123"},
        options=options,
        unique_id="12345",
    )
    entry.add_to_hass(hass)

    migrated = await async_migrate_entry(hass, entry)
    assert migrated
    assert MANUAL_PROPERTIES not in entry.options
    assert entry.minor_version == 2
    assert entry.version == 1
    assert OPTION_PROPERTIES in entry.options
    assert entry.options[OPTION_PROPERTIES][MANUAL_PROPERTIES] == {
        LOCATION_INSIDE: "Home",
        LOCATION_OUTSIDE: "Away",
    }
    assert entry == snapshot


def helper_fetch_area_options(area_registry):
    return [
        {"value": area.id, "label": area.name} for area in area_registry.areas.values()
    ]
