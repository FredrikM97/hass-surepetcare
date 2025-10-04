import pytest
from syrupy.assertion import SnapshotAssertion
from homeassistant.core import HomeAssistant
from custom_components.surepcha.const import (
    DEVICE_OPTION,
    DOMAIN,
    CONF_EMAIL,
    CONF_PASSWORD,
    ENTRY_ID,
    LOCATION_INSIDE,
    LOCATION_OUTSIDE,
    NAME,
    OPTION_DEVICES,
    OPTIONS_FINISHED,
    POLLING_SPEED,
    PRODUCT_ID,
    TOKEN,
)
from custom_components.surepcha.config_flow import (
    SurePetCareConfigFlow,
    SurePetCareOptionsFlow,
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


@pytest.mark.asyncio
async def test_options_flow(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="test_entry_id",
        data={TOKEN: "existing_token"},
        options={OPTION_DEVICES: {"444": {NAME: "Test Device", PRODUCT_ID: 6}}},
    )

    with patch("custom_components.surepcha.config_flow.SurePetcareClient", MockClient):
        entry.add_to_hass(hass)
        flow = SurePetCareOptionsFlow(entry)
        """
        hass.data = {
            DOMAIN: {
                entry.entry_id: {
                    "coordinator": {
                        "coordinator_dict": {
                            "Test Device": type(
                                "Coordinator", (), {"data": coordinator_data}
                            )()
                        }
                    }
                }
            }
        }
        """
        flow.hass = hass
        flow._config_entry = entry
        flow.context = {"source": "reconfigure", ENTRY_ID: entry.entry_id}
        # Step 1: Init (should show device selection form)
        result = await flow.async_step_init()
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "init"
        assert DEVICE_OPTION in result["data_schema"].schema
        assert (
            result["data_schema"].schema[DEVICE_OPTION].config["options"][0]["label"]
            == "Test Device (DUAL_SCAN_CONNECT)"
        )

        # Step 2: Select device (should show config form)
        result = await flow.async_step_init({DEVICE_OPTION: "444"})
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "configure_device"
        result1 = await flow.async_step_configure_device()
        assert result1["type"] == FlowResultType.FORM
        assert result1["step_id"] == "configure_device"
        assert POLLING_SPEED in result1["data_schema"].schema
        assert LOCATION_INSIDE in result1["data_schema"].schema.keys()
        assert LOCATION_OUTSIDE in result1["data_schema"].schema.keys()
        result2 = await flow.async_step_configure_device(
            {
                POLLING_SPEED: 200,
                LOCATION_INSIDE: "Kitchen",
                LOCATION_OUTSIDE: "Garden",
            }
        )

        assert result2["type"] == FlowResultType.FORM
        assert result2["step_id"] == "init"
        assert flow._options[OPTION_DEVICES]["444"] == {
            NAME: "Test Device",
            PRODUCT_ID: 6,
            LOCATION_INSIDE: "Kitchen",
            LOCATION_OUTSIDE: "Garden",
            POLLING_SPEED: 200,
        }

        result3 = await flow.async_step_init({OPTIONS_FINISHED: True})
        assert result3["type"] == FlowResultType.CREATE_ENTRY


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
    mock_config_entry, hass: HomeAssistant, snapshot: SnapshotAssertion
):
    """Test the full options flow for device selection and configuration."""
    mock_config_entry.add_to_hass(hass)
    flow = SurePetCareOptionsFlow(mock_config_entry)
    flow.hass = hass

    result = await flow.async_step_init()
    assert result["type"] == "form"
    assert result["step_id"] == "init"

    result2 = await flow.async_step_init({DEVICE_OPTION: "1299453"})
    assert result2["type"] == "form"
    assert result2["step_id"] == "configure_device"

    result3 = await flow.async_step_configure_device(
        {
            LOCATION_INSIDE: "Washington DC",
            LOCATION_OUTSIDE: "Space",
            POLLING_SPEED: 120,
        }
    )
    assert result3["type"] == "form"
    assert result3["step_id"] == "init"

    result4 = await flow.async_step_init({"finished": True})
    assert result4["type"] == "create_entry"
    assert result4 == snapshot
    assert mock_config_entry == snapshot
