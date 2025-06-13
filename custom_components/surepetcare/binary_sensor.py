"""TODO."""

from collections.abc import Callable
from dataclasses import dataclass
import logging
from typing import Any, cast

from surepetcare.enums import ProductId

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import COORDINATOR, COORDINATOR_DICT, DOMAIN, KEY_API
from .coordinator import SurePetCareDeviceDataUpdateCoordinator
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
    ProductId.FEEDER_CONNECT: (
        SurePetCareBinarySensorEntityDescription(
            key="learn_mode",
            translation_key="learn_mode",
            value=lambda device: device.raw_data["status"]["learn_mode"],
        ),
        *SENSOR_DESCRIPTIONS_AVAILABLE,
    ),
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

    for subentry_id, subentry in config_entry.subentries.items():
        device_id = subentry.data.get("id")
        if not device_id:
            continue
        if device_coordinator := coordinator_data[COORDINATOR_DICT].get(device_id):
            descriptions = SENSORS.get(device_coordinator.product_id, ())
            if not descriptions:
                continue
            entities = []
            for description in descriptions:
                entities.append(
                    SurePetCareBinarySensor(
                        device_coordinator,
                        client,
                        description=description,
                    )
                )

            async_add_entities(
                entities,
                update_before_add=True,
                config_subentry_id=subentry_id,
            )


class SurePetCareBinarySensor(SurePetCareBaseEntity, BinarySensorEntity):
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

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        return self.entity_description.value(self.coordinator.data)
