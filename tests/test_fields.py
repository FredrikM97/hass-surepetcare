"""Native Home Assistant descriptions and API behavior."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from surepcio import TimelineEvent
from surepcio.devices import load_device_class
from surepcio.enums import BowlType, FlapLocking, ProductId, TimelineEventType
from surepcio.timeline import WeightFrame, WeightResource

from custom_components.surepcha.binary_sensor import (
    BINARY_SENSOR_FIELDS,
    SurePetCareBinarySensorEntityDescription,
)
from custom_components.surepcha.button import (
    BUTTON_FIELDS,
    SurePetCareButtonEntityDescription,
)
from custom_components.surepcha.const import NAME, PRODUCT_ID
from custom_components.surepcha.field_helpers import (
    _assignment_options,
    iter_device_events,
)
from custom_components.surepcha.fields import (
    FieldOption,
    FieldPathError,
)
from custom_components.surepcha.lock import (
    LOCK_FIELDS,
    SurePetCareLockEntityDescription,
)
from custom_components.surepcha.number import (
    NUMBER_FIELDS,
    SurePetCareNumberEntityDescription,
)
from custom_components.surepcha.select import (
    SELECT_FIELDS,
    SurePetCareSelectEntityDescription,
)
from custom_components.surepcha.sensor import (
    SENSOR_FIELDS,
    SurePetCareSensor,
    SurePetCareSensorEntityDescription,
)
from custom_components.surepcha.switch import (
    SWITCH_FIELDS,
    SurePetCareSwitchEntityDescription,
)

PLATFORM_FIELDS = {
    "sensor": SENSOR_FIELDS,
    "binary_sensor": BINARY_SENSOR_FIELDS,
    "number": NUMBER_FIELDS,
    "select": SELECT_FIELDS,
    "switch": SWITCH_FIELDS,
    "button": BUTTON_FIELDS,
    "lock": LOCK_FIELDS,
}


def _descriptions(
    product: ProductId,
    *,
    platform: str | None = None,
    device=None,
    devices=(),
):
    """Collect native platform descriptions and apply their setup support rule."""
    catalogues = (
        {platform: PLATFORM_FIELDS[platform]}
        if platform is not None
        else PLATFORM_FIELDS
    )
    return tuple(
        (name, description)
        for name, catalogue in catalogues.items()
        for description in catalogue.get(product, ())
        if (
            not description.supported_products
            or any(item.product in description.supported_products for item in devices)
        )
        and (
            description.supported is None
            or (device is not None and description.supported(device))
        )
    )


def _pet():
    return load_device_class(ProductId.PET)(
        {
            "id": 10,
            "name": "Mittens",
            "household_id": 1,
            "tag": {"id": 100, "tag": "test-tag"},
        }
    )


def test_device_event_selection_uses_library_matching_and_selects_target_pet():
    pet = _pet()
    other_pet = _pet()
    other_pet.entity_info.id = 11
    event = MagicMock()
    matched = MagicMock()
    other_matched = MagicMock()
    with patch(
        "custom_components.surepcha.field_helpers.iter_pet_events",
        return_value=iter(((other_pet, other_matched), (pet, matched))),
    ) as match:
        assert list(iter_device_events(event, pet, [pet, other_pet])) == [matched]
        assert list(match.call_args.args[1]) == [pet, other_pet]
    device = MagicMock()
    assert list(iter_device_events(event, device, [device])) == [event]
    event.created_at = None
    assert list(iter_device_events(event, device, [device])) == []


def test_native_description_metadata_and_path_reading(snapshot):
    from homeassistant.components.sensor import SensorEntityDescription

    description = SurePetCareSensorEntityDescription(
        key="weight", value="status.weight"
    )
    entity = SimpleNamespace(
        device={"status": {"weight": 12}},
    )
    assert isinstance(description, SensorEntityDescription)
    assert not hasattr(description, "entity_description")
    assert not hasattr(description, "describe")
    assert {
        "reading": description.read_value(entity),
        "unit": description.native_unit_of_measurement,
    } == snapshot(name="path")

    entity.device = {"status": {}}
    with pytest.raises(FieldPathError, match="missing key"):
        description.read_value(entity)

    callable_description = SurePetCareSensorEntityDescription(
        key="value", value=lambda current: current.device.value
    )
    assert callable_description.read_value(
        SimpleNamespace(device=SimpleNamespace(value=21))
    ) == snapshot(name="callable")


def test_report_reading_normalizes_values_and_reads_attributes_once(snapshot):
    value = MagicMock(return_value=FlapLocking.UNLOCKED)
    attributes = MagicMock(return_value={"detail": False})
    description = SurePetCareSensorEntityDescription(
        key="state", value=value, attributes=attributes
    )
    entity = SimpleNamespace(device=object())

    assert description.read_value(entity) == snapshot
    value.assert_called_once_with(entity)
    attributes.assert_called_once_with(entity)


@pytest.mark.parametrize("allowed", [False, True])
def test_entity_support_property_evaluates_discovery_requirements(allowed, snapshot):
    predicate = MagicMock(return_value=allowed)
    description = SurePetCareSensorEntityDescription(
        key="conditional", supported=predicate
    )
    coordinator = MagicMock()
    device = MagicMock(id=1)
    entity = SurePetCareSensor(coordinator, device, description)
    conditional = entity.is_supported
    predicate.assert_called_once_with(device)
    unconditional = SurePetCareSensor(
        coordinator, device, SurePetCareSensorEntityDescription(key="unconditional")
    ).is_supported
    assert {
        "conditional": conditional,
        "unconditional": unconditional,
    } == snapshot


@pytest.mark.parametrize(
    "products",
    [
        [],
        [ProductId.HUB],
        [ProductId.PET_DOOR],
        [ProductId.HUB, ProductId.DUAL_SCAN_CONNECT],
    ],
    ids=["empty", "hub", "flap", "hub-and-flap"],
)
def test_supported_products_uses_any_matching_coordinator_device(products, snapshot):
    description = SurePetCareSensorEntityDescription(
        key="position",
        supported_products=(ProductId.PET_DOOR, ProductId.DUAL_SCAN_CONNECT),
    )
    coordinator = MagicMock()
    coordinator.devices = {
        index: SimpleNamespace(product=product)
        for index, product in enumerate(products)
    }
    entity = SurePetCareSensor(coordinator, MagicMock(id=1), description)
    assert {"supported": entity.is_supported} == snapshot


def test_timeline_fields_require_a_callable_value_reader():
    with pytest.raises(ValueError, match="callable value reader"):
        SurePetCareSensorEntityDescription(
            key="missing_reader",
            timeline_events=(TimelineEventType.MOVEMENT,),
        )
    with pytest.raises(ValueError, match="callable value reader"):
        SurePetCareSensorEntityDescription(
            key="two_sources",
            value="status.position",
            timeline_events=(TimelineEventType.MOVEMENT,),
        )
    reader = lambda device, event: None
    description = SurePetCareSensorEntityDescription(
        key="timeline",
        value=reader,
        timeline_events=(TimelineEventType.MOVEMENT,),
    )
    assert description.value is reader


def test_native_select_options_and_dynamic_api_options_are_distinct(snapshot):
    description = SurePetCareSelectEntityDescription(
        key="choice", options=["First", "Second"]
    )
    dynamic = SurePetCareSelectEntityDescription(
        key="choice",
        options=["Static"],
        options_fn=lambda *_: (FieldOption("write_value", "Dynamic"),),
    )
    assert {
        "static": description.get_options(None),
        "dynamic_metadata": dynamic.options,
        "dynamic": dynamic.get_options(None),
    } == snapshot
    with pytest.raises(FrozenInstanceError):
        description.key = "changed"
    with pytest.raises(TypeError):
        SurePetCareSelectEntityDescription("choice")


def test_assignment_options_read_current_configuration_without_copied_inventory(
    snapshot,
):
    from surepcio.enums import ModifyDeviceTag

    entity = SimpleNamespace(
        hass=object(),
        coordinator=SimpleNamespace(config_entry=object()),
        device=SimpleNamespace(
            status=SimpleNamespace(devices=SimpleNamespace(items=[]))
        ),
    )
    options = {
        "20": {NAME: "Feeder", PRODUCT_ID: ProductId.FEEDER_CONNECT},
        "21": {NAME: "Hub", PRODUCT_ID: ProductId.HUB},
    }
    with patch(
        "custom_components.surepcha.field_helpers.get_device_options",
        return_value=options,
    ):
        assert _assignment_options(entity, ModifyDeviceTag.ADD) == snapshot(
            name="initial"
        )
        options["20"][NAME] = "Renamed"
        assert _assignment_options(entity, ModifyDeviceTag.ADD) == snapshot(
            name="renamed"
        )


def test_native_catalogues_cover_products_with_platform_scoped_keys(snapshot):
    assert {
        platform: {
            product.name: [description.key for description in descriptions]
            for product, descriptions in catalogue.items()
        }
        for platform, catalogue in PLATFORM_FIELDS.items()
    } == snapshot
    products = {
        product for catalogue in PLATFORM_FIELDS.values() for product in catalogue
    }
    for product in products:
        assert _descriptions(product)
        for catalogue in PLATFORM_FIELDS.values():
            descriptions = catalogue.get(product, ())
            assert len({description.key for description in descriptions}) == len(
                descriptions
            )
    assert not hasattr(load_device_class(ProductId.HUB), "field_definitions")


@pytest.mark.parametrize(
    "products",
    [
        [],
        [ProductId.HUB],
        [ProductId.FEEDER_CONNECT],
        [ProductId.POSEIDON_CONNECT],
        [ProductId.PET_DOOR],
        [ProductId.DUAL_SCAN_CONNECT],
        [ProductId.DUAL_SCAN_PET_DOOR],
    ],
    ids=[
        "empty",
        "hub",
        "feeder",
        "poseidon",
        "pet-door",
        "dual-scan",
        "dual-scan-pet-door",
    ],
)
def test_supported_pet_descriptions_use_the_complete_household_inventory(
    products, snapshot
):
    pet = _pet()
    devices = tuple(SimpleNamespace(product=product) for product in products)
    assert {
        platform: sorted(
            description.key
            for name, description in _descriptions(
                ProductId.PET, device=pet, devices=devices
            )
            if name == platform
        )
        for platform in PLATFORM_FIELDS
    } == snapshot


def test_second_bowl_descriptions_are_supported_only_for_two_bowls(snapshot):
    feeder = load_device_class(ProductId.FEEDER_CONNECT)(
        {
            "id": 20,
            "household_id": 1,
            "control": {
                "bowls": {
                    "type": BowlType.TWO_SMALL.value,
                    "settings": [{"target": 100}, {"target": 200}],
                }
            },
        }
    )
    descriptions = {}
    for platform, description in _descriptions(ProductId.FEEDER_CONNECT, device=feeder):
        descriptions.setdefault(platform, []).append(description)
    command = next(
        description
        for description in descriptions["number"]
        if description.key == "bowl_1_target_weight"
    ).command
    api_command = command(SimpleNamespace(device=feeder), 150)
    assert {
        "fields": {
            platform: [description.key for description in fields]
            for platform, fields in descriptions.items()
        },
        "command": api_command.params,
    } == snapshot(name="two-bowls")

    single = load_device_class(ProductId.FEEDER_CONNECT)({"id": 21, "household_id": 1})
    assert [
        (platform, description.key)
        for platform, description in _descriptions(
            ProductId.FEEDER_CONNECT, device=single
        )
    ] == snapshot(name="single-bowl")


@pytest.mark.parametrize(
    "value",
    [True, False],
)
def test_boolean_command_values_are_prepared_by_the_description(value, snapshot):
    description = SurePetCareSwitchEntityDescription(
        key="toggle", true_value="enabled", false_value="disabled"
    )
    entity = SimpleNamespace(device=object())
    prepared = description.prepare_command_value(value, entity)
    assert {
        "prepared": prepared,
        "normalized": description.normalize_value(prepared, entity),
    } == snapshot
    with pytest.raises(TypeError, match="boolean"):
        description.prepare_command_value("yes", entity)


def test_select_command_prepares_api_choice_and_rejects_unavailable_choice(snapshot):
    description = SurePetCareSelectEntityDescription(
        key="locking",
        choices=FlapLocking,
        options_fn=lambda *_: (
            FieldOption("locked", "Locked"),
            FieldOption("unlocked", "Unlocked"),
        ),
    )
    entity = SimpleNamespace(device=object())
    assert {
        "normalized": description.normalize_value(FlapLocking.UNLOCKED, entity),
        "prepared": description.prepare_command_value("Locked", entity),
    } == snapshot
    with pytest.raises(ValueError, match="unavailable"):
        description.prepare_command_value("Unknown", entity)


async def test_entity_command_sends_prepared_value_and_refreshes_target():
    from custom_components.surepcha.switch import SurePetCareSwitch

    device = MagicMock(id=42)
    command = MagicMock(return_value="api-command")
    description = SurePetCareSwitchEntityDescription(
        key="toggle",
        command=command,
        true_value="enabled",
        false_value="disabled",
    )
    coordinator = MagicMock()
    coordinator.client.api = AsyncMock(return_value="sent")
    coordinator.async_refresh_device = AsyncMock()
    entity = SurePetCareSwitch(coordinator, device, description)

    await entity.send_command(True)

    command.assert_called_once_with(entity, "enabled")
    coordinator.client.api.assert_awaited_once_with("api-command")
    coordinator.async_refresh_device.assert_awaited_once_with(device)


def test_timeline_readers_use_only_the_existing_event(snapshot):
    feeder = load_device_class(ProductId.FEEDER_CONNECT)(
        {
            "id": 20,
            "household_id": 1,
            "control": {
                "bowls": {
                    "type": BowlType.TWO_SMALL.value,
                    "settings": [{"target": 100}, {"target": 200}],
                }
            },
        }
    )
    event = TimelineEvent(
        id=1,
        type=TimelineEventType.WEIGHT_CHANGED,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        weights=[
            WeightResource(
                device_id=feeder.id,
                frames=[
                    WeightFrame(index=0, current_weight=50),
                    WeightFrame(index=1, current_weight=100),
                ],
            )
        ],
    )
    descriptions = {
        description.key: description
        for _, description in _descriptions(ProductId.FEEDER_CONNECT, device=feeder)
        if description.timeline_events
    }
    assert {
        key: description.read_timeline(feeder, event)
        for key, description in descriptions.items()
    } == snapshot(name="observed")
    for setting in feeder.control.bowls.settings:
        setting.target = None
    assert descriptions["fill_percent"].read_timeline(feeder, event) == snapshot(
        name="unknown-targets"
    )
    event.weights.clear()
    assert {
        key: description.read_timeline(feeder, event)
        for key, description in descriptions.items()
    } == snapshot(name="absent")


def test_same_description_key_can_exist_on_separate_native_platforms():
    sensor = SurePetCareSensorEntityDescription(key="position", value="status.where")
    switch = SurePetCareSwitchEntityDescription(key="position", value="status.where")
    assert sensor.key == switch.key
    assert sensor is not switch
    assert isinstance(sensor, SurePetCareSensorEntityDescription)
    assert isinstance(switch, SurePetCareSwitchEntityDescription)


def test_platform_description_types_remain_native():
    assert isinstance(
        BINARY_SENSOR_FIELDS[ProductId.HUB][0],
        SurePetCareBinarySensorEntityDescription,
    )
    assert isinstance(
        BUTTON_FIELDS[ProductId.HUB][0], SurePetCareButtonEntityDescription
    )
    assert isinstance(
        LOCK_FIELDS[ProductId.PET_DOOR][0], SurePetCareLockEntityDescription
    )
    assert isinstance(
        NUMBER_FIELDS[ProductId.FEEDER_CONNECT][0],
        SurePetCareNumberEntityDescription,
    )
