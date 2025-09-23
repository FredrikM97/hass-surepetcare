"""Support for Sure Petcare schedule entities."""

from dataclasses import dataclass
from typing import Any
from surepcio import SurePetcareClient
from surepcio.enums import ProductId
from homeassistant.components.schedule import Schedule
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.schedule import WEEKDAY_TO_CONF

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.entity import EntityDescription
from .const import (
    COORDINATOR,
    COORDINATOR_DICT,
    DOMAIN,
    KEY_API,
)
from .coordinator import SurePetCareDeviceDataUpdateCoordinator
from .entity import (
    SurePetCareBaseEntity,
    SurePetCareBaseEntityDescription,
)


@dataclass(frozen=True, kw_only=True)
class SurePetCareScheduleEntityDescription(
    SurePetCareBaseEntityDescription, EntityDescription
):
    field: str
    multiple: bool = False
    mapping: dict[str, str] | None = None


SCHEDULES: dict[str, tuple[SurePetCareScheduleEntityDescription, ...]] = {
    ProductId.DUAL_SCAN_CONNECT: (
        SurePetCareScheduleEntityDescription(
            key="curfew",
            name="Curfew Schedule",
            field="control.curfew",
            multiple=True,
            mapping={"from": "lock_time", "to": "unlock_time", "data": "enabled"},
        ),
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator_data = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR]
    client = coordinator_data[KEY_API]
    entities = []
    for device_id, device_coordinator in coordinator_data[COORDINATOR_DICT].items():
        descriptions = SCHEDULES.get(device_coordinator.product_id, ())
        for description in descriptions:
            entities.append(
                SurePetCareSchedule(
                    device_coordinator,
                    client,
                    description=description,
                )
            )
    async_add_entities(entities, update_before_add=True)


class SurePetCareSchedule(SurePetCareBaseEntity, Schedule):
    """Entity representing a Sure Petcare schedule."""

    entity_description: SurePetCareScheduleEntityDescription

    def __init__(
        self,
        device_coordinator: SurePetCareDeviceDataUpdateCoordinator,
        client: SurePetcareClient,
        description: SurePetCareScheduleEntityDescription,
    ) -> None:
        super().__init__(device_coordinator=device_coordinator, client=client)
        self.device_coordinator = device_coordinator
        self.entity_description = description
        self._attr_name = description.name
        self._attr_unique_id = f"{self._attr_unique_id}-{description.key}"
        self._config: dict[str, list[dict[str, Any]]] = self._build_config()

    def _build_config(self) -> dict[str, list[dict[str, Any]]]:
        """Build the schedule config mapping weekdays to schedule entries."""
        schedule_data = self._convert_value()
        mapping = self.entity_description.mapping or {}
        config: dict[str, list[dict[str, Any]]] = {
            day: [] for day in WEEKDAY_TO_CONF.values()
        }
        if self.entity_description.multiple and isinstance(schedule_data, list):
            for entry in schedule_data:
                # Assume it to be used for every day
                for day_idx, day_name in WEEKDAY_TO_CONF.items():
                    config[day_name].append(
                        {
                            "from": entry.get(mapping.get("from")),
                            "to": entry.get(mapping.get("to")),
                            "data": entry.get(mapping.get("data")),
                        }
                    )
        else:
            # Single schedule entry
            for day_idx, day_name in WEEKDAY_TO_CONF.items():
                config[day_name].append(
                    {
                        "from": schedule_data.get(mapping.get("from")),
                        "to": schedule_data.get(mapping.get("to")),
                        "data": schedule_data.get(mapping.get("data")),
                    }
                )
        return config

    async def async_added_to_hass(self) -> None:
        """Called when entity is added to hass."""
        await super().async_added_to_hass()
        self._config = self._build_config()
