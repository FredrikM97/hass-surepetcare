"""Tests for timeline-event driven pet position (presence, position switch/sensor)."""

from unittest.mock import patch

import pytest
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from surepcio.enums import PetLocation

from custom_components.surepcha.const import EVENT_TIMELINE
from custom_components.surepcha.method_field import FieldContext, MethodField

from . import initialize_entry

PET_ID = 472721
HOUSEHOLD_ID = 222527


def _movement(direction: str, **overrides) -> dict:
    payload = {
        "household_id": HOUSEHOLD_ID,
        "id": 1,
        "type": "MOVEMENT",
        "created_at": "2026-10-11T08:34:57+00:00",
        "pets": [PET_ID],
        "devices": [269654],
        "users": [],
        "data": None,
        "movements": [{"device_id": 269654, "direction": direction, "side": "INSIDE"}],
    }
    payload.update(overrides)
    return payload


@pytest.fixture
async def setup(hass, mock_client, mock_config_entry, mock_devices, mock_pets):
    """Set up the pet platforms and return a helper that finds a pet entity id."""
    registry = er.async_get(hass)
    with patch(
        "custom_components.surepcha.PLATFORMS",
        [Platform.BINARY_SENSOR, Platform.SWITCH, Platform.SENSOR],
    ):
        await initialize_entry(
            hass, mock_client, mock_config_entry, mock_devices, mock_pets
        )

    def entity_id(domain: str, key: str) -> str:
        found = registry.async_get_entity_id(domain, "surepcha", f"{PET_ID}-{key}")
        assert found is not None
        registry.async_update_entity(found, disabled_by=None)
        return found

    return entity_id


async def _fire(hass: HomeAssistant, payload: dict) -> None:
    hass.bus.async_fire(EVENT_TIMELINE, payload)
    await hass.async_block_till_done()


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("entity_registry_enabled_default")
async def test_left_and_entered_update_all_position_entities(hass, setup) -> None:
    presence = setup("binary_sensor", "presence")
    switch = setup("switch", "position")
    assert hass.states.get(presence).state == "on"
    assert hass.states.get(switch).state == "off"

    await _fire(hass, _movement("LEFT"))
    assert hass.states.get(presence).state == "off"
    assert hass.states.get(switch).state == "on"
    assert hass.states.get(presence).attributes["since"] == "2026-10-11 08:34:57+00:00"

    await _fire(
        hass, _movement("ENTERED", id=2, created_at="2026-10-11T08:47:01+00:00")
    )
    assert hass.states.get(presence).state == "on"
    assert hass.states.get(switch).state == "off"


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("entity_registry_enabled_default")
async def test_looked_through_changes_nothing(hass, setup) -> None:
    presence = setup("binary_sensor", "presence")
    before = hass.states.get(presence)

    await _fire(hass, _movement("LOOKED_THROUGH"))

    assert hass.states.get(presence).state == before.state
    assert hass.states.get(presence).attributes == before.attributes


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("entity_registry_enabled_default")
@pytest.mark.parametrize(
    "overrides",
    [
        {"pets": [999]},
        {"household_id": 1},
        {"type": "FEEDING"},
        {"created_at": "2019-01-01T00:00:00+00:00"},
    ],
    ids=["other-pet", "other-household", "other-type", "older-than-position"],
)
async def test_unrelated_or_stale_events_are_ignored(hass, setup, overrides) -> None:
    presence = setup("binary_sensor", "presence")

    await _fire(hass, _movement("LEFT", **overrides))

    assert hass.states.get(presence).state == "on"


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("entity_registry_enabled_default")
async def test_event_for_current_side_keeps_since(hass, setup) -> None:
    presence = setup("binary_sensor", "presence")
    before = hass.states.get(presence).attributes["since"]

    await _fire(hass, _movement("ENTERED", created_at="2026-10-11T08:47:01+00:00"))

    assert hass.states.get(presence).attributes["since"] == before


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("entity_registry_enabled_default")
async def test_polling_no_longer_updates_event_driven_entities(hass, setup) -> None:
    presence = setup("binary_sensor", "presence")
    coordinators = hass.config_entries.async_entries("surepcha")[
        0
    ].runtime_data.device_coordinators
    pet_coordinator = next(c for c in coordinators if c.data.id == PET_ID)

    pet_coordinator.data.status.activity.where = PetLocation.OUTSIDE
    pet_coordinator.async_update_listeners()
    await hass.async_block_till_done()

    assert hass.states.get(presence).state == "on"


def test_apply_event_ignores_fields_that_are_not_event_driven() -> None:
    field = MethodField(path="status.activity.where")
    assert field.is_event_driven is False
    assert field.apply_event(FieldContext(None, {}), {"type": "MOVEMENT"}) is False


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("entity_registry_enabled_default")
async def test_switch_command_updates_all_position_entities(
    hass, setup, mock_client
) -> None:
    """A manual position change (no timeline event) must reach presence too."""
    presence = setup("binary_sensor", "presence")
    switch = setup("switch", "position")
    coordinators = hass.config_entries.async_entries("surepcha")[
        0
    ].runtime_data.device_coordinators
    pet = next(c for c in coordinators if c.data.id == PET_ID).data

    async def server_applies_change(_command):
        pet.status.activity.where = PetLocation.OUTSIDE

    mock_client.api.side_effect = server_applies_change
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": switch}, blocking=True
    )
    await hass.async_block_till_done()

    assert hass.states.get(switch).state == "on"
    assert hass.states.get(presence).state == "off"
