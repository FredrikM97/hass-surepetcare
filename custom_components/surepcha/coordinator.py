import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from surepcio import Household, SurePetcareClient
from surepcio.devices.device import SurePetCareBase
from surepcio.enums import TimelineEventType
from surepcio.timeline import MovementResource, TimelineEvent, WeightResource

from .const import (
    EVENT_TIMELINE,
    OPTION_DEVICES,
    OPTION_TIMELINE,
    POLLING_SPEED,
    SCAN_INTERVAL,
    TIMELINE_POLLING_SPEED,
)

logger = logging.getLogger(__name__)


# TODO: Move or remove this later to separate file
# Event types that carry door movement data (event.movements).
_MOVEMENT_EVENT_TYPES = {
    TimelineEventType.MOVEMENT,
    TimelineEventType.INTRUDER_MOVEMENT,
}

# TODO: Move or remove this later to separate file
# Event types that carry feeder/fountain weight data (event.weights).
_FEEDING_EVENT_TYPES = {
    TimelineEventType.FEEDING,
    TimelineEventType.WEIGHT_CHANGED,
    TimelineEventType.WEIGHT_CHANGED_TARGET_MET,
    TimelineEventType.TARGET_WEIGHT_SET,
    TimelineEventType.TARE,
}

# TODO: Move or remove this later to separate file
_DRINKING_EVENT_TYPES = {
    TimelineEventType.POSEIDON_DRINKING,
    TimelineEventType.POSEIDON_WEIGHT_CHANGED,
    TimelineEventType.POSEIDON_TARE,
}


# TODO: Move or remove this later to separate file
def _movement_details(movement: MovementResource) -> dict[str, Any]:
    """Build the payload for a single door movement entry."""
    return {
        "device_id": movement.device_id,
        "direction": movement.direction.name
        if movement.direction is not None
        else None,
        "side": movement.side.name if movement.side is not None else None,
    }


# TODO: Move or remove this later to separate file
def _weight_details(weight: WeightResource) -> dict[str, Any]:
    """Build the payload for a single feeder/fountain weight reading."""
    return {
        "device_id": weight.device_id,
        "duration": weight.duration,
        "frames": [
            {
                "index": frame.index,
                "current_weight": frame.current_weight,
                "change": frame.change,
            }
            for frame in weight.frames
        ],
    }


# TODO: Move or remove this later to separate file
def _base_event_payload(household_id: int, event: TimelineEvent) -> dict[str, Any]:
    """Build the fields common to every timeline event, regardless of type."""
    return {
        "household_id": household_id,
        "id": event.id,
        "type": event.event_type.name if event.event_type is not None else None,
        "created_at": event.created_at.isoformat()
        if event.created_at is not None
        else None,
        "pets": [pet.id for pet in event.pets],
        "devices": [device.id for device in event.devices],
        "users": [user.id for user in event.users],
    }


# TODO: Move or remove this later to separate file
def build_event_payload(household_id: int, event: TimelineEvent) -> dict[str, Any]:
    """Build the EVENT_TIMELINE payload for one event, by event category."""
    payload = _base_event_payload(household_id, event)
    if event.event_type in _MOVEMENT_EVENT_TYPES:
        payload["movements"] = [_movement_details(m) for m in event.movements]
    elif (
        event.event_type in _FEEDING_EVENT_TYPES
        or event.event_type in _DRINKING_EVENT_TYPES
    ):
        payload["weights"] = [_weight_details(w) for w in event.weights]
    return payload


@dataclass
class SurePetCareRuntimeData:
    """Runtime data stored on the config entry."""

    device_coordinators: list[SurePetCareDeviceDataUpdateCoordinator] = field(
        default_factory=list
    )
    timeline_coordinators: list[SurePetCareHouseholdTimelineCoordinator] = field(
        default_factory=list
    )


type SurePetcareConfigEntry = ConfigEntry[SurePetCareRuntimeData]
T = TypeVar("T", bound=SurePetCareBase)


class SurePetCareDeviceDataUpdateCoordinator(DataUpdateCoordinator[T]):
    """Coordinator to manage data for a specific SurePetCare device."""

    config_entry: SurePetcareConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: SurePetcareConfigEntry,
        client: SurePetcareClient,
        device: SurePetCareBase,
    ) -> None:
        """Initialize device coordinator."""
        super().__init__(
            hass,
            logger,
            config_entry=entry,
            name=f"{device.name}",
            update_interval=timedelta(
                seconds=entry.options.get(OPTION_DEVICES, {})
                .get(str(device.id), {})
                .get(POLLING_SPEED, SCAN_INTERVAL)
            ),
        )
        self._device = device
        self.product_id = self._device.product_id
        self.client = client
        self._exception: Exception | None = None

    async def _async_setup(self):
        """Fetch initial data for the device."""
        await self.client.api(self._device.refresh())

    async def _async_update_data(self) -> Any:
        """Fetch data from the api for a specific device."""
        logger.debug(
            "Fetching data for device %s (id=%s)", self._device.name, self._device.id
        )
        await self.client.api(self._device.refresh())
        return self._device


class SurePetCareHouseholdTimelineCoordinator(DataUpdateCoordinator[None]):
    """Polls a household's timeline and fires each new entry as a bus event.

    Events are not bound to any device/pet entity; consumers subscribe to
    EVENT_TIMELINE directly (e.g. via automations) rather than entity state.
    """

    config_entry: SurePetcareConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: SurePetcareConfigEntry,
        client: SurePetcareClient,
        household: Household,
    ) -> None:
        """Initialize the household timeline coordinator."""
        super().__init__(
            hass,
            logger,
            config_entry=entry,
            name=f"{household.id} timeline",
            update_interval=timedelta(
                seconds=entry.options.get(OPTION_TIMELINE, {}).get(
                    TIMELINE_POLLING_SPEED, SCAN_INTERVAL
                )
            ),
        )
        self.client = client
        self.household = household
        # Timeline ids are not strictly monotonic in created_at order (rare
        # cross-household id/time inversions), so a naive "cursor = highest id
        # seen" can permanently skip a late-arriving event with a lower id.
        # The cursor therefore lags one poll behind, and a bounded set of
        # recently-seen ids provides the dedupe that makes the lag safe.
        self._cursor: int | None = None
        self._pending_cursor: int | None = None
        self._seen_ids: OrderedDict[int, None] = OrderedDict()
        self._seen_ids_limit = 500

    def _mark_seen(self, event_id: int) -> None:
        """Record an event id as seen after it has been fired."""
        self._seen_ids[event_id] = None
        if len(self._seen_ids) > self._seen_ids_limit:
            self._seen_ids.popitem(last=False)

    async def _async_update_data(self) -> None:
        """Fetch new timeline events since the last known cursor and fire them."""
        logger.debug(
            "Fetching timeline for household %s (since_id=%s)",
            self.household.id,
            self._cursor,
        )
        events = list(
            await self.client.api(self.household.get_timeline(since_id=self._cursor))
        )
        if not events:
            logger.debug("No timeline events for household %s", self.household.id)
            return

        newest_id = max(event.id for event in events)

        if self._cursor is None and self._pending_cursor is None:
            # First poll after startup/reload: hook into the stream without
            # replaying existing history as if it just happened.
            for event in events:
                self._mark_seen(event.id)
            self._cursor = self._pending_cursor = newest_id
            logger.debug(
                "Timeline baseline set for household %s (cursor=%s)",
                self.household.id,
                newest_id,
            )
            return

        fired = 0
        for event in sorted(
            events, key=lambda e: e.created_at or datetime.min.replace(tzinfo=UTC)
        ):
            if event.id in self._seen_ids:
                continue
            self.hass.bus.async_fire(
                EVENT_TIMELINE, build_event_payload(self.household.id, event)
            )
            self._mark_seen(event.id)
            fired += 1
        logger.debug(
            "Fired %d/%d new timeline event(s) for household %s",
            fired,
            len(events),
            self.household.id,
        )
        self._cursor, self._pending_cursor = self._pending_cursor, newest_id
        return
