"""Schedule household requests and forward timeline events unchanged."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from surepcio import Household, HouseholdState, SurePetcareClient, TimelineEvent
from surepcio.devices.device import SurePetCareBase

from .const import DOMAIN, EVENT_TIMELINE
from .helper import translate_auth_errors

logger = logging.getLogger(__name__)
DEVICE_POLL_INTERVAL = timedelta(minutes=15)


@dataclass
class SurePetCareRuntimeData:
    coordinator: SurePetCareCoordinator


type SurePetcareConfigEntry = ConfigEntry[SurePetCareRuntimeData]


class SurePetCareCoordinator(DataUpdateCoordinator[None]):
    """Refresh a household, retaining independent device and timeline failures."""

    config_entry: SurePetcareConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: SurePetcareConfigEntry,
        client: SurePetcareClient,
        household: Household,
        devices: list[SurePetCareBase],
    ) -> None:
        super().__init__(
            hass,
            logger,
            config_entry=entry,
            name=f"{household.id} household",
            update_interval=None,
        )
        self.client = client
        self.state = HouseholdState(
            client, household, devices, device_poll_interval=DEVICE_POLL_INTERVAL
        )
        self.devices = self.state.devices
        self.device_errors = self.state.device_errors
        self._store: Store[dict[str, Any]] = Store(
            hass,
            1,
            f"{DOMAIN}.{entry.entry_id}.timeline",
            private=True,
            atomic_writes=True,
        )
        self._timeline_listeners: list[Callable[[TimelineEvent], None]] = []

    async def _async_setup(self) -> None:
        """Restore the cursor once, before Home Assistant starts refreshing."""
        stored = await self._store.async_load()
        if stored is not None:
            self.state = HouseholdState(
                self.client,
                self.state.household,
                self.devices.values(),
                since_id=stored["seen_id"],
                device_poll_interval=DEVICE_POLL_INTERVAL,
            )
            self.devices = self.state.devices
            self.device_errors = self.state.device_errors

    async def async_refresh_device(self, device: SurePetCareBase) -> None:
        """Refresh a command target without polling the rest of the household."""
        async with self._debounced_refresh.async_lock():
            with translate_auth_errors():
                await self.state.refresh_device(device, publish=lambda _device: None)
            self.async_update_listeners()

    async def _async_update_data(self) -> None:
        with translate_auth_errors():
            await self.state.refresh(
                publish=lambda _device: None,
                publish_event=self._publish_event,
                publish_timeline=self._publish_timeline,
                on_devices_updated=self.async_update_listeners,
            )
        seen_id = self.state.seen_id
        if seen_id is not None:
            await self._store.async_save({"seen_id": seen_id})

    @callback
    def async_subscribe_timeline(
        self, listener: Callable[[TimelineEvent], None]
    ) -> Callable[[], None]:
        """Subscribe to unmodified household timeline events."""
        self._timeline_listeners.append(listener)

        @callback
        def unsubscribe() -> None:
            self._timeline_listeners.remove(listener)

        return unsubscribe

    @callback
    def _publish_timeline(self, event: TimelineEvent) -> None:
        for listener in tuple(self._timeline_listeners):
            listener(event)

    @callback
    def _publish_event(self, payload: dict[str, Any]) -> None:
        self.hass.bus.async_fire(EVENT_TIMELINE, payload)
