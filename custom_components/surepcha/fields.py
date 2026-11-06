"""API readers and commands shared by native Home Assistant descriptions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, cast

from homeassistant.helpers.entity import EntityDescription
from surepcio.command import Command
from surepcio.enums import ProductId, TimelineEventType
from surepcio.timeline import TimelineEvent

if TYPE_CHECKING:
    from .entity import SurePetCareBaseEntity

type TimelineValue = Callable[[Any, TimelineEvent], tuple[Any, dict[str, Any]] | None]
type ReportValue = str | Callable[[Any], Any]
type FieldValue = ReportValue | TimelineValue
type FieldCommand = Callable[[Any, Any], Command | list[Command]]
FLAP_PRODUCTS = (
    ProductId.PET_DOOR,
    ProductId.DUAL_SCAN_CONNECT,
    ProductId.DUAL_SCAN_PET_DOOR,
)
ACTIVITY_PRODUCTS = (
    ProductId.FEEDER_CONNECT,
    ProductId.POSEIDON_CONNECT,
    *FLAP_PRODUCTS,
)


class FieldPathError(LookupError):
    """A declared API path does not exist on the device."""


@dataclass(frozen=True, slots=True)
class FieldOption:
    """An API write value and its Home Assistant label."""

    value: str
    label: str


@dataclass(frozen=True, kw_only=True)
class SurePetCareDescriptionMixin(EntityDescription):
    """API behavior added to native platform metadata."""

    value: FieldValue | None = None
    command: FieldCommand | None = None
    attributes: ReportValue | None = None
    supported: Callable[[Any], bool] | None = None
    supported_products: tuple[ProductId, ...] = ()
    timeline_events: tuple[TimelineEventType, ...] = ()

    def __post_init__(self) -> None:
        if self.timeline_events and not callable(self.value):
            raise ValueError(
                f"Timeline field {self.key!r} needs a callable value reader"
            )

    def normalize_value(self, value: Any, entity: SurePetCareBaseEntity) -> Any:
        """Convert a report value to this platform's native representation."""
        return value.name.lower() if isinstance(value, Enum) else value

    def prepare_command_value(self, value: Any, entity: SurePetCareBaseEntity) -> Any:
        """Convert a native command value to its API representation."""
        return value

    def read_value(self, entity: SurePetCareBaseEntity) -> tuple[Any, dict[str, Any]]:
        """Read a report using an entity callback or an explicit device path."""
        value = _read(entity, cast(ReportValue | None, self.value), self.key)
        attributes = _read(entity, self.attributes, f"{self.key} attributes")
        return self.normalize_value(value, entity), attributes or {}

    def read_timeline(
        self, device: Any, event: TimelineEvent
    ) -> tuple[Any, dict[str, Any]] | None:
        """Read a timeline value after event-type and resource matching."""
        return cast(TimelineValue, self.value)(device, event)


@dataclass(frozen=True, kw_only=True)
class SurePetCareBooleanDescription(SurePetCareDescriptionMixin):
    """API enum conversion shared by binary sensors, switches, and locks."""

    true_value: Any = True
    false_value: Any = False

    def normalize_value(self, value: Any, entity: SurePetCareBaseEntity) -> bool | None:
        return (
            True
            if value == self.true_value
            else False
            if value == self.false_value
            else None
        )

    def prepare_command_value(self, value: Any, entity: SurePetCareBaseEntity) -> Any:
        if not isinstance(value, bool):
            raise TypeError(f"Field {self.key!r} requires a boolean")
        return self.true_value if value else self.false_value


def _read(entity: SurePetCareBaseEntity, reader: ReportValue | None, label: str) -> Any:
    if reader is None:
        return None
    if callable(reader):
        return reader(entity)
    value: Any = entity.device
    for part in reader.split("."):
        if value is None:
            return None
        if isinstance(value, dict):
            if part not in value:
                raise FieldPathError(
                    f"Field {label!r} path {reader!r} is missing key {part!r}"
                )
            value = value[part]
        else:
            try:
                value = getattr(value, part)
            except AttributeError as error:
                raise FieldPathError(
                    f"Field {label!r} path {reader!r} is missing attribute {part!r}"
                ) from error
    return value
