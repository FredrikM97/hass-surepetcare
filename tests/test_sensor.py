from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from surepcio import TimelineEvent
from surepcio.enums import DoorDirection, ProductId, TimelineEventType
from surepcio.timeline import (
    MovementResource,
    TimelineEntityInfo,
    WeightFrame,
    WeightResource,
)
from syrupy.assertion import SnapshotAssertion

from custom_components.surepcha.const import (
    DOMAIN,
    LOCATION_INSIDE,
    LOCATION_OUTSIDE,
    MANUAL_PROPERTIES,
    NAME,
    OPTION_DEVICES,
    OPTION_PROPERTIES,
)
from custom_components.surepcha.sensor import (
    SurePetCareSensor,
    SurePetCareSensorEntityDescription,
)

from . import initialize_entry
from .support import MockConfigEntry, snapshot_platform


def test_sensor_presentation_uses_descriptor_not_identity(hass):
    coordinator = MagicMock(last_update_success=True)
    device = MagicMock(id=1, product=ProductId.HUB)
    display = MagicMock(return_value="Presented value")
    descriptor = SurePetCareSensorEntityDescription(
        key="arbitrary",
        format_value=display,
        picture=lambda device: device.photo,
    )
    entity = SurePetCareSensor(coordinator, device, descriptor)
    entity.hass = hass
    assert entity.entity_description is descriptor
    entity._set_value(12)
    assert entity.native_value == "Presented value"
    display.assert_called_once_with(entity)
    assert entity.entity_picture == device.photo
    entity._set_value(None)
    assert entity.native_value is None
    assert display.call_count == 1


@patch("custom_components.surepcha.PLATFORMS", [Platform.SENSOR])
@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("entity_registry_enabled_default")
@pytest.mark.asyncio
async def test_platform_setup_and_discovery(
    hass: HomeAssistant,
    mock_client,
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


@patch("custom_components.surepcha.PLATFORMS", [Platform.SENSOR])
@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("entity_registry_enabled_default")
@pytest.mark.asyncio
async def test_platform_setup_and_discovery_missing_entities(
    hass: HomeAssistant,
    mock_client,
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


@patch("custom_components.surepcha.PLATFORMS", [Platform.SENSOR])
@pytest.mark.usefixtures("enable_custom_integrations")
async def test_poseidon_fill_percent_uses_report_not_timeline_weight(
    hass, mock_client, mock_config_entry, mock_devices, mock_pets, entity_registry
):
    await initialize_entry(
        hass, mock_client, mock_config_entry, mock_devices, mock_pets, history=[]
    )
    device = next(
        device
        for device in mock_devices
        if device.product == ProductId.POSEIDON_CONNECT
    )
    coordinator = mock_config_entry.runtime_data.coordinator
    entity_id = entity_registry.async_get_entity_id(
        "sensor", DOMAIN, f"{device.id}-fill_percent"
    )
    assert float(hass.states.get(entity_id).state) == 91
    coordinator._publish_timeline(
        TimelineEvent(
            id=2000,
            type=TimelineEventType.POSEIDON_WEIGHT_CHANGED,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            weights=[
                WeightResource(
                    device_id=device.id,
                    frames=[WeightFrame(index=0, current_weight=500)],
                )
            ],
        )
    )
    assert float(hass.states.get(entity_id).state) == 91
    for value, expected in ((70, "70"), (0, "0"), (None, "unknown")):
        device.status.bowl_status[0].fill_percent = value
        coordinator.async_update_listeners()
        await hass.async_block_till_done()
        assert hass.states.get(entity_id).state == expected


@patch("custom_components.surepcha.PLATFORMS", [Platform.SENSOR])
@pytest.mark.usefixtures("enable_custom_integrations")
async def test_timeline_tag_attributes_preserve_event_data(
    hass, mock_client, mock_config_entry, mock_devices, mock_pets, entity_registry
):
    await initialize_entry(
        hass, mock_client, mock_config_entry, mock_devices, mock_pets, history=[]
    )
    pet = next(pet for pet in mock_pets if pet.id == 532070)
    coordinator = mock_config_entry.runtime_data.coordinator
    entity_id = entity_registry.async_get_entity_id(
        "sensor", DOMAIN, f"{pet.id}-position"
    )
    for index, tag_id in enumerate((pet.tag, None), start=2000):
        event = TimelineEvent(
            id=index,
            type=TimelineEventType.MOVEMENT,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            pets=[TimelineEntityInfo(id=pet.id)],
            movements=[
                MovementResource(
                    device_id=695379,
                    tag_id=tag_id,
                    direction=DoorDirection.ENTERED,
                )
            ],
        )
        coordinator._publish_timeline(event)
        assert hass.states.get(entity_id).attributes["tag_id"] == tag_id
        assert event.movements[0].tag_id == tag_id


@patch("custom_components.surepcha.PLATFORMS", [Platform.SENSOR])
@pytest.mark.usefixtures(
    "enable_custom_integrations", "entity_registry_enabled_default"
)
async def test_timeline_labels_are_ha_owned_and_resolved_without_new_events(
    hass,
    mock_client,
    mock_config_entry,
    entity_registry,
    mock_devices,
    mock_pets,
    snapshot,
):
    await initialize_entry(
        hass, mock_client, mock_config_entry, mock_devices, mock_pets, history=[]
    )
    coordinator = mock_config_entry.runtime_data.coordinator
    pet = mock_pets[0]
    event = TimelineEvent(
        id=1,
        type=TimelineEventType.MOVEMENT,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        pets=[TimelineEntityInfo(id=pet.id)],
        movements=[
            MovementResource(device_id=1299453, direction=DoorDirection.ENTERED)
        ],
    )
    coordinator._publish_timeline(event)

    async def capture(label):
        coordinator.async_update_listeners()
        await hass.async_block_till_done()
        states = {}
        for code in ("position", "last_activity"):
            entity_id = entity_registry.async_get_entity_id(
                "sensor", DOMAIN, f"{pet.id}-{code}"
            )
            if entity_id is None:
                pytest.fail(f"Missing sensor for {code}")
            states[code] = hass.states.get(entity_id)
        assert states == snapshot(name=label)

    await capture("device-overrides")
    manual = {
        OPTION_PROPERTIES: {
            MANUAL_PROPERTIES: {LOCATION_INSIDE: "House", LOCATION_OUTSIDE: "Yard"}
        }
    }
    hass.config_entries.async_update_entry(
        mock_config_entry,
        options={
            **manual,
            OPTION_DEVICES: {
                "1299453": {NAME: "Renamed flap", LOCATION_INSIDE: "Kitchen"}
            },
        },
    )
    await capture("renamed-without-event")
    hass.config_entries.async_update_entry(
        mock_config_entry,
        options={**manual, OPTION_DEVICES: {"1299453": {NAME: "Flap"}}},
    )
    await capture("household-fallback")

    other = MockConfigEntry(
        domain=DOMAIN,
        options={
            OPTION_DEVICES: {
                "1299453": {NAME: "Other entry flap", LOCATION_INSIDE: "Hall"}
            }
        },
    )
    other.add_to_hass(hass)
    await capture("current-entry-takes-precedence")
    hass.config_entries.async_update_entry(mock_config_entry, options=manual)
    await capture("cross-entry-labels")

    event.id = 2
    event.movements[0].device_id = 999999
    event.movements[0].direction = DoorDirection.LEFT
    coordinator._publish_timeline(event)
    await capture("unknown-device-outside")
