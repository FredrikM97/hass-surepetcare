import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, TypeVar

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util
from surepcio import Household, SurePetcareClient
from surepcio.devices.device import SurePetCareBase

from .const import (
    EVENT_TIMELINE,
    OPTION_DEVICES,
    OPTION_TIMELINE,
    POLLING_SPEED,
    SCAN_INTERVAL,
    TIMELINE_POLLING_SPEED,
)
from .feeding_timeline import (
    HouseholdTimelineData,
    fetch_household_name,
    fetch_household_timeline_today,
    fetch_new_events,
    fold_new_events,
)
from .timeline import build_event_payload

logger = logging.getLogger(__name__)


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


class SurePetCareFeedingTimelineCoordinator(
    DataUpdateCoordinator[HouseholdTimelineData]
):
    """Coordinator exposing today's feeding stats and activity feed for a household.

    Rebuilds from scratch (a backward walk to local midnight) on the first
    poll, after local midnight, or when there's no cursor yet; otherwise
    polls incrementally via a single since_id request. The cursor lags one
    poll behind, like SurePetCareHouseholdTimelineCoordinator above, since
    timeline ids aren't strictly ordered by created_at.
    """

    config_entry: SurePetcareConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: SurePetcareConfigEntry,
        client: SurePetcareClient,
        household_id: int,
    ) -> None:
        """Initialize household feeding-timeline coordinator."""
        super().__init__(
            hass,
            logger,
            config_entry=entry,
            name=f"surepetcare feeding timeline household {household_id}",
            update_interval=timedelta(
                seconds=entry.options.get(OPTION_TIMELINE, {}).get(
                    TIMELINE_POLLING_SPEED, SCAN_INTERVAL
                )
            ),
        )
        self.client = client
        self.household_id = household_id
        self.household_name: str | None = None
        self._today_date: date | None = None
        self._cursor: int | None = None
        self._pending_cursor: int | None = None
        self._seen_ids: OrderedDict[int, None] = OrderedDict()
        self._seen_ids_limit = 500

    def _mark_seen(self, event_id: int) -> None:
        """Record an event id as folded in, bounding memory to the most recent ones."""
        self._seen_ids[event_id] = None
        if len(self._seen_ids) > self._seen_ids_limit:
            self._seen_ids.popitem(last=False)

    async def _async_update_data(self) -> HouseholdTimelineData:
        """Fetch today's feeding stats and activity feed for the household."""
        # Refresh the display name each poll so a household rename is picked up,
        # but keep the last known name if a fetch fails transiently.
        if (
            name := await fetch_household_name(self.client, self.household_id)
        ) is not None:
            self.household_name = name

        today = dt_util.start_of_local_day().date()
        if self.data is None or self._today_date != today or self._cursor is None:
            data = await fetch_household_timeline_today(self.client, self.household_id)
            self._today_date = today
            self._seen_ids.clear()
            self._cursor = self._pending_cursor = data.cursor
            return data

        data = self.data
        new_events = await fetch_new_events(
            self.client, self.household_id, self._cursor
        )
        if new_events:
            newest_id = max(event.id for event in new_events)
            unseen = [event for event in new_events if event.id not in self._seen_ids]
            fold_new_events(data, unseen)
            for event in new_events:
                self._mark_seen(event.id)
            self._cursor, self._pending_cursor = self._pending_cursor, newest_id
        return data
