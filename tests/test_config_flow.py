import pytest
from unittest.mock import patch
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from custom_components.surepetcare.config_flow import SurePetCareConfigFlow
from custom_components.surepetcare.const import DOMAIN
from surepcio import Household

from custom_components.surepetcare.config_flow import SurePetCareOptionsFlow


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

    async def login(self, email, password):
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
    with patch(
        "custom_components.surepetcare.config_flow.SurePetcareClient", MockClient
    ):
        result = await flow.async_step_user(
            {"email": "test@example.com", "password": "password123"}
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY


@pytest.mark.asyncio
async def test_options_flow(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="test_entry_id",
        data={
            "token": "existing_token",
            "entities": {"444": {"name": "Test Device", "product_id": 6}},
        },
    )

    with patch(
        "custom_components.surepetcare.config_flow.SurePetcareClient", MockClient
    ):
        entry.add_to_hass(hass)
        flow = SurePetCareOptionsFlow(entry)
        # Mock coordinator data for the device
        coordinator_data = type(
            "Device", (), {"id": "444", "name": "Test Device", "product_id": 6}
        )()
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
        flow.hass = hass
        flow._config_entry = entry
        flow.context = {"source": "reconfigure", "entry_id": entry.entry_id}
        # Step 1: Init (should show device selection form)
        result = await flow.async_step_init()
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "init"
        assert "device_option" in result["data_schema"].schema
        assert (
            result["data_schema"].schema["device_option"].config["options"][0]["label"]
            == "Test Device (DUAL_SCAN_CONNECT)"
        )

        # Step 2: Select device (should show config form)
        result = await flow.async_step_init({"device_option": "444"})
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "configure_device"
        result1 = await flow.async_step_configure_device()
        assert result1["type"] == FlowResultType.FORM
        assert result1["step_id"] == "configure_device"
        assert "polling_speed" in result1["data_schema"].schema
        assert "location_inside" in result1["data_schema"].schema.keys()
        assert "location_outside" in result1["data_schema"].schema.keys()
        result2 = await flow.async_step_configure_device(
            {
                "polling_speed": 200,
                "location_inside": "Kitchen",
                "location_outside": "Garden",
            }
        )

        assert result2["type"] == FlowResultType.FORM
        assert result2["step_id"] == "init"
        assert flow._options["444"] == {
            "location_inside": "Kitchen",
            "location_outside": "Garden",
            "polling_speed": 200,
        }

        result3 = await flow.async_step_init({"finished": True})
        assert result3["type"] == FlowResultType.CREATE_ENTRY
