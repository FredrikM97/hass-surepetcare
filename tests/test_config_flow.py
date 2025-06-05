import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from custom_components.surepetcare.config_flow import SurePetCareConfigFlow, SurePetCareDeviceSubentryFlowHandler
from homeassistant.data_entry_flow import FlowResultType
from tests.conftest import make_dummy_handler, stop_dummy_handler_patches, DummyClient, DummyFailClient

@pytest.mark.asyncio
async def test_user_login_success_flap_config():
    with patch("custom_components.surepetcare.config_flow.SurePetcareClient", DummyClient):
        flow = SurePetCareConfigFlow()
        flow.client = DummyClient()
        flow.client.token = "token"
        flow.client.device_id = "deviceid"
        flow.client.login = AsyncMock(return_value=True)
        flow.client.close = AsyncMock()
        # Patch _setup_subentry_data to return dummy subentries
        flow._setup_subentry_data = AsyncMock(return_value=[{"title": "Device1", "data": {"id": "1", "name": "Device1", "product_id": "DUAL_SCAN_PET_DOOR"}, "subentry_type": "device"}])
        result = await flow.async_step_user({"email": "a@b.com", "password": "pw"})
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == "SurePetCare Devices"
        assert result["data"]["token"] == "token"

@pytest.mark.asyncio
async def test_user_login_failure():
    with patch("custom_components.surepetcare.config_flow.SurePetcareClient", DummyFailClient):
        flow = SurePetCareConfigFlow()
        result = await flow.async_step_user({"email": "a@b.com", "password": "pw"})
        assert result["type"] == FlowResultType.FORM
        assert result["errors"]["base"] == "auth_failed"

@pytest.mark.asyncio
async def test_device_subentry_configure_user(dummy_entry, dummy_subentry):
    handler = make_dummy_handler(SurePetCareDeviceSubentryFlowHandler, dummy_entry, dummy_subentry)
    try:
        # Test with user_input provided
        result = await handler.async_step_configure_user({"location_inside": "A", "location_outside": "B"})
        assert result["type"] == FlowResultType.CREATE_ENTRY
        # Test with no user_input (should call async_step_select_device)
        async def dummy_select_device():
            return {"type": FlowResultType.FORM}
        handler.async_step_select_device = dummy_select_device
        result = await handler.async_step_configure_user(None)
        assert result["type"] == FlowResultType.FORM
    finally:
        stop_dummy_handler_patches(handler)

@pytest.mark.asyncio
async def test_device_subentry_reconfigure(dummy_entry, dummy_subentry):
    handler = make_dummy_handler(SurePetCareDeviceSubentryFlowHandler, dummy_entry, dummy_subentry)
    try:
        handler._get_entry = MagicMock(return_value=dummy_entry)
        handler._get_reconfigure_subentry = MagicMock(return_value=dummy_subentry)
        # Patch DEVICE_CONFIG_SCHEMAS to provide a schema
        with patch("custom_components.surepetcare.config_flow.DEVICE_CONFIG_SCHEMAS", {"DUAL_SCAN_PET_DOOR": {"schema": {"location_inside": str, "location_outside": str}}}):
            # Test with user_input provided
            with patch.object(handler, 'async_update_and_abort', MagicMock(return_value={"type": FlowResultType.ABORT})) as mock_update:
                result = await handler.async_step_reconfigure({"location_inside": "A", "location_outside": "B"})
                assert result["type"] == FlowResultType.ABORT
                mock_update.assert_called_once()
            # Test with no user_input and schema present
            with patch.object(handler, 'async_show_form', MagicMock(return_value={"type": FlowResultType.FORM})) as mock_show:
                result = await handler.async_step_reconfigure(None)
                assert result["type"] == FlowResultType.FORM
                mock_show.assert_called_once()
            # Test with no user_input and schema is None
            with patch("custom_components.surepetcare.config_flow.DEVICE_CONFIG_SCHEMAS", {"DUAL_SCAN_PET_DOOR": {"schema": None}}):
                result = await handler.async_step_reconfigure(None)
                assert result["type"] == FlowResultType.ABORT
                assert result["reason"] == "no_reconfigure_schema"
    finally:
        stop_dummy_handler_patches(handler)
