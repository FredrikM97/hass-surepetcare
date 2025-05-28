import pytest
from unittest.mock import AsyncMock, patch
from surepetcare.enums import ProductId
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant import config_entries
from homeassistant.data_entry_flow import InvalidData
from custom_components.surepetcare.config_flow import DOMAIN
from homeassistant.config_entries import ConfigEntryState


@pytest.fixture
async def mock_surepy():
    with patch(
        "custom_components.surepetcare.config_flow.SurePetcareClient"
    ) as mock_client:
        instance = mock_client.return_value
        instance.login = AsyncMock(return_value=True)
        instance.get_devices = AsyncMock(
            return_value=[
                {
                    "product_id": ProductId.DUAL_SCAN_PET_DOOR.value,
                    "id": 1,
                    "name": "Flap 1",
                },
                {
                    "product_id": ProductId.FEEDER_CONNECT.value,
                    "id": 2,
                    "name": "Feeder 1",
                },
            ]
        )
        instance.token = "dummy-token"
        yield instance


async def test_flow_user_step_no_input(hass: HomeAssistant):
    """Test appropriate error when no input is provided."""
    _result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    with pytest.raises(InvalidData):
        await hass.config_entries.flow.async_configure(
            _result["flow_id"], user_input={}
        )


async def test_user_login_failure(hass: HomeAssistant, mock_surepy):
    with patch(
        "custom_components.surepetcare.config_flow.SurePetcareClient"
    ) as mock_client:
        instance = mock_client.return_value
        instance.login = AsyncMock(return_value=False)

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"email": "baduser@example.com", "password": "wrongpass"},
        )

        assert result["type"] == FlowResultType.FORM
        assert result["errors"] == {"base": "auth_failed"}


def test_dual_scan_pet_door_schema_valid():
    from custom_components.surepetcare.device_config_schema import DEVICE_CONFIG_SCHEMAS
    from surepetcare.enums import ProductId

    schema = DEVICE_CONFIG_SCHEMAS[ProductId.DUAL_SCAN_PET_DOOR]["schema"]
    # Valid input
    valid = {"location_inside": "Hall", "location_outside": "Garden"}
    assert schema(valid) == valid
    # Invalid input (missing location_inside)
    import voluptuous as vol

    with pytest.raises(vol.Invalid):
        schema({"location_outside": "Garden"})
    # Invalid input (missing location_outside)
    with pytest.raises(vol.Invalid):
        schema({"location_inside": "Hall"})


async def test_device_subentry_flow(hass: HomeAssistant, mock_surepy):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"email": "user@example.com", "password": "test1234"},
    )

    entry: config_entries.ConfigEntry = result.get("result")

    subentry_result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "device"), context={"source": "user"}
    )
    assert subentry_result["type"] == "form"
    product_id_field = subentry_result["data_schema"].schema["product_id"].container
    product_id = next(iter(product_id_field))
    subentry_result = await hass.config_entries.subentries.async_configure(
        subentry_result["flow_id"], user_input={"product_id": product_id}
    )
    assert subentry_result["type"] == "form"
    user_input = {
        "device_1": {"location_inside": "Living Room", "location_outside": "Garden"}
    }
    subentry_result = await hass.config_entries.subentries.async_configure(
        subentry_result["flow_id"], user_input=user_input
    )
    assert subentry_result["type"] == "create_entry"
    assert "devices" in subentry_result["data"]
    assert subentry_result["data"]["product_id"] == product_id
    devices = subentry_result["data"]["devices"]
    assert devices["device_1"]["location_outside"] == "Garden"
    assert devices["device_1"]["location_inside"] == "Living Room"


async def test_entities_created_for_devices(hass: HomeAssistant, mock_surepy):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"email": "user@example.com", "password": "test1234"},
    )

    entry: config_entries.ConfigEntry = result.get("result")

    subentry_result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "device"), context={"source": "user"}
    )
    assert subentry_result["type"] == "form"
    product_id_field = subentry_result["data_schema"].schema["product_id"].container
    product_id = next(iter(product_id_field))
    subentry_result = await hass.config_entries.subentries.async_configure(
        subentry_result["flow_id"], user_input={"product_id": product_id}
    )
    assert subentry_result["type"] == "form"
    user_input = {"1": {"location_inside": "Living Room", "location_outside": "Garden"}}
    subentry_result = await hass.config_entries.subentries.async_configure(
        subentry_result["flow_id"], user_input=user_input
    )

    entry = hass.config_entries.async_get_entry(result["result"].entry_id)
    assert entry.state == ConfigEntryState.LOADED
    await hass.async_block_till_done()

    assert hass.states.get("sensor.flap_1_location") is not None
    assert hass.states.get("sensor.feeder_1_last_fed") is not None

    flap_sensor = hass.states.get("sensor.flap_1_location")
    assert flap_sensor.state is not None  # or check for a specific value
    # assert flap_sensor.attributes["some_attribute"] == expected_value
