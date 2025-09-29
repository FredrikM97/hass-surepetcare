"""Support for Sure Petcare binary sensors."""

from dataclasses import dataclass
from datetime import datetime
import logging
from typing import cast

from surepcio.enums import ProductId
from surepcio.devices.device import SurePetCareBase
from surepcio.devices.dual_scan_connect import Curfew
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import COORDINATOR, COORDINATOR_DICT, DOMAIN, KEY_API
from .coordinator import SurePetCareDeviceDataUpdateCoordinator
from .entity import (
    SurePetCareBaseEntity,
    SurePetCareBaseEntityDescription,
)

logger = logging.getLogger(__name__)


def _next_enabled_future_curfew(device: SurePetCareBase, r: ConfigEntry) -> bool | None:
    curfews: list[Curfew] | Curfew = device.control.curfew

    if curfews is None:
        return None

    if not isinstance(curfews, list):
        curfews = [curfews]

    now = datetime.now().time()
    return any(c.enabled and c.lock_time <= now <= c.unlock_time for c in curfews)


@dataclass(frozen=True, kw_only=True)
class SurePetCareBinarySensorEntityDescription(
    SurePetCareBaseEntityDescription, BinarySensorEntityDescription
):
    """Describes SurePetCare.binary_sensor entity."""


SENSOR_DESCRIPTIONS_AVAILABLE: tuple[SurePetCareBinarySensorEntityDescription, ...] = (
    SurePetCareBinarySensorEntityDescription(
        key="connectivity",
        translation_key="connectivity",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        field="available",
    ),
)

SENSORS: dict[str, tuple[SurePetCareBinarySensorEntityDescription, ...]] = {
    ProductId.FEEDER_CONNECT: (
        SurePetCareBinarySensorEntityDescription(
            key="learn_mode",
            translation_key="learn_mode",
            field="status.learn_mode",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        ),
        *SENSOR_DESCRIPTIONS_AVAILABLE,
    ),
    ProductId.DUAL_SCAN_CONNECT: (
        SurePetCareBinarySensorEntityDescription(
            key="learn_mode",
            translation_key="learn_mode",
            field="status.learn_mode",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        ),
        SurePetCareBinarySensorEntityDescription(
            key="curfew",
            translation_key="curfew_active",
            field_fn=_next_enabled_future_curfew,
            extra_field="control.curfew",
        ),
        *SENSOR_DESCRIPTIONS_AVAILABLE,
    ),
    ProductId.PET_DOOR: (
        SurePetCareBinarySensorEntityDescription(
            key="learn_mode",
            translation_key="learn_mode",
            field="status.learn_mode",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
        ),
        SurePetCareBinarySensorEntityDescription(
            key="curfew",
            translation_key="curfew_active",
            field_fn=_next_enabled_future_curfew,
            extra_field="control.curfew",
        ),
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

    entities = []
    for device_coordinator in coordinator_data[COORDINATOR_DICT].values():
        descriptions = SENSORS.get(device_coordinator.product_id, ())
        entities.extend(
            [
                SurePetCareBinarySensor(
                    device_coordinator,
                    client,
                    description=description,
                )
                for description in descriptions
            ]
        )
    async_add_entities(entities, update_before_add=True)


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
        return cast(bool, self._convert_value())
