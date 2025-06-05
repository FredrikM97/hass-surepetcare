"""TODO."""

from collections.abc import Callable
from dataclasses import dataclass
import logging
from typing import Any, cast

from surepetcare.enums import ProductId

from .coordinator import (
    SurePetCareDeviceDataUpdateCoordinator,
)
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import COORDINATOR, COORDINATOR_LIST, DOMAIN, KEY_API
from .entity import SurePetCareBaseEntity

logger = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class SurePetCareBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes SurePetCare sensor entity."""

    value: Callable[[Any], Any | None]


SENSOR_DESCRIPTIONS_AVAILABLE: tuple[SurePetCareBinarySensorEntityDescription, ...] = (
    SurePetCareBinarySensorEntityDescription(
        key="connectivity",
        translation_key="connectivity",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value=lambda device: cast(bool, device.available),
    ),
)

SENSORS: dict[str, tuple[SurePetCareBinarySensorEntityDescription, ...]] = {
    ProductId.FEEDER_CONNECT: (*SENSOR_DESCRIPTIONS_AVAILABLE,),
    ProductId.DUAL_SCAN_PET_DOOR: (*SENSOR_DESCRIPTIONS_AVAILABLE,),
    ProductId.HUB: (*SENSOR_DESCRIPTIONS_AVAILABLE,),
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a Surepetcare config entry."""
    coordinator_data = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR]
    client = coordinator_data[KEY_API]
    coordinators_by_id = {
        str(coordinator.device.id): coordinator
        for coordinator in coordinator_data[COORDINATOR_LIST]
    }

    for subentry_id, subentry in config_entry.subentries.items():
        device_id = subentry.data.get("id")
        if not device_id:
            continue
        if coordinator := coordinators_by_id.get(device_id):
            descriptions = SENSORS.get(coordinator.device.product_id, ())
            if not descriptions:
                continue
            entities = []
            for description in descriptions:
                entities.append(
                    SurePetCareSensor(
                        coordinator,
                        client,
                        description=description,
                    )
                )

            async_add_entities(
                entities,
                update_before_add=True,
                config_subentry_id=subentry_id,
            )


class SurePetCareSensor(SurePetCareBaseEntity, BinarySensorEntity):
    """The platform class required by Home Assistant."""

    entity_description: SurePetCareBinarySensorEntityDescription

    def __init__(
        self,
        device_coordinator: SurePetCareDeviceDataUpdateCoordinator,
        client,
        description: SurePetCareBinarySensorEntityDescription,
    ) -> None:
        """Initialize a SurePetCare binary sensor."""
        super().__init__(
            device_coordinator=device_coordinator,
            client=client,
        )

        self.entity_description = description

        self._attr_unique_id = f"{self._attr_unique_id}-{description.key}"

        self._refresh()

    def _refresh(self) -> None:
        """Refresh the device."""
        self._attr_native_value = self.entity_description.value(self.coordinator.data)
