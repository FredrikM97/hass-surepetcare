from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
)
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from surepcio import SurePetcareClient
from surepcio.enums import ProductId
from syrupy.assertion import SnapshotAssertion

from custom_components.surepcha.binary_sensor import (
    SurePetCareBinarySensor,
    SurePetCareBinarySensorEntityDescription,
)
from custom_components.surepcha.lock import (
    SurePetCareLock,
    SurePetCareLockEntityDescription,
)
from custom_components.surepcha.switch import (
    SurePetCareSwitch,
    SurePetCareSwitchEntityDescription,
)

from . import initialize_entry
from .support import MockConfigEntry, snapshot_platform


@pytest.mark.parametrize("translation_key", [None, "custom_translation"])
def test_connectivity_availability_uses_device_class(translation_key):
    coordinator = MagicMock(last_update_success=True)
    coordinator.device_errors = {}
    device = MagicMock(id=1, product=ProductId.HUB, available=False)
    description = SurePetCareBinarySensorEntityDescription(
        key="arbitrary_identity",
        translation_key=translation_key,
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
    )
    entity = SurePetCareBinarySensor(coordinator, device, description)
    entity._update_state(False, {})
    assert entity.available
    assert entity.is_on is False
    assert entity.translation_key == (translation_key or description.key)
    assert description.translation_key == translation_key
    coordinator.device_errors[device.id] = TimeoutError("Report failed")
    assert not entity.available
    coordinator.device_errors.clear()
    other = SurePetCareBinarySensor(
        coordinator,
        device,
        SurePetCareBinarySensorEntityDescription(
            key="presence", device_class=BinarySensorDeviceClass.PRESENCE
        ),
    )
    other._update_state(False, {})
    assert not other.available


@pytest.mark.parametrize("expected", [True, False])
@pytest.mark.parametrize(
    "entity_class, description_type, platform, true_state, false_state, getter",
    [
        (
            SurePetCareBinarySensor,
            SurePetCareBinarySensorEntityDescription,
            "binary_sensor",
            "on",
            "off",
            "is_on",
        ),
        (
            SurePetCareSwitch,
            SurePetCareSwitchEntityDescription,
            "switch",
            "on",
            "off",
            "is_on",
        ),
        (
            SurePetCareLock,
            SurePetCareLockEntityDescription,
            "lock",
            "locked",
            "unlocked",
            "is_locked",
        ),
    ],
)
async def test_boolean_platform_restores_state_without_changing_native_reading(
    expected, entity_class, description_type, platform, true_state, false_state, getter
):
    coordinator = MagicMock(last_update_success=True)
    coordinator.device_errors = {}
    device = MagicMock(id=1, product=ProductId.HUB, available=True)
    device.current = None
    description = description_type(
        key="example",
        value="current",
    )
    entity = entity_class(coordinator, device, description)
    entity.async_get_last_state = AsyncMock(
        return_value=State(
            f"{platform}.example", true_state if expected else false_state
        )
    )
    entity.async_on_remove = MagicMock()
    with (
        patch(
            "custom_components.surepcha.entity.CoordinatorEntity.async_added_to_hass",
            new=AsyncMock(),
        ),
    ):
        await entity.async_added_to_hass()
    entity.async_get_last_state.assert_awaited_once()
    assert entity.available
    assert getattr(entity, getter) is expected
    entity.async_write_ha_state = MagicMock()

    device.current = None
    entity._handle_coordinator_update()
    assert getattr(entity, getter) is None
    assert entity.available

    device.current = False
    entity._handle_coordinator_update()
    assert getattr(entity, getter) is False
    device.current = 0
    entity._handle_coordinator_update()
    assert getattr(entity, getter) is False
    device.current = True
    entity._handle_coordinator_update()
    assert getattr(entity, getter) is True
    assert entity.available


@patch("custom_components.surepcha.PLATFORMS", [Platform.BINARY_SENSOR])
@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("entity_registry_enabled_default")
@pytest.mark.asyncio
async def test_platform_setup_and_discovery(
    hass: HomeAssistant,
    mock_client: SurePetcareClient,
    mock_config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    mock_devices,
    mock_pets,
) -> None:
    await initialize_entry(
        hass, mock_client, mock_config_entry, mock_devices, mock_pets
    )
    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


@patch("custom_components.surepcha.PLATFORMS", [Platform.BINARY_SENSOR])
@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("entity_registry_enabled_default")
@pytest.mark.asyncio
async def test_platform_setup_and_discovery_missing_entities(
    hass: HomeAssistant,
    mock_client: SurePetcareClient,
    mock_config_entry_missing_entities: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    mock_devices,
    mock_pets,
) -> None:
    await initialize_entry(
        hass, mock_client, mock_config_entry_missing_entities, mock_devices, mock_pets
    )
    await snapshot_platform(
        hass, entity_registry, snapshot, mock_config_entry_missing_entities.entry_id
    )
