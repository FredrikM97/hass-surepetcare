"""Support for Sure Petcare sensors."""

from dataclasses import dataclass
import logging
from typing import cast

from surepcio import SurePetcareClient
from surepcio.enums import ProductId, PetLocation
from surepcio.devices import Pet
from surepcio.devices.pet import PetPositionResource
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfMass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback


from .const import (
    COORDINATOR,
    COORDINATOR_DICT,
    DOMAIN,
    KEY_API,
    LOCATION_INSIDE,
    LOCATION_OUTSIDE,
    OPTION_DEVICES,
)
from .coordinator import SurePetCareDeviceDataUpdateCoordinator
from .entity import (
    SurePetCareBaseEntity,
    SurePetCareBaseEntityDescription,
)

logger = logging.getLogger(__name__)


def get_location(device: Pet, reconfig) -> PetLocation | str | None:
    """Return PetLocation, or None if unknown.

    Uses reconfigured values for location_inside/location_outside if available.
    """
    position: PetPositionResource = getattr(device.status, "activity", None)

    if position is not None:
        if position.where == PetLocation.INSIDE:
            return (
                reconfig[OPTION_DEVICES]
                .get(str(position.device_id), {})
                .get(LOCATION_INSIDE, position.where)
            )
        elif position.where == PetLocation.OUTSIDE:
            return (
                reconfig[OPTION_DEVICES]
                .get(str(position.device_id), {})
                .get(LOCATION_OUTSIDE, position.where)
            )

    return None


@dataclass(frozen=True, kw_only=True)
class SurePetCareSensorEntityDescription(
    SurePetCareBaseEntityDescription, SensorEntityDescription
):
    """Describes SurePetCare sensor entity."""


SENSOR_DESCRIPTIONS_BATTERY: tuple[SurePetCareSensorEntityDescription, ...] = (
    SurePetCareSensorEntityDescription(
        key="battery_level",
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        field_fn= lambda device, r: device.battery_level,
    ),
)

SENSOR_DESCRIPTIONS_DEVICE_INFORMATION: tuple[
    SurePetCareSensorEntityDescription, ...
] = (
    SurePetCareSensorEntityDescription(
        key="entity_information",
        translation_key="entity_information",
        icon="mdi:information",
        field_fn= lambda device, r: device.name,
        extra_fn=lambda device, r:{
            "household_id": device.household_id,
            "product_id": device.product_id,
            "id": device.id,
            "parent_device_id": device.entity_info.parent_device_id,
        },
    ),
)

SENSOR_DESCRIPTIONS_PET_INFORMATION: tuple[SurePetCareSensorEntityDescription, ...] = (
    SurePetCareSensorEntityDescription(
        key="entity_information",
        translation_key="entity_information",
        icon="mdi:information",
        field_fn=lambda device, r: device.name,
        extra_fn=lambda device, r:{
            "household_id": device.household_id,
            "product_id": device.product_id,
            "tag": device.tag,
            "id": device.id,
            "parent_device_id": device.entity_info.parent_device_id,
        },
    ),
)

SENSORS: dict[str, tuple[SurePetCareSensorEntityDescription, ...]] = {
    ProductId.FEEDER_CONNECT: (
        SurePetCareSensorEntityDescription(
            key="bowl_0_weight",
            translation_key="bowl_weight",
            translation_placeholders={"bowl": "One"},
            state_class=SensorStateClass.MEASUREMENT,
            device_class=SensorDeviceClass.WEIGHT,
            native_unit_of_measurement=UnitOfMass.GRAMS,
            field_fn=lambda device, r: device.status.bowl_status[0].current_weight,
            extra_fn= lambda device, r: {
                "position": device.status.bowl_status[0].position.name,
                "food_type": device.status.bowl_status[0].food_type.name,
                "substance_type":  device.status.bowl_status[0].substance_type,
                "last_filled_at":  device.status.bowl_status[0].last_filled_at,
                "last_zeroed_at": device.status.bowl_status[0].last_zeroed_at,
                "last_fill_weight":  device.status.bowl_status[0].last_fill_weight
            }
        ),
        SurePetCareSensorEntityDescription(
            key="bowl_1_weight",
            translation_key="bowl_weight",
            translation_placeholders={"bowl": "Two"},
            state_class=SensorStateClass.MEASUREMENT,
            device_class=SensorDeviceClass.WEIGHT,
            native_unit_of_measurement=UnitOfMass.GRAMS,
            field_fn= lambda device, r: device.status.bowl_status[1].current_weight,
            extra_fn= lambda device, r: {
                "position": device.status.bowl_status[1].position.name,
                "food_type": device.status.bowl_status[1].food_type.name,
                "substance_type": device.status.bowl_status[1].substance_type,
                "last_filled_at": device.status.bowl_status[1].last_filled_at,
                "last_zeroed_at": device.status.bowl_status[1].last_zeroed_at,
                "last_fill_weight": device.status.bowl_status[1].last_fill_weight,
            }
        ),
        SurePetCareSensorEntityDescription(
            key="fill_percent",
            translation_key="fill_percent",
            state_class=SensorStateClass.MEASUREMENT,
            field_fn=lambda device, r: sum(
                v for v in (
                    getattr(bowl, "fill_percent", 0)
                    for bowl in (getattr(device.status, "bowl_status", []) or [])
                    if bowl is not None
                ) if isinstance(v, (int, float)) and v is not None
            ),
            extra_fn=lambda device, r: (
                lambda bowl_status: {
                    "bowl_0_fill_percent": bowl_status[0].fill_percent if len(bowl_status) > 0 else None,
                    "bowl_1_fill_percent": bowl_status[1].fill_percent if len(bowl_status) > 1 else None,
                }
            )(getattr(device.status, "bowl_status", []))
        ),
        SurePetCareSensorEntityDescription(
            key="weight_capacity",
            translation_key="weight_capacity",
            state_class=SensorStateClass.MEASUREMENT,
            field_fn=lambda device, r: sum(w.target for w in device.control.bowls.settings),
            extra_fn=lambda device, r:{"bowls": device.control.bowls.settings},
        ),
        SurePetCareSensorEntityDescription(
            key="rssi",
            translation_key="rssi",
            field_fn=lambda device, r: device.status.signal.device_rssi,
        ),
        *SENSOR_DESCRIPTIONS_BATTERY,
        *SENSOR_DESCRIPTIONS_DEVICE_INFORMATION,
    ),
    ProductId.DUAL_SCAN_PET_DOOR: (
        *SENSOR_DESCRIPTIONS_BATTERY,
        *SENSOR_DESCRIPTIONS_DEVICE_INFORMATION,
    ),
    ProductId.DUAL_SCAN_CONNECT: (
        *SENSOR_DESCRIPTIONS_BATTERY,
        *SENSOR_DESCRIPTIONS_DEVICE_INFORMATION,
    ),
    ProductId.PET_DOOR: (
        *SENSOR_DESCRIPTIONS_BATTERY,
        *SENSOR_DESCRIPTIONS_DEVICE_INFORMATION,
    ),
    ProductId.POSEIDON_CONNECT: (
        *SENSOR_DESCRIPTIONS_BATTERY,
        *SENSOR_DESCRIPTIONS_DEVICE_INFORMATION,
    ),
    ProductId.HUB: (),
    ProductId.PET: (
        SurePetCareSensorEntityDescription(
            key="feeding",
            translation_key="feeding",
            device_class=SensorDeviceClass.WEIGHT,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfMass.GRAMS,
            field_fn=lambda device, r: abs(change[0])
            if (change := getattr(device.status.feeding, "change", []))
            else None,
            extra_fn=lambda device, r:{
                "device_id": device.status.feeding.device_id,
                "id": device.status.feeding.id,
                "at": device.status.feeding.at,
                "tag_id": device.status.feeding.tag_id,
            },
        ),
        SurePetCareSensorEntityDescription(
            key="position",
            translation_key="position",
            field_fn=get_location,
            extra_fn=lambda device, r: {
                "device_id": device.status.activity.device_id,
                "id": device.status.activity.id,
                "since": device.status.activity.since,
                "where": device.status.activity.where,
                "tag_id": device.status.activity.tag_id,
            },
        ),
        SurePetCareSensorEntityDescription(
            key="drinking",
            translation_key="drinking",
            device_class=SensorDeviceClass.WEIGHT,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfMass.GRAMS,
            field_fn=lambda device, r: abs(change[0])
            if (change := getattr(device.status.drinking, "change", []))
            else None,
            extra_fn=lambda device, r: {
                "device_id": device.status.drinking.device_id,
                "id": device.status.drinking.id,
                "at": device.status.drinking.at,
                "tag_id": device.status.drinking.tag_id,
            },
        ),
        SurePetCareSensorEntityDescription(
            key="devices",
            translation_key="devices",
            field_fn=lambda device, r: len(getattr(device.status, "devices", []) or []),
            extra_fn=lambda device, r: {"devices": [d.id for d in getattr(device.status, "devices", [])]},
        ),
        SurePetCareSensorEntityDescription(
            key="last_activity",
            translation_key="last_activity",
            field_fn=lambda device, r: r[OPTION_DEVICES]
            .get(str(device.last_activity()[1]), {})
            .get("name"),
        ),
        *SENSOR_DESCRIPTIONS_PET_INFORMATION,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up SurePetCare sensors for each matching device."""
    coordinator_data = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR]
    client = coordinator_data[KEY_API]

    entities = []
    for device_id, device_coordinator in coordinator_data[COORDINATOR_DICT].items():
        descriptions = SENSORS.get(device_coordinator.product_id, ())
        for description in descriptions:
            entities.append(
                SurePetCareSensor(
                    device_coordinator,
                    client,
                    description=description,
                )
            )
    async_add_entities(entities, update_before_add=True)


class SurePetCareSensor(SurePetCareBaseEntity, SensorEntity):
    """The platform class required by Home Assistant."""

    entity_description: SurePetCareSensorEntityDescription

    def __init__(
        self,
        device_coordinator: SurePetCareDeviceDataUpdateCoordinator,
        client: SurePetcareClient,
        description: SurePetCareSensorEntityDescription,
    ) -> None:
        """Initialize a Surepetcare sensor."""
        super().__init__(
            device_coordinator=device_coordinator,
            client=client,
        )
        self.entity_description = description
        self._attr_unique_id = f"{self._attr_unique_id}-{description.key}"

        
    @property
    def entity_picture(self) -> str | None:
        """Return the entity picture URL."""
        if self.entity_description.icon:
            return self.coordinator.data.photo
        return None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            cast(bool, self._device.available)
            and self._convert_value() is not None
            and super().available
        )
