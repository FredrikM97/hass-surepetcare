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
    HOUSEHOLD_ID,
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

from unittest.mock import AsyncMock, MagicMock, patch
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
            return [Household({"id": 1, "name": "Test Household"})]
        if "device" in command.endpoint:
            return [MockDevice(device_id=444, product_id=10)]
        if "pet" in command.endpoint:
            return [MockDevice(device_id=111, product_id=1)]

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_setup_complete_flow(hass):
    flow = SurePetCareConfigFlow()
    flow.hass = hass
    with (
        patch("custom_components.surepcha.config_flow.SurePetcareClient", MockClient),
        patch.object(flow, "async_set_unique_id", return_value=None),
        patch.object(flow, "_abort_if_unique_id_configured"),
    ):
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


@pytest.mark.asyncio
async def test_user_step_skips_fetch_when_auth_has_errors() -> None:
    """A failed login must not attempt to fetch entities with an unauthenticated
    client - regression test for the session-leak fix's auth-failure guard."""
    flow = SurePetCareConfigFlow()

    client = MagicMock()
    client.close = AsyncMock()

    with (
        patch.object(
            flow,
            "_authenticate",
            AsyncMock(return_value=(client, {"base": "auth_failed"})),
        ),
        patch.object(flow, "_fetch_all_household_data", AsyncMock()) as fetch_mock,
    ):
        result = await flow.async_step_user(
            {"email": "test@example.com", "password": "bad-password"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "auth_failed"
    fetch_mock.assert_not_awaited()
    client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_user_step_calls_fetch_when_auth_ok(hass: HomeAssistant) -> None:
    """A successful login still fetches entities and creates the entry."""
    flow = SurePetCareConfigFlow()
    flow.hass = hass

    client = MagicMock()
    client.token = "tok"
    client.device_id = "dev"
    client.close = AsyncMock()

    mock_household = MagicMock(id=123, data={"name": "Test Household"})

    with (
        patch.object(flow, "_authenticate", AsyncMock(return_value=(client, {}))),
        patch.object(
            flow,
            "_fetch_all_household_data",
            AsyncMock(
                return_value=[
                    (mock_household, {"123": {"name": "Device", "product_id": 4}})
                ]
            ),
        ) as fetch_mock,
        patch.object(flow, "_trigger_discovery_flows"),
        patch.object(flow, "async_set_unique_id", AsyncMock()),
        patch.object(flow, "_abort_if_unique_id_configured"),
    ):
        result = await flow.async_step_user(
            {"email": "test@example.com", "password": "good-password"}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    fetch_mock.assert_awaited_once_with(client)
    client.close.assert_awaited_once()


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
    assert entry.minor_version == 4
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


@pytest.mark.asyncio
async def test_user_step_no_devices_found() -> None:
    """async_step_user shows an error when fetch returns no devices."""
    flow = SurePetCareConfigFlow()
    client = MagicMock()
    client.close = AsyncMock()

    with (
        patch.object(flow, "_authenticate", AsyncMock(return_value=(client, {}))),
        patch.object(flow, "_fetch_all_household_data", AsyncMock(return_value=[])),
    ):
        result = await flow.async_step_user(
            {"email": "test@example.com", "password": "pass"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "no_devices_or_pet_found"
    client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_user_step_aborts_when_all_households_already_configured(
    hass: HomeAssistant,
) -> None:
    """async_step_user aborts when every returned household already has a config entry."""
    flow = SurePetCareConfigFlow()
    flow.hass = hass
    client = MagicMock()
    client.token = "tok"
    client.device_id = "dev"
    client.close = AsyncMock()
    mock_household = MagicMock(id=999)

    existing_entry = MagicMock()
    with (
        patch.object(flow, "_authenticate", AsyncMock(return_value=(client, {}))),
        patch.object(
            flow,
            "_fetch_all_household_data",
            AsyncMock(return_value=[(mock_household, {})]),
        ),
        patch.object(
            hass.config_entries,
            "async_entry_for_domain_unique_id",
            return_value=existing_entry,
        ),
    ):
        result = await flow.async_step_user(
            {"email": "test@example.com", "password": "pass"}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_integration_discovery_step(hass) -> None:
    """async_step_integration_discovery creates an entry for the discovered household."""
    flow = SurePetCareConfigFlow()
    flow.hass = hass

    with (
        patch.object(flow, "async_set_unique_id", AsyncMock()),
        patch.object(flow, "_abort_if_unique_id_configured"),
    ):
        result = await flow.async_step_integration_discovery(
            {
                HOUSEHOLD_ID: 99,
                NAME: "Second Home",
                TOKEN: "tok",
                CLIENT_DEVICE_ID: "dev",
                OPTION_DEVICES: {"1": {NAME: "Cat flap", PRODUCT_ID: 6}},
            }
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Second Home"
    assert result["data"][HOUSEHOLD_ID] == 99


@pytest.mark.asyncio
async def test_async_fetch_entities_no_devices() -> None:
    """_async_fetch_entities_for_household returns empty dicts when no devices/pets exist."""
    flow = SurePetCareConfigFlow()
    client = MagicMock()
    client.api = AsyncMock(return_value=[])
    household = MagicMock()

    entity_info, errors = await flow._async_fetch_entities_for_household(
        client, household
    )

    assert entity_info == {}
    assert errors == {}


@pytest.mark.asyncio
async def test_fetch_entity_info_for_id_not_found() -> None:
    """_fetch_entity_info_for_id returns None when the household_id is not present."""
    flow = SurePetCareConfigFlow()
    mock_household = MagicMock()
    mock_household.id = 1
    client = MagicMock()
    client.api = AsyncMock(return_value=[mock_household])

    result = await flow._fetch_entity_info_for_id(client, household_id=999)

    assert result is None


@pytest.mark.asyncio
async def test_reconfigure_auth_failure(hass) -> None:
    """async_step_reconfigure aborts with auth_failed when credentials are rejected."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={TOKEN: "old_tok", CLIENT_DEVICE_ID: "dev", HOUSEHOLD_ID: 1},
        options={OPTION_DEVICES: {}, OPTION_PROPERTIES: {}},
        unique_id="1",
    )
    entry.add_to_hass(hass)

    flow = SurePetCareConfigFlow()
    flow.hass = hass
    flow.context = {ENTRY_ID: entry.entry_id}
    client = MagicMock()
    client.close = AsyncMock()

    with patch.object(
        flow,
        "_authenticate",
        AsyncMock(return_value=(client, {"base": "auth_failed"})),
    ):
        result = await flow.async_step_reconfigure()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "auth_failed"
    client.close.assert_awaited_once()


@pytest.mark.usefixtures("mock_surepetcare_login_control", "enable_custom_integrations")
async def test_reconfigure_legacy_no_household_id(hass: HomeAssistant) -> None:
    """async_step_reconfigure migrates a legacy entry that has no HOUSEHOLD_ID."""
    legacy_entry = MockConfigEntry(
        domain=DOMAIN,
        data={TOKEN: "tok", CLIENT_DEVICE_ID: "dev"},  # no HOUSEHOLD_ID
        options={OPTION_DEVICES: {}, OPTION_PROPERTIES: {}},
        unique_id="legacy",
    )
    legacy_entry.add_to_hass(hass)

    flow = SurePetCareConfigFlow()
    flow.hass = hass
    flow.context = {ENTRY_ID: legacy_entry.entry_id}

    result = await flow.async_step_reconfigure()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "entities_reconfigured"
    assert legacy_entry.data[HOUSEHOLD_ID] == 12345


@pytest.mark.asyncio
async def test_authenticate_cannot_connect() -> None:
    """_authenticate returns cannot_connect when login succeeds but token is absent."""
    flow = SurePetCareConfigFlow()
    client = MagicMock()
    client.token = None
    client.login = AsyncMock(return_value=True)

    with patch(
        "custom_components.surepcha.config_flow.SurePetcareClient",
        return_value=client,
    ):
        _, errors = await flow._authenticate(email="a@b.com", password="pw")

    assert errors["base"] == "cannot_connect"


@pytest.mark.asyncio
async def test_reauth_step_delegates_to_confirm(hass) -> None:
    """async_step_reauth delegates directly to async_step_reauth_confirm."""
    flow = SurePetCareConfigFlow()
    flow.hass = hass
    confirm_mock = AsyncMock(return_value={"type": "form"})

    with patch.object(flow, "async_step_reauth_confirm", confirm_mock):
        await flow.async_step_reauth({})

    confirm_mock.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_reauth_confirm_shows_form(hass) -> None:
    """async_step_reauth_confirm with no input shows the reauth form."""
    flow = SurePetCareConfigFlow()
    flow.hass = hass
    reauth_entry = MockConfigEntry(
        domain=DOMAIN,
        data={TOKEN: "tok", CLIENT_DEVICE_ID: "dev", CONF_EMAIL: "a@b.com"},
        options={OPTION_DEVICES: {}, OPTION_PROPERTIES: {}},
    )
    reauth_entry.add_to_hass(hass)

    with patch.object(flow, "_get_reauth_entry", return_value=reauth_entry):
        result = await flow.async_step_reauth_confirm()

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"


@pytest.mark.asyncio
async def test_reauth_confirm_success(hass) -> None:
    """async_step_reauth_confirm with valid credentials calls update_reload_and_abort."""
    flow = SurePetCareConfigFlow()
    flow.hass = hass
    reauth_entry = MockConfigEntry(
        domain=DOMAIN,
        data={TOKEN: "old", CLIENT_DEVICE_ID: "dev", CONF_EMAIL: "a@b.com"},
        options={OPTION_DEVICES: {}, OPTION_PROPERTIES: {}},
    )
    reauth_entry.add_to_hass(hass)

    client = MagicMock()
    client.token = "new_token"
    client.device_id = "new_dev"
    client.close = AsyncMock()

    with (
        patch.object(flow, "_get_reauth_entry", return_value=reauth_entry),
        patch.object(flow, "_authenticate", AsyncMock(return_value=(client, {}))),
        patch.object(
            flow,
            "async_update_reload_and_abort",
            return_value={"type": "abort", "reason": "reauth_successful"},
        ) as mock_abort,
    ):
        result = await flow.async_step_reauth_confirm({CONF_PASSWORD: "new_pass"})

    assert result["reason"] == "reauth_successful"
    mock_abort.assert_called_once()
    client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_options_init_aborts_when_no_devices(
    hass: HomeAssistant, mock_config_entry_missing_entities
) -> None:
    """Options init aborts with no_devices_or_pet_found when OPTION_DEVICES is empty."""
    mock_config_entry_missing_entities.add_to_hass(hass)
    flow = SurePetCareOptionsFlow(mock_config_entry_missing_entities)
    flow.hass = hass

    result = await flow.async_step_init()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_or_pet_found"


def test_device_picker_unknown_product_id() -> None:
    """_device_picker_options handles unrecognized and None product_id values gracefully."""
    devices = {
        "42": {NAME: "Mystery Device", PRODUCT_ID: 9999},
        "99": {NAME: "Null Device", PRODUCT_ID: None},
    }
    labels = {device_id: label for device_id, label in _device_picker_options(devices)}

    assert "9999" in labels["42"]
    assert "Unknown" in labels["99"]


@pytest.mark.asyncio
async def test_trigger_discovery_flows(hass) -> None:
    """_trigger_discovery_flows calls async_create_task for each additional household."""
    flow = SurePetCareConfigFlow()
    flow.hass = hass
    mock_household = MagicMock(id=99)
    mock_household.data = {"name": "Second Home"}

    with patch.object(
        hass.config_entries.flow, "async_init", AsyncMock(return_value=None)
    ):
        flow._trigger_discovery_flows(
            "tok", "dev", [(mock_household, {"1": {NAME: "Cat flap"}})]
        )
        await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_authenticate_login_failed() -> None:
    """_authenticate returns auth_failed when the login call returns False."""
    flow = SurePetCareConfigFlow()
    client = MagicMock()
    client.token = "tok"
    client.login = AsyncMock(return_value=False)

    with patch(
        "custom_components.surepcha.config_flow.SurePetcareClient",
        return_value=client,
    ):
        _, errors = await flow._authenticate(email="a@b.com", password="wrong")

    assert errors["base"] == "auth_failed"


def test_async_get_options_flow(mock_config_entry) -> None:
    """async_get_options_flow returns a SurePetCareOptionsFlow instance."""
    result = SurePetCareConfigFlow.async_get_options_flow(mock_config_entry)
    assert isinstance(result, SurePetCareOptionsFlow)
