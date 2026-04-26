"""Lock platform for SurePetCare integration."""

from __future__ import annotations
from dataclasses import dataclass
import logging
from homeassistant.components.lock import LockEntity, LockEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.lock.const import LockState
from custom_components.surepcha.method_field import LockMethodField
from .coordinator import SurePetCareDeviceDataUpdateCoordinator, SurePetcareConfigEntry
from .entity import (
    SurePetCareBaseEntity,
    SurePetCareBaseEntityDescription,
)
from surepcio.enums import ProductId, FlapLocking

logger = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class SurePetCareLockEntityDescription(
    SurePetCareBaseEntityDescription, LockEntityDescription
):
    """Describes SurePetCare lock entity."""


SENSOR_DESCRIPTIONS_LOCKING: tuple[SurePetCareLockEntityDescription, ...] = (
    SurePetCareLockEntityDescription(
        key="locking",
        translation_key="locking",
        field=LockMethodField(
            path="control.locking",
            states={
                LockState.LOCKED: FlapLocking.LOCKED,
                LockState.UNLOCKED: FlapLocking.UNLOCKED,
            },
        ),
    ),
)

LOCKS: dict[str, tuple[SurePetCareLockEntityDescription, ...]] = {
    ProductId.PET_DOOR: (*SENSOR_DESCRIPTIONS_LOCKING,),
    ProductId.DUAL_SCAN_CONNECT: (*SENSOR_DESCRIPTIONS_LOCKING,),
    ProductId.DUAL_SCAN_PET_DOOR: (*SENSOR_DESCRIPTIONS_LOCKING,),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SurePetcareConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SurePetCare lock for each matching device."""
    coordinators = entry.runtime_data

    entities = [
        SurePetCareLock(
            coordinator,
            description=description,
        )
        for coordinator in coordinators
        for description in LOCKS.get(coordinator.product_id, ())
    ]
    async_add_entities(entities)


class SurePetCareLock(SurePetCareBaseEntity, LockEntity):
    """Lock entity for SurePetCare device."""

    entity_description: SurePetCareLockEntityDescription

    def __init__(
        self,
        coordinator: SurePetCareDeviceDataUpdateCoordinator,
        description: SurePetCareLockEntityDescription,
    ) -> None:
        super().__init__(
            coordinator=coordinator,
        )
        self.entity_description = description
        self._attr_unique_id = f"{coordinator._device.id}-{description.key}"

    @property
    def is_locked(self) -> bool:
        return self.lock_state() == LockState.LOCKED

    async def async_lock(self, **kwargs):
        await self.send_command(LockState.LOCKED)

    async def async_unlock(self, **kwargs):
        await self.send_command(LockState.UNLOCKED)

    def lock_state(self):
        """Return the lock state."""
        return self.entity_description.field.get(self.context)
