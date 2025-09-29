"""Lock platform for SurePetCare integration."""

from __future__ import annotations
from dataclasses import dataclass
from homeassistant.components.lock import LockEntity, LockEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .coordinator import SurePetCareDeviceDataUpdateCoordinator
from .entity import (
    SurePetCareBaseEntity,
    SurePetCareBaseEntityDescription,
)
from surepcio.enums import ProductId, FlapLocking
from .const import COORDINATOR, COORDINATOR_DICT, DOMAIN, KEY_API


@dataclass(frozen=True, kw_only=True)
class SurePetCareLockEntityDescription(
    SurePetCareBaseEntityDescription, LockEntityDescription
):
    """Describes SurePetCare lock entity."""

    locked_states: dict[str, str] | None = None


LOCKS: dict[str, tuple[SurePetCareLockEntityDescription, ...]] = {
    ProductId.PET_DOOR: (
        SurePetCareLockEntityDescription(
            key="locking",
            translation_key="locking",
            field="control.locking",
            locked_states={
                "locked": FlapLocking.LOCKED.value,
                "unlocked": FlapLocking.UNLOCKED.value,
            },
        ),
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SurePetCare lock for each matching device."""
    coordinator_data = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR]
    client = coordinator_data[KEY_API]

    entities = []
    for device_id, device_coordinator in coordinator_data[COORDINATOR_DICT].items():
        descriptions = LOCKS.get(device_coordinator.product_id, ())
        for description in descriptions:
            entities.append(
                SurePetCareLock(
                    device_coordinator,
                    client,
                    description=description,
                )
            )
    async_add_entities(entities, update_before_add=True)


class SurePetCareLock(SurePetCareBaseEntity, LockEntity):
    """Lock entity for SurePetCare device."""

    entity_description: SurePetCareLockEntityDescription

    def __init__(
        self,
        device_coordinator: SurePetCareDeviceDataUpdateCoordinator,
        client,
        description: SurePetCareLockEntityDescription,
    ) -> None:
        super().__init__(
            device_coordinator=device_coordinator,
            client=client,
        )
        self.entity_description = description
        self._attr_unique_id = f"{self._attr_unique_id}-{description.key}"

    @property
    def is_locked(self) -> bool:
        value = self._convert_value()
        if value is None or not self.entity_description.locked_states:
            return False
        return value == self.entity_description.locked_states["locked"]

    async def async_lock(self, **kwargs):
        if self.entity_description.field and hasattr(
            self.entity_description, "locked_states"
        ):
            await self.coordinator.client.api(
                self._device.set_control(
                    **{
                        self.entity_description.field: self.entity_description.locked_states[
                            "locked"
                        ]
                    }
                )
            )
        await self.coordinator.async_request_refresh()

    async def async_unlock(self, **kwargs):
        if self.entity_description.field and hasattr(
            self.entity_description, "locked_states"
        ):
            await self.coordinator.client.api(
                self._device.set_control(
                    **{
                        self.entity_description.field: self.entity_description.locked_states[
                            "unlocked"
                        ]
                    }
                )
            )
        await self.coordinator.async_request_refresh()
