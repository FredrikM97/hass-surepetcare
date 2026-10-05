"""Test helpers kept local to this integration."""

import dataclasses
import json
from collections.abc import Iterable, Mapping
from contextlib import suppress
from pathlib import Path
from typing import Any, ClassVar

import attr
import attrs
import voluptuous as vol
from homeassistant.config_entries import (
    SOURCE_USER,
    ConfigEntry,
    ConfigEntryDisabler,
    ConfigEntryState,
    DiscoveryKey,
)
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import ulid as ulid_util
from probatio import to_field_list
from syrupy.assertion import SnapshotAssertion
from syrupy.extensions.amber import AmberDataSerializer, AmberSnapshotExtension
from syrupy.location import PyTestLocation
from syrupy.types import PropertyFilter, PropertyMatcher, PropertyPath, SerializableData


class _AnyValue:
    def __repr__(self) -> str:
        return "<ANY>"


ANY = _AnyValue()


class ConfigEntrySnapshot(dict):
    """Stable config-entry representation for snapshots."""


class DeviceRegistryEntrySnapshot(dict):
    """Stable device-registry representation for snapshots."""


class EntityRegistryEntrySnapshot(dict):
    """Stable entity-registry representation for snapshots."""


class FlowResultSnapshot(dict):
    """Stable config-flow representation for snapshots."""


class StateSnapshot(dict):
    """Stable state representation for snapshots."""


class MockConfigEntry(ConfigEntry):
    """Config entry with defaults for integration tests."""

    def __init__(
        self,
        *,
        data: Mapping[str, Any] | None = None,
        disabled_by: ConfigEntryDisabler | None = None,
        discovery_keys: Mapping[str, tuple[DiscoveryKey, ...]] | None = None,
        domain: str = "test",
        entry_id: str | None = None,
        minor_version: int = 1,
        options: Mapping[str, Any] | None = None,
        pref_disable_new_entities: bool | None = None,
        pref_disable_polling: bool | None = None,
        reason: str | None = None,
        source: str | None = SOURCE_USER,
        state: ConfigEntryState | None = None,
        subentries_data: Iterable[Any] | None = None,
        title: str = "Mock Title",
        unique_id: str | None = None,
        version: int = 1,
    ) -> None:
        kwargs: dict[str, Any] = {
            "data": data or {},
            "disabled_by": disabled_by,
            "discovery_keys": discovery_keys or {},
            "domain": domain,
            "entry_id": entry_id or ulid_util.ulid_now(),
            "minor_version": minor_version,
            "options": options or {},
            "pref_disable_new_entities": pref_disable_new_entities,
            "pref_disable_polling": pref_disable_polling,
            "subentries_data": subentries_data or (),
            "title": title,
            "unique_id": unique_id,
            "version": version,
        }
        if source is not None:
            kwargs["source"] = source
        if state is not None:
            kwargs["state"] = state
        super().__init__(**kwargs)
        if reason is not None:
            object.__setattr__(self, "reason", reason)

    def add_to_hass(self, hass: HomeAssistant) -> None:
        hass.config_entries._entries[self.entry_id] = self


def load_json_value_fixture(filename: str) -> Any:
    """Load a JSON fixture from this test package."""
    fixture_path = Path(__file__).parent / "fixtures" / filename
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def async_capture_events(hass: HomeAssistant, event_name: str) -> list[Event]:
    """Collect events with the given type from Home Assistant's event bus."""
    events: list[Event] = []

    @callback
    def capture(event: Event) -> None:
        events.append(event)

    hass.bus.async_listen(event_name, capture)
    return events


async def snapshot_platform(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    snapshot: SnapshotAssertion,
    config_entry_id: str,
) -> None:
    """Snapshot every enabled entity and state for a single platform."""
    entity_entries = er.async_entries_for_config_entry(entity_registry, config_entry_id)
    assert entity_entries
    assert len({entry.domain for entry in entity_entries}) == 1, (
        "Please limit the loaded platforms to 1 platform."
    )
    for entity_entry in entity_entries:
        assert entity_entry == snapshot(name=f"{entity_entry.entity_id}-entry")
        assert entity_entry.disabled_by is None, "Please enable all entities."
        state = hass.states.get(entity_entry.entity_id)
        assert state, f"State not found for {entity_entry.entity_id}"
        assert state == snapshot(name=f"{entity_entry.entity_id}-state")


class HomeAssistantSnapshotSerializer(AmberDataSerializer):
    """Normalize Home Assistant objects before Syrupy serializes them."""

    _INTERNAL_DEVICE_FIELDS: ClassVar[set[str]] = {
        "composite_device_id",
        "composite_primary_config_entry",
        "has_composite_identifiers",
        "split_at",
    }

    @classmethod
    def _serialize(
        cls,
        data: SerializableData,
        *,
        depth: int = 0,
        exclude: PropertyFilter | None = None,
        include: PropertyFilter | None = None,
        matcher: PropertyMatcher | None = None,
        path: PropertyPath = (),
        visited: set[Any] | None = None,
    ) -> str:
        if isinstance(data, State):
            normalized: SerializableData = StateSnapshot(
                data.as_dict()
                | {
                    "context": ANY,
                    "last_changed": ANY,
                    "last_reported": ANY,
                    "last_updated": ANY,
                }
            )
        elif isinstance(data, dr.DeviceEntry):
            normalized = cls._device_entry(data)
        elif isinstance(data, er.RegistryEntry):
            normalized = cls._entity_entry(data)
        elif isinstance(data, ConfigEntry):
            normalized = cls._remove_timestamps(
                ConfigEntrySnapshot(data.as_dict() | {"entry_id": ANY})
            )
        elif isinstance(data, dict) and "flow_id" in data and "handler" in data:
            normalized = FlowResultSnapshot(data | {"flow_id": ANY})
        elif isinstance(data, vol.Schema):
            normalized = to_field_list(data)
        elif dataclasses.is_dataclass(type(data)):
            normalized = dataclasses.asdict(data)
        else:
            normalized = data
            with suppress(TypeError):
                if attr.has(type(data)):
                    normalized = attrs.asdict(data)

        return super()._serialize(
            normalized,
            depth=depth,
            exclude=exclude,
            include=include,
            matcher=matcher,
            path=path,
            visited=visited,
        )

    @classmethod
    def _device_entry(cls, data: dr.DeviceEntry) -> SerializableData:
        serialized = DeviceRegistryEntrySnapshot(
            attr.asdict(
                data,
                retain_collection_types=True,
                filter=lambda attribute, _: (
                    not attribute.name.startswith("_")
                    and attribute.name not in cls._INTERNAL_DEVICE_FIELDS
                ),
            )
            | {
                "config_entry_id": ANY,
                "config_subentry_id": ANY,
                "id": ANY,
            }
        )
        if serialized.get("via_device_id") is not None:
            serialized["via_device_id"] = ANY
        if serialized.get("primary_config_entry") is not None:
            serialized["primary_config_entry"] = ANY
        return cls._remove_timestamps(serialized)

    @classmethod
    def _entity_entry(cls, data: er.RegistryEntry) -> SerializableData:
        serialized = EntityRegistryEntrySnapshot(
            attrs.asdict(data)
            | {
                "config_entry_id": ANY,
                "config_subentry_id": ANY,
                "device_id": ANY,
                "id": ANY,
                "options": {key: dict(value) for key, value in data.options.items()},
            }
        )
        for key in ("categories", "compat_aliases", "original_name_unprefixed", "_cache"):
            serialized.pop(key, None)
        serialized["aliases"] = er._serialize_aliases(serialized["aliases"])
        return cls._remove_timestamps(serialized)

    @staticmethod
    def _remove_timestamps(data: dict[str, Any]) -> dict[str, Any]:
        data.pop("created_at", None)
        data.pop("modified_at", None)
        return data


class HomeAssistantSnapshotExtension(AmberSnapshotExtension):
    """Use the repository's snapshots directory and HA-aware serializer."""

    VERSION = "1"
    serializer_class = HomeAssistantSnapshotSerializer

    @classmethod
    def dirname(cls, *, test_location: PyTestLocation) -> str:
        return str(Path(test_location.filepath).parent / "snapshots")