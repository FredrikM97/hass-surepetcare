import json
from pathlib import Path
import pytest
from syrupy.assertion import SnapshotAssertion
from unittest.mock import MagicMock
from custom_components.surepetcare.const import DOMAIN
from custom_components.surepetcare.sensor import (
    async_setup_entry,
)
from tests.conftest import (
    FIXTURES,
    create_device_from_fixture,
    extract_sensor_outputs,
    setup_coordinator,
)

from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.mark.parametrize("fixture_file", FIXTURES)
@pytest.mark.asyncio
async def test_sensor_snapshot_from_fixture(
    hass, snapshot: SnapshotAssertion, fixture_file
):
    fixture_data = json.loads((Path("tests/fixtures") / fixture_file).read_text())
    config_entry = MockConfigEntry(
        domain=DOMAIN, data={"token": "abc", "device_id": "123"}
    )
    config_entry.add_to_hass(hass)

    device = create_device_from_fixture(fixture_data)
    setup_coordinator(hass, config_entry, device)

    async_add_entities = MagicMock()
    await async_setup_entry(hass, config_entry, async_add_entities)

    assert extract_sensor_outputs(async_add_entities) == snapshot
