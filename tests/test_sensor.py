from unittest.mock import patch

import pytest
from freezegun import freeze_time
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    snapshot_platform,
)
from syrupy.assertion import SnapshotAssertion

from . import initialize_entry


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
    # feeding_timeline_frames.json's events carry fixed calendar dates,
    # which the feeding sensors filter against "today" - freeze time so
    # this snapshot doesn't drift/expire as real time moves past that date.
    await hass.config.async_set_time_zone("UTC")
    with freeze_time("2026-08-27T12:00:00+00:00"):
        await initialize_entry(
            hass, mock_client, mock_config_entry, mock_devices, mock_pets
        )
        await snapshot_platform(
            hass, entity_registry, snapshot, mock_config_entry.entry_id
        )


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
    await hass.config.async_set_time_zone("UTC")
    with freeze_time("2026-08-27T12:00:00+00:00"):
        await initialize_entry(
            hass,
            mock_client,
            mock_config_entry_missing_entities,
            mock_devices,
            mock_pets,
        )
        await snapshot_platform(
            hass,
            entity_registry,
            snapshot,
            mock_config_entry_missing_entities.entry_id,
        )


@patch("custom_components.surepcha.PLATFORMS", [Platform.SENSOR])
@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.usefixtures("entity_registry_enabled_default")
@pytest.mark.asyncio
async def test_feeding_sensors_reflect_real_timeline_events(
    hass: HomeAssistant,
    mock_client,
    mock_config_entry: MockConfigEntry,
    mock_devices,
    mock_pets,
) -> None:
    """Feeding sensors populate real state/attributes through the actual
    config-entry/entity/coordinator setup, not a mocked client directly
    (that's what test_feeding_timeline.py covers)."""
    await hass.config.async_set_time_zone("UTC")
    with freeze_time("2026-08-27T12:00:00+00:00"):
        await initialize_entry(
            hass, mock_client, mock_config_entry, mock_devices, mock_pets
        )

        # Maui (household 222527): one feeding event, 12g wet + 1g dry.
        maui_feedings = hass.states.get("sensor.maui_feedings_today")
        assert maui_feedings.state == "1"
        assert maui_feedings.attributes["total_grams"] == 13.0

        maui_food = hass.states.get("sensor.maui_food_today")
        assert maui_food.state == "13.0"
        assert maui_food.attributes["total_wet_grams"] == 12.0
        assert maui_food.attributes["total_dry_grams"] == 1.0

        # Ajax (household 245684): one feeding event, 3g wet + 2g dry.
        ajax_feedings = hass.states.get("sensor.ajax_feedings_today")
        assert ajax_feedings.state == "1"

        ajax_food = hass.states.get("sensor.ajax_food_today")
        assert ajax_food.state == "5.0"

        # Household 222527's activity feed: Maui's feeding + a bowl refill,
        # oldest first.
        activity_222527 = hass.states.get(
            "sensor.test_household_222527_household_activity_today"
        )
        assert activity_222527.state == "2"
        assert [
            event["activity_type"] for event in activity_222527.attributes["events"]
        ] == ["bowl_filled", "feeding"]
        assert "472721" in activity_222527.attributes["pet_photos"]  # Maui
        # Regression for the household's own feeder/hub devices: surepcio
        # gives FeederConnect/Hub a real stock product photo (unlike the base
        # DeviceBase.photo, which is always None), so this must be populated.
        assert any(
            "surepetcare.io/assets/assets/products" in url
            for url in activity_222527.attributes["device_photos"].values()
        )

        # Household 245684's activity feed: just Ajax's feeding.
        activity_245684 = hass.states.get(
            "sensor.test_household_245684_household_activity_today"
        )
        assert activity_245684.state == "1"
