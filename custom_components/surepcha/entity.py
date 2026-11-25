from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any, cast

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo, EntityDescription
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import UNDEFINED
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from surepcio.command import Command
from surepcio.devices.device import SurePetCareBase
from surepcio.enums import ProductId, TimelineEventType
from surepcio.timeline import TimelineEvent

from .const import DOMAIN
from .coordinator import SurePetCareCoordinator
from .helper import iter_device_events, serialize

logger = logging.getLogger(__name__)


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


class SurePetCareBaseEntity(CoordinatorEntity[SurePetCareCoordinator], RestoreEntity):
    """Base SurePetCare device."""

    _attr_has_entity_name = True
    entity_description: SurePetCareDescriptionMixin

    def __init__(
        self,
        coordinator: SurePetCareCoordinator,
        device: SurePetCareBase,
        description: SurePetCareDescriptionMixin,
    ) -> None:
        """Initialize a device."""
        super().__init__(coordinator)
        self.device = device
        self._attr_extra_state_attributes = {}
        self.entity_description = description
        self._attr_translation_key = description.translation_key or description.key
        self._attr_unique_id = f"{device.id}-{description.key}"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self.entity_description.timeline_events:
            self.async_on_remove(
                self.coordinator.async_subscribe_timeline(self._handle_timeline)
            )

    @property
    def is_supported(self) -> bool:
        """Whether household hardware and device configuration allow discovery."""
        description = self.entity_description
        if description.supported_products and not any(
            device.product in description.supported_products
            for device in self.coordinator.devices.values()
        ):
            return False
        supported = description.supported
        return supported is None or supported(self.device)

    def _set_value(self, value: Any) -> None:
        """Store a value exposed by the platform's state property."""
        raise NotImplementedError

    def _update_state(self, value: Any, attributes: dict[str, Any]) -> None:
        self._set_value(value)
        self._attr_extra_state_attributes = (
            serialize(attributes) if value is not None else {}
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        return self._attr_extra_state_attributes

    def _handle_coordinator_update(self) -> None:
        description = self.entity_description
        if (
            description.value is not None
            and not description.timeline_events
            and self.device.id not in self.coordinator.device_errors
        ):
            self._update_state(*description.read_value(self))
        super()._handle_coordinator_update()

    def _handle_timeline(self, event: TimelineEvent) -> None:
        description = self.entity_description
        if event.event_type in description.timeline_events:
            for source in iter_device_events(
                event, self.device, self.coordinator.devices.values()
            ):
                reading = description.read_timeline(self.device, source)
                if reading is not None:
                    self._update_state(*reading)
                    self.async_write_ha_state()

    @property
    def name(self) -> str | None:
        """Use HA translations, retaining discovery for fields without translations."""
        name = super().name
        return (
            self.entity_description.key.replace("_", " ").capitalize()
            if name is UNDEFINED
            else name
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return a device description for device registry."""
        parent_device_id = self.device.entity_info.parent_device_id
        device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{self.device.id}")},
            manufacturer="SurePetCare",
            model=self.device.product_name,
            model_id=str(self.device.product_id),
            name=self.device.name,
        )
        if parent_device_id is not None:
            parent_identifier = (DOMAIN, str(parent_device_id))
            try:
                device_info["via_device_id"] = dr.async_get_device_id_by_identifier(
                    self.hass,
                    parent_identifier,
                    config_entry_id=self.coordinator.config_entry.entry_id,
                )
            except ValueError:
                logger.debug(
                    "Skipping via_device_id for %s: parent %s not found in config entry %s",
                    self.device.id,
                    parent_identifier,
                    self.coordinator.config_entry.entry_id,
                )
        return device_info

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.device.id not in self.coordinator.device_errors
            and bool(self.device.available)
            and super().available
        )

    async def send_command(self, value: Any) -> None:
        """Send command to device."""
        description = self.entity_description
        if description.command is None:
            raise HomeAssistantError(
                f"Field {self.entity_description.key!r} is not writable"
            )
        value = description.prepare_command_value(value, self)
        await self.coordinator.client.api(description.command(self, value))
        await self.coordinator.async_refresh_device(self.device)
