"""Timeline-event behavior for SurePetCare entities."""

from dataclasses import dataclass
from typing import Any

from homeassistant.core import Event, callback
from homeassistant.helpers.restore_state import ExtraStoredData

from .const import EVENT_TIMELINE
from .coordinator import SurePetCareDeviceDataUpdateCoordinator
from .entity import SurePetCareBaseEntity
from .method_field import FieldContext


@dataclass(frozen=True, slots=True)
class TimelineEventRestoreData(ExtraStoredData):
    """Persist the parent timeline event used by an event-backed entity."""

    event_data: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        """Return JSON-serializable restored data."""
        return {"event_data": self.event_data}


class SurePetCareEventEntity(SurePetCareBaseEntity):
    """Base entity behavior for values sourced from household timeline events."""

    def __init__(self, coordinator: SurePetCareDeviceDataUpdateCoordinator) -> None:
        """Initialize an event-capable entity."""
        super().__init__(coordinator)
        self._event_data: dict[str, Any] | None = None

    def _handle_coordinator_update(self) -> None:
        """Ignore polled updates for event-backed values."""
        if self.use_events:
            return
        super()._handle_coordinator_update()

    async def async_added_to_hass(self) -> None:
        """Restore and subscribe to timeline data when this entity uses events."""
        await super().async_added_to_hass()
        if not self.use_events:
            return

        if restored_data := await self.async_get_last_extra_data():
            event_data = restored_data.as_dict().get("event_data")
            if isinstance(event_data, dict):
                self._event_data = event_data
        runtime_data = self.coordinator.config_entry.runtime_data
        field = self.entity_description.field
        context = self.context
        for event_data in runtime_data.recent_timeline_events_for_household(
            self._device.household_id
        ):
            if matching_event := field.apply_event(context, event_data):
                self._event_data = matching_event
        self._cached_value = None
        self.async_on_remove(
            self.hass.bus.async_listen(EVENT_TIMELINE, self._handle_timeline_event)
        )

    @property
    def extra_restore_state_data(self) -> ExtraStoredData | None:
        """Persist event data used to calculate an event-backed entity state."""
        if self._event_data is None:
            return None
        return TimelineEventRestoreData(self._event_data)

    @property
    def context(self) -> FieldContext:
        """Return field context containing the last accepted timeline event."""
        return self._build_context(self._event_data)

    @callback
    def _handle_timeline_event(self, event: Event) -> None:
        field = self.entity_description.field
        if str(event.data.get("household_id")) != str(self._device.household_id):
            return

        if event_data := field.apply_event(self.context, event.data):
            self._event_data = event_data
            self._write_event_state()

    @callback
    def _write_event_state(self) -> None:
        self._cached_value = None
        self.async_write_ha_state()
