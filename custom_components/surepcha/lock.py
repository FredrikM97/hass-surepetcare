"""Present library lock interactions."""

from dataclasses import dataclass
from typing import Any

from homeassistant.components.lock import LockEntity, LockEntityDescription, LockState
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from surepcio.enums import FlapLocking, ProductId

from .coordinator import SurePetcareConfigEntry
from .entity import SurePetCareBaseEntity
from .fields import SurePetCareBooleanDescription


@dataclass(frozen=True, kw_only=True)
class SurePetCareLockEntityDescription(
    LockEntityDescription, SurePetCareBooleanDescription
):
    """Native lock metadata and SurePetCare API behavior."""


_locking = SurePetCareLockEntityDescription(
    key="locking",
    value="control.locking",
    command=lambda entity, value: entity.device.set_locking(value),
    true_value=FlapLocking.LOCKED,
    false_value=FlapLocking.UNLOCKED,
)
LOCK_FIELDS: dict[ProductId, tuple[SurePetCareLockEntityDescription, ...]] = {
    ProductId.PET_DOOR: (_locking,),
    ProductId.DUAL_SCAN_CONNECT: (_locking,),
    ProductId.DUAL_SCAN_PET_DOOR: (_locking,),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SurePetcareConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        SurePetCareLock(coordinator, device, description)
        for device in coordinator.devices.values()
        for description in LOCK_FIELDS.get(device.product, ())
    )


class SurePetCareLock(SurePetCareBaseEntity, LockEntity):
    """A library-provided lock."""

    entity_description: SurePetCareLockEntityDescription

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state is not None and state.state in (LockState.LOCKED, LockState.UNLOCKED):
            self._update_state(state.state == LockState.LOCKED, dict(state.attributes))

    def _set_value(self, value: Any) -> None:
        self._attr_is_locked = value

    @property
    def is_locked(self) -> bool | None:
        return self._attr_is_locked

    async def async_lock(self, **kwargs) -> None:
        await self.send_command(True)

    async def async_unlock(self, **kwargs) -> None:
        await self.send_command(False)
