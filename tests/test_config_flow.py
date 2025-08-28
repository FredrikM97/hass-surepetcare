import pytest
from unittest.mock import patch
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from custom_components.surepetcare.config_flow import SurePetCareConfigFlow
from custom_components.surepetcare.const import DOMAIN
from surepetcare.household import Household


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
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "select_device"
        assert "device_option" in result["data_schema"].schema
        assert (
            result["data_schema"].schema["device_option"].container[0] == "Test Device"
        )
        result2 = await flow.async_step_select_device({"device_option": "Test Device"})

        assert result2["type"] == FlowResultType.FORM
        assert result2["step_id"] == "configure_device"
        assert "location_inside" in result2["data_schema"].schema.keys()
        assert "location_outside" in result2["data_schema"].schema.keys()
        result3 = await flow.async_step_configure_device(
            {"location_inside": "Kitchen", "location_outside": "Garden"}
        )
        assert result3["step_id"] == "select_device"
        assert flow._device_config == {
            "444": {"location_inside": "Kitchen", "location_outside": "Garden"}
        }
        result4 = await flow.async_step_select_device({"device_option": "Finish setup"})
        assert result4["type"] == FlowResultType.CREATE_ENTRY


@pytest.mark.asyncio
async def test_reconfigure_flow(hass):
    flow = SurePetCareConfigFlow()
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"token": "existing_token"},
        options={"444": {"location_inside": "Kitchen", "location_outside": "Garden"}},
    )
    entry.add_to_hass(hass)
    flow.hass = hass
    with patch(
        "custom_components.surepetcare.config_flow.SurePetcareClient", MockClient
    ):
        coordinator_data = type(
            "Device", (), {"id": 444, "name": "Test Device", "product_id": 10}
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
        flow.context = {"source": "reconfigure", "entry_id": entry.entry_id}

        result = await flow.async_step_reconfigure()
        assert flow._device_config == {
            "444": {"location_inside": "Kitchen", "location_outside": "Garden"}
        }

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "select_device"
        assert "device_option" in result["data_schema"].schema
        assert (
            result["data_schema"].schema["device_option"].container[0] == "Test Device"
        )
        result1 = await flow.async_step_select_device({"device_option": "Test Device"})
        assert result1["type"] == FlowResultType.FORM
        assert result1["step_id"] == "configure_device"
        assert "location_inside" in result1["data_schema"].schema.keys()
        assert "location_outside" in result1["data_schema"].schema.keys()
        result2 = await flow.async_step_configure_device(
            {"location_inside": "Bedroom", "location_outside": "Garden"}
        )
        assert result2["step_id"] == "select_device"
        assert flow._device_config == {
            "444": {"location_inside": "Bedroom", "location_outside": "Garden"}
        }
        result3 = await flow.async_step_select_device({"device_option": "Finish setup"})
        assert result3["type"] == FlowResultType.ABORT
        assert result3["reason"] == "reconfigure_successful"
