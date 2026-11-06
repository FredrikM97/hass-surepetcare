"""Native entity restoration and live observations."""

import asyncio
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorExtraStoredData
from homeassistant.core import State
from surepcio.enums import ProductId

from custom_components.surepcha.binary_sensor import (
    SurePetCareBinarySensor,
    SurePetCareBinarySensorEntityDescription,
)
from custom_components.surepcha.button import (
    SurePetCareButton,
    SurePetCareButtonEntityDescription,
)
from custom_components.surepcha.const import (
    OPTION_TIMELINE,
    SCAN_INTERVAL,
    TIMELINE_POLLING_SPEED,
)
from custom_components.surepcha.lock import (
    SurePetCareLock,
    SurePetCareLockEntityDescription,
)
from custom_components.surepcha.select import (
    SurePetCareSelect,
    SurePetCareSelectEntityDescription,
)
from custom_components.surepcha.sensor import (
    SurePetCareSensor,
    SurePetCareSensorEntityDescription,
)
from custom_components.surepcha.switch import (
    SurePetCareSwitch,
    SurePetCareSwitchEntityDescription,
)

from . import initialize_entry


@pytest.mark.parametrize(
    ("saved", "attributes", "metadata"),
    [
        ("Saved label", {"detail": "retained"}, {}),
        (
            "0.00523",
            {"unit_of_measurement": "kg"},
            {"device_class": SensorDeviceClass.WEIGHT, "native_unit_of_measurement": "g"},
        ),
        ("0", {"unit_of_measurement": "%"}, {"native_unit_of_measurement": "%"}),
    ],
    ids=["label", "converted-weight", "zero"],
)
async def test_sensor_restores_legacy_state_without_native_data(
    hass, saved, attributes, metadata, snapshot
):
    coordinator = MagicMock(last_update_success=True)
    coordinator.device_errors = {}
    entity = SurePetCareSensor(
        coordinator,
        SimpleNamespace(id=1, product=ProductId.HUB, available=True),
        SurePetCareSensorEntityDescription(key="example", **metadata),
    )
    entity.async_get_last_state = AsyncMock(
        return_value=State("sensor.example", saved, attributes)
    )
    entity.async_get_last_sensor_data = AsyncMock(return_value=None)
    entity.async_on_remove = MagicMock()
    entity.async_write_ha_state = MagicMock()
    with patch(
        "custom_components.surepcha.entity.CoordinatorEntity.async_added_to_hass",
        new=AsyncMock(),
    ):
        await entity.async_added_to_hass()
    entity._handle_coordinator_update()
    assert {
        "value": entity.native_value,
        "attributes": entity.extra_state_attributes,
    } == snapshot


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.parametrize("polling_speed", [None, 120])
async def test_setup_awaits_restore_hook_before_polling(
    hass, mock_client, mock_config_entry, mock_devices, mock_pets, polling_speed
):
    if polling_speed is not None:
        mock_config_entry.add_to_hass(hass)
        hass.config_entries.async_update_entry(
            mock_config_entry,
            options={
                **mock_config_entry.options,
                OPTION_TIMELINE: {TIMELINE_POLLING_SPEED: polling_speed},
            },
        )
    restored = asyncio.Event()
    finish_restore = asyncio.Event()
    added_to_hass = SurePetCareSensor.async_added_to_hass
    target_id = mock_pets[0].id
    captured = {}

    async def added(entity):
        if entity.device.id == target_id and entity.entity_description.key == "feeding":
            captured["entity"] = entity
            restored.set()
            await finish_restore.wait()
        await added_to_hass(entity)

    with patch.object(SurePetCareSensor, "async_added_to_hass", new=added):
        task = hass.async_create_task(
            initialize_entry(
                hass, mock_client, mock_config_entry, mock_devices, mock_pets
            )
        )
        try:
            async with asyncio.timeout(10):
                await restored.wait()
            coordinator = mock_config_entry.runtime_data.coordinator
            assert coordinator.update_interval is None
            assert coordinator._unsub_refresh is None
            assert not any(
                hasattr(call.args[0], "endpoint")
                and "timeline" in call.args[0].endpoint
                for call in mock_client.api.await_args_list
            )
        finally:
            finish_restore.set()
            await task
    assert coordinator.update_interval == timedelta(
        seconds=SCAN_INTERVAL if polling_speed is None else polling_speed
    )
    assert coordinator._unsub_refresh is not None
    assert coordinator.state.seen_id is not None
    assert captured["entity"].native_value == 5.23


@pytest.mark.parametrize(
    "entity_type,description_type,platform,saved_value,saved_state,live_value",
    [
        (
            SurePetCareBinarySensor,
            SurePetCareBinarySensorEntityDescription,
            "binary_sensor",
            False,
            "off",
            False,
        ),
        (
            SurePetCareSwitch,
            SurePetCareSwitchEntityDescription,
            "switch",
            False,
            "off",
            False,
        ),
        (
            SurePetCareLock,
            SurePetCareLockEntityDescription,
            "lock",
            False,
            "unlocked",
            False,
        ),
        (
            SurePetCareSensor,
            SurePetCareSensorEntityDescription,
            "sensor",
            "Saved label",
            "Saved label",
            0,
        ),
    ],
)
async def test_platform_restores_native_state_then_reads_live_observations(
    hass,
    entity_type,
    description_type,
    platform,
    saved_value,
    saved_state,
    live_value,
):
    coordinator = MagicMock(last_update_success=True)
    coordinator.device_errors = {}
    device = SimpleNamespace(
        id=1, product=ProductId.HUB, available=True, current=None
    )
    description = description_type(
        key="example",
        value=lambda entity: entity.device.current,
        **(
            {
                "format_value": lambda entity: (
                    entity._attr_native_value
                    if isinstance(entity._attr_native_value, str)
                    else "Live label"
                )
            }
            if platform == "sensor"
            else {}
        ),
    )
    entity = entity_type(coordinator, device, description)
    entity.async_write_ha_state = MagicMock()
    entity.async_get_last_state = AsyncMock(
        return_value=State(
            f"{platform}.example",
            saved_state,
            {"saved_attribute": "retained"},
        )
    )
    if platform == "sensor":
        entity.async_get_last_sensor_data = AsyncMock(
            return_value=SensorExtraStoredData(saved_value, None)
        )
    entity.async_on_remove = MagicMock()

    with patch(
        "custom_components.surepcha.entity.CoordinatorEntity.async_added_to_hass",
        new=AsyncMock(),
    ):
        await entity.async_added_to_hass()

    entity.async_get_last_state.assert_awaited_once()
    assert entity.available
    if platform == "sensor":
        entity.async_get_last_sensor_data.assert_awaited_once()
        assert entity.native_value == saved_value
    else:
        assert getattr(
            entity,
            {"binary_sensor": "is_on", "switch": "is_on", "lock": "is_locked"}[
                platform
            ],
        ) is False
    assert entity.extra_state_attributes == {"saved_attribute": "retained"}

    device.current = live_value
    entity._handle_coordinator_update()
    if platform == "sensor":
        assert entity.native_value == "Live label"
    else:
        assert getattr(
            entity,
            {"binary_sensor": "is_on", "switch": "is_on", "lock": "is_locked"}[
                platform
            ],
        ) is False
    assert entity.available

    device.current = None
    entity._handle_coordinator_update()
    if platform == "sensor":
        assert entity.native_value is None
    else:
        assert getattr(
            entity,
            {"binary_sensor": "is_on", "switch": "is_on", "lock": "is_locked"}[
                platform
            ],
        ) is None
    assert entity.extra_state_attributes == {}
    assert entity.available


@pytest.mark.parametrize("platform_state", ["unknown", "unavailable"])
async def test_invalid_saved_state_is_not_restored_but_is_still_queried(
    hass, platform_state
):
    coordinator = MagicMock(last_update_success=True)
    coordinator.device_errors = {}
    device = SimpleNamespace(id=1, product=ProductId.HUB, available=True)
    entity = SurePetCareSensor(
        coordinator,
        device,
        SurePetCareSensorEntityDescription(key="example"),
    )
    entity.async_get_last_state = AsyncMock(
        return_value=State("sensor.example", platform_state)
    )
    entity.async_get_last_sensor_data = AsyncMock(
        return_value=SensorExtraStoredData("Saved", None)
    )
    entity.async_on_remove = MagicMock()
    with patch(
        "custom_components.surepcha.entity.CoordinatorEntity.async_added_to_hass",
        new=AsyncMock(),
    ):
        await entity.async_added_to_hass()
    entity.async_get_last_state.assert_awaited_once()
    entity.async_get_last_sensor_data.assert_not_awaited()
    assert entity.native_value is None


@pytest.mark.parametrize(
    "entity_type,description_type",
    [
        (SurePetCareSelect, SurePetCareSelectEntityDescription),
        (SurePetCareButton, SurePetCareButtonEntityDescription),
    ],
)
async def test_command_only_choice_and_action_entities_do_not_restore(
    hass, entity_type, description_type
):
    coordinator = MagicMock(last_update_success=True)
    coordinator.device_errors = {}
    device = SimpleNamespace(id=1, product=ProductId.HUB, available=True)
    entity = entity_type(
        coordinator,
        device,
        description_type(key="example", command=lambda *_: "command"),
    )
    entity.async_get_last_state = AsyncMock(
        return_value=State(f"{entity_type.__name__.lower()}.example", "saved")
    )
    entity.async_on_remove = MagicMock()
    with patch(
        "custom_components.surepcha.entity.CoordinatorEntity.async_added_to_hass",
        new=AsyncMock(),
    ):
        await entity.async_added_to_hass()
    entity.async_get_last_state.assert_not_awaited()
