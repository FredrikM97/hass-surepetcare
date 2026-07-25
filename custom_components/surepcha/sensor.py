"""Support for Sure Petcare sensors."""

from dataclasses import dataclass
import logging
from types import MappingProxyType
from typing import Any

from surepcio.enums import ProductId, PetLocation
from surepcio.devices import Pet
from surepcio.devices.pet import PetPositionResource
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.const import PERCENTAGE, UnitOfMass, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.surepcha.method_field import MethodField

from .const import (
    DOMAIN,
    LOCATION_INSIDE,
    LOCATION_OUTSIDE,
    MANUAL_PROPERTIES,
    NAME,
    OPTION_DEVICES,
    PRODUCT_ID,
    OPTION_PROPERTIES,
)
from .coordinator import (
    SurePetCareDeviceDataUpdateCoordinator,
    SurePetCareTimelineCoordinator,
    SurePetcareConfigEntry,
)
from .entity import (
    SurePetCareBaseEntity,
    SurePetCareBaseEntityDescription,
)
from .helper import (
    abs_sum_attr,
    avg_attr,
    index_attr,
    option_name,
    stringify,
)
from .subentries import add_entities_by_household
from .timeline import PetFeedingStats

logger = logging.getLogger(__name__)


def get_device_location(entry_options, position, key, default):
    """Return reconfigured location for device, or default."""
    return (
        entry_options[OPTION_DEVICES].get(str(position.device_id), {}).get(key, default)
    )


def get_manual_location(entry_options, position):
    """Return reconfigured manual location name for device, or default."""
    return (
        entry_options[OPTION_PROPERTIES]
        .get(MANUAL_PROPERTIES, {})
        .get(position.where.name.lower(), position.where.name.lower())
    )


def get_location(
    device: Pet, entry_options: MappingProxyType[str, Any]
) -> PetLocation | str | None:
    """Return PetLocation, or None if unknown.

    Uses reconfigured values for location_inside/location_outside if available.
    """
    position: PetPositionResource = getattr(device.status, "activity", None)

    if position is not None:
        if position.where == PetLocation.INSIDE:
            return get_device_location(
                entry_options,
                position,
                LOCATION_INSIDE,
                get_manual_location(entry_options, position),
            )
        elif position.where == PetLocation.OUTSIDE:
            return get_device_location(
                entry_options,
                position,
                LOCATION_OUTSIDE,
                get_manual_location(entry_options, position),
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
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        field=MethodField(path="battery_level"),
    ),
)

SENSOR_DESCRIPTIONS_DEVICE_INFORMATION: tuple[
    SurePetCareSensorEntityDescription, ...
] = (
    SurePetCareSensorEntityDescription(
        key="entity_information",
        translation_key="entity_information",
        icon="mdi:information",
        field=MethodField(
            path=NAME,
            get_extra_fn=lambda ctx: {
                "household_id": str(ctx.device.household_id),
                "id": str(ctx.device.id),
                "parent_device_id": stringify(ctx.device.entity_info.parent_device_id),
                "photo": ctx.device.photo,
            },
            entity_picture="photo",
        ),
    ),
)

SENSOR_DESCRIPTIONS_RSSI: tuple[SurePetCareSensorEntityDescription, ...] = (
    SurePetCareSensorEntityDescription(
        key="rssi",
        translation_key="rssi",
        native_unit_of_measurement="dBm",
        field=MethodField(
            get_fn=lambda ctx: ctx.device.status.signal.device_rssi,
        ),
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)

SENSOR_DESCRIPTIONS_PET_INFORMATION: tuple[SurePetCareSensorEntityDescription, ...] = (
    SurePetCareSensorEntityDescription(
        key="entity_information",
        translation_key="entity_information",
        icon="mdi:information",
        field=MethodField(
            path=NAME,
            get_extra_fn=lambda ctx: {
                "household_id": str(ctx.device.household_id),
                PRODUCT_ID: ctx.device.product_id,
                "tag": str(ctx.device.tag),
                "id": str(ctx.device.id),
                "parent_device_id": stringify(ctx.device.entity_info.parent_device_id),
                "photo": ctx.device.photo,
            },
            entity_picture="photo",
        ),
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
            field=MethodField(
                path="status.bowl_status[0].current_weight",
                get_extra_fn=lambda ctx: {
                    "position": ctx.device.status.bowl_status[0].position.name.lower(),
                    "food_type": ctx.device.control.bowls.settings[
                        0
                    ].food_type.name.lower(),
                    "last_filled_at": ctx.device.status.bowl_status[0].last_filled_at,
                    "last_zeroed_at": ctx.device.status.bowl_status[0].last_zeroed_at,
                    "last_fill_weight": ctx.device.status.bowl_status[
                        0
                    ].last_fill_weight,
                },
            ),
        ),
        SurePetCareSensorEntityDescription(
            key="bowl_1_weight",
            translation_key="bowl_weight",
            translation_placeholders={"bowl": "Two"},
            state_class=SensorStateClass.MEASUREMENT,
            device_class=SensorDeviceClass.WEIGHT,
            native_unit_of_measurement=UnitOfMass.GRAMS,
            field=MethodField(
                path="status.bowl_status[1].current_weight",
                get_extra_fn=lambda ctx: {
                    "position": ctx.device.status.bowl_status[1].position.name.lower(),
                    "food_type": ctx.device.control.bowls.settings[
                        1
                    ].food_type.name.lower(),
                    "substance_type": ctx.device.status.bowl_status[1].substance_type,
                    "last_filled_at": ctx.device.status.bowl_status[1].last_filled_at,
                    "last_zeroed_at": ctx.device.status.bowl_status[1].last_zeroed_at,
                    "last_fill_weight": ctx.device.status.bowl_status[
                        1
                    ].last_fill_weight,
                },
            ),
        ),
        SurePetCareSensorEntityDescription(
            key="fill_percent",
            translation_key="fill_percent",
            icon="mdi:percent-outline",
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=PERCENTAGE,
            suggested_display_precision=1,
            field=MethodField(
                path="status.fill_percentages.total",
                get_extra_fn=lambda ctx: (
                    {
                        f"bowl_{i}_fill_percent": percent
                        for i, percent in (
                            ctx.device.status.fill_percentages.get("per_bowl", {}) or {}
                        ).items()
                    }
                    if ctx.device.status.fill_percentages
                    else {}
                ),
            ),
        ),
        SurePetCareSensorEntityDescription(
            key="weight_capacity",
            translation_key="weight_capacity",
            state_class=SensorStateClass.MEASUREMENT,
            device_class=SensorDeviceClass.WEIGHT,
            native_unit_of_measurement=UnitOfMass.GRAMS,
            field=MethodField(
                get_fn=lambda ctx: sum(
                    w.target
                    for w in getattr(
                        getattr(getattr(ctx.device, "control"), "bowls"), "settings", []
                    )
                ),
                get_extra_fn=lambda ctx: {
                    "bowls_0_target": index_attr(
                        ctx.device.control.bowls.settings, 0, attr="target"
                    ),
                    "bowls_1_target": index_attr(
                        ctx.device.control.bowls.settings, 1, attr="target"
                    ),
                },
            ),
        ),
        *SENSOR_DESCRIPTIONS_RSSI,
        *SENSOR_DESCRIPTIONS_BATTERY,
        *SENSOR_DESCRIPTIONS_DEVICE_INFORMATION,
    ),
    ProductId.DUAL_SCAN_PET_DOOR: (
        *SENSOR_DESCRIPTIONS_RSSI,
        *SENSOR_DESCRIPTIONS_BATTERY,
        *SENSOR_DESCRIPTIONS_DEVICE_INFORMATION,
    ),
    ProductId.DUAL_SCAN_CONNECT: (
        *SENSOR_DESCRIPTIONS_RSSI,
        *SENSOR_DESCRIPTIONS_BATTERY,
        *SENSOR_DESCRIPTIONS_DEVICE_INFORMATION,
    ),
    ProductId.PET_DOOR: (
        *SENSOR_DESCRIPTIONS_RSSI,
        *SENSOR_DESCRIPTIONS_BATTERY,
        *SENSOR_DESCRIPTIONS_DEVICE_INFORMATION,
    ),
    ProductId.POSEIDON_CONNECT: (
        SurePetCareSensorEntityDescription(
            key="bowl_volume",
            translation_key="bowl_volume",
            translation_placeholders={"bowl": ""},
            device_class=SensorDeviceClass.VOLUME_STORAGE,
            native_unit_of_measurement=UnitOfVolume.MILLILITERS,
            field=MethodField(
                path="status.bowl_status[0].current_weight",
                get_extra_fn=lambda ctx: {
                    "last_filled_at": ctx.device.status.bowl_status[0].last_filled_at,
                    "last_zeroed_at": ctx.device.status.bowl_status[
                        0
                    ].last_zeroed_at,  # Remove this later
                    "last_fill_weight": ctx.device.status.bowl_status[
                        0
                    ].last_fill_weight,
                },
            ),
        ),
        SurePetCareSensorEntityDescription(
            key="fill_percent",
            translation_key="fill_percent",
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=PERCENTAGE,
            field=MethodField(
                get_fn=lambda ctx: avg_attr(
                    getattr(ctx.device.status, "bowl_status", []), "fill_percent"
                ),
            ),
        ),
        SurePetCareSensorEntityDescription(
            key="last_filled_at",
            translation_key="last_filled_at",
            field=MethodField(
                get_fn=lambda ctx: ctx.device.status.bowl_status[0].last_filled_at,
            ),
        ),
        SurePetCareSensorEntityDescription(
            key="last_zeroed_at",
            translation_key="last_zeroed_at",
            field=MethodField(
                get_fn=lambda ctx: ctx.device.status.bowl_status[0].last_zeroed_at,
            ),
        ),
        *SENSOR_DESCRIPTIONS_RSSI,
        *SENSOR_DESCRIPTIONS_BATTERY,
        *SENSOR_DESCRIPTIONS_DEVICE_INFORMATION,
    ),
    ProductId.HUB: (),
    ProductId.PET: (
        SurePetCareSensorEntityDescription(
            key="feeding",
            translation_key="feeding",
            icon="mdi:food-drumstick",
            device_class=SensorDeviceClass.WEIGHT,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfMass.GRAMS,
            entity_registry_enabled_default=False,
            field=MethodField(
                get_fn=lambda ctx: abs_sum_attr(ctx.device.status.feeding, "change"),
                get_extra_fn=lambda ctx: {
                    "device_id": str(ctx.device.status.feeding.device_id),
                    "id": str(ctx.device.status.feeding.id),
                    "at": ctx.device.status.feeding.at,
                    "tag_id": str(ctx.device.status.feeding.tag_id),
                    "change_0": abs(
                        index_attr(ctx.device.status.feeding.change, 0, default=0)
                    ),
                    "change_1": abs(
                        index_attr(ctx.device.status.feeding.change, 1, default=0)
                    ),
                },
            ),
        ),
        SurePetCareSensorEntityDescription(
            key="position",
            translation_key="position",
            icon="mdi:map-marker",
            entity_registry_enabled_default=False,
            field=MethodField(
                get_fn=lambda ctx: get_location(ctx.device, ctx.options),
                get_extra_fn=lambda ctx: {
                    "device_id": str(ctx.device.status.activity.device_id),
                    "id": str(ctx.device.status.activity.id),
                    "since": ctx.device.status.activity.since,
                    "where": ctx.device.status.activity.where,
                    "tag_id": str(ctx.device.status.activity.tag_id),
                },
            ),
        ),
        SurePetCareSensorEntityDescription(
            key="drinking",
            translation_key="drinking",
            icon="mdi:water",
            state_class=SensorStateClass.TOTAL,
            device_class=SensorDeviceClass.VOLUME,
            native_unit_of_measurement=UnitOfVolume.MILLILITERS,
            entity_registry_enabled_default=False,
            field=MethodField(
                get_fn=lambda ctx: abs_sum_attr(ctx.device.status.drinking, "change"),
                get_extra_fn=lambda ctx: {
                    "device_id": str(ctx.device.status.drinking.device_id),
                    "id": str(ctx.device.status.drinking.id),
                    "at": ctx.device.status.drinking.at,
                    "tag_id": str(ctx.device.status.drinking.tag_id),
                    "change_0": abs(
                        index_attr(ctx.device.status.drinking.change, 0, default=0)
                    ),
                    "change_1": abs(
                        index_attr(ctx.device.status.drinking.change, 1, default=0)
                    ),
                },
            ),
        ),
        SurePetCareSensorEntityDescription(
            key="devices",
            translation_key="devices",
            icon="mdi:devices",
            native_unit_of_measurement="pcs",
            field=MethodField(
                path="status.devices.count",
                get_extra_fn=lambda ctx: {
                    "devices": [
                        str(item.id) for item in ctx.device.status.devices.items
                    ]
                },
            ),
        ),
        SurePetCareSensorEntityDescription(
            key="last_activity",
            translation_key="last_activity",
            icon="mdi:history",
            entity_registry_enabled_default=False,
            field=MethodField(
                get_fn=lambda ctx: (
                    option_name(ctx.options, ctx.device.status.last_activity.device_id)
                    if ctx.device.status.last_activity
                    else None
                ),
                get_extra_fn=lambda ctx: (
                    {"device": str(ctx.device.status.last_activity.device_id)}
                    if ctx.device.status.last_activity
                    else {}
                ),
            ),
        ),
        *SENSOR_DESCRIPTIONS_PET_INFORMATION,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SurePetcareConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up SurePetCare sensors for each matching device."""
    coordinators = entry.runtime_data

    entities: list[SensorEntity] = [
        SurePetCareSensor(
            coordinator,
            description=description,
        )
        for coordinator in coordinators
        for description in SENSORS.get(coordinator.product_id, ())
    ]

    pet_photos = {
        coordinator.data.id: coordinator.data.photo
        for coordinator in coordinators
        if coordinator.product_id == ProductId.PET
    }
    device_photos = {
        coordinator.data.id: coordinator.data.photo for coordinator in coordinators
    }

    timeline_coordinators: dict[int, SurePetCareTimelineCoordinator] = {}
    for coordinator in coordinators:
        if coordinator.product_id != ProductId.PET:
            continue
        household_id = coordinator.data.household_id
        timeline_coordinator = timeline_coordinators.get(household_id)
        if timeline_coordinator is None:
            timeline_coordinator = SurePetCareTimelineCoordinator(
                hass, entry, coordinator.client, household_id
            )
            await timeline_coordinator.async_config_entry_first_refresh()
            timeline_coordinators[household_id] = timeline_coordinator

            entities.append(
                SurePetCareHouseholdActivitySensor(
                    timeline_coordinator, household_id, pet_photos, device_photos
                )
            )
        entities.append(
            SurePetCareFeedingsTodaySensor(coordinator, timeline_coordinator)
        )
        entities.append(SurePetCareFoodTodaySensor(coordinator, timeline_coordinator))

    add_entities_by_household(async_add_entities, entry, entities)


class SurePetCareSensor(SurePetCareBaseEntity, SensorEntity):
    """The platform class required by Home Assistant."""

    entity_description: SurePetCareSensorEntityDescription

    def __init__(
        self,
        coordinator: SurePetCareDeviceDataUpdateCoordinator,
        description: SurePetCareSensorEntityDescription,
    ) -> None:
        """Initialize a Surepetcare sensor."""
        super().__init__(
            coordinator=coordinator,
        )
        self.entity_description = description
        self._attr_unique_id = f"{coordinator._device.id}-{description.key}"

    @property
    def entity_picture(self) -> str | None:
        """Return the entity picture URL to use for the entity."""
        if entity_picture := self.entity_description.field.get_entity_picture(
            self._device
        ):
            return entity_picture
        return None


class SurePetCareTimelineSensorBase(
    CoordinatorEntity[SurePetCareDeviceDataUpdateCoordinator], SensorEntity
):
    """Base for per-pet sensors backed by the household timeline coordinator."""

    _attr_has_entity_name = True
    _key: str

    def __init__(
        self,
        pet_coordinator: SurePetCareDeviceDataUpdateCoordinator,
        timeline_coordinator: SurePetCareTimelineCoordinator,
    ) -> None:
        """Initialize a timeline-backed sensor."""
        super().__init__(pet_coordinator)
        self._pet = pet_coordinator.data
        self._household_id: int | None = self._pet.household_id
        self._timeline_coordinator = timeline_coordinator
        self._attr_unique_id = f"{self._pet.id}-{self._key}"
        self._attr_translation_key = self._key

    async def async_added_to_hass(self) -> None:
        """Also refresh when the household timeline coordinator updates."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._timeline_coordinator.async_add_listener(
                self._handle_coordinator_update
            )
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return a device description for device registry."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._pet.id}")},
            manufacturer="SurePetCare",
            model=self._pet.product_name,
            model_id=str(self._pet.product_id),
            name=self._pet.name,
        )

    @property
    def _stats(self) -> PetFeedingStats:
        """Return today's feeding stats for this pet (zeroed if none yet)."""
        data = self._timeline_coordinator.data
        feeding_stats = data.feeding_stats if data else {}
        return feeding_stats.get(self._pet.id, PetFeedingStats())

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available and self._timeline_coordinator.last_update_success

    def _events_attribute(self) -> list[dict[str, Any]]:
        """Return today's individual feeding events, for use in graphing cards."""
        return [
            {
                "at": event["at"].isoformat(),
                "device_id": event["device_id"],
                "grams": event["grams"],
                "wet_grams": event["wet_grams"],
                "dry_grams": event["dry_grams"],
                "duration_seconds": event["duration_seconds"],
            }
            for event in self._stats.events
        ]


class SurePetCareFeedingsTodaySensor(SurePetCareTimelineSensorBase):
    """Number of feeder visits for a pet since local midnight."""

    _key = "feedings_today"
    _attr_icon = "mdi:counter"
    _attr_native_unit_of_measurement = "feedings"
    # Monotonically increases through the day, hard-resets to 0 at local
    # midnight - TOTAL_INCREASING lets the recorder auto-detect that reset
    # (via the drop itself) and carry the long-term sum forward correctly.
    # Plain TOTAL only detects resets via an explicit last_reset attribute,
    # which we don't provide - without it the midnight drop gets recorded as
    # a literal decrease and silently corrupts the running statistics sum.
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    @property
    def native_value(self) -> int:
        """Return the number of feedings today."""
        return self._stats.count

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return today's individual feeding events for graphing."""
        return {
            "total_grams": self._stats.total_grams,
            "events": self._events_attribute(),
        }


class SurePetCareFoodTodaySensor(SurePetCareTimelineSensorBase):
    """Total grams eaten by a pet since local midnight."""

    _key = "food_today"
    _attr_icon = "mdi:food-drumstick"
    _attr_device_class = SensorDeviceClass.WEIGHT
    _attr_native_unit_of_measurement = UnitOfMass.GRAMS
    # See SurePetCareFeedingsTodaySensor for why TOTAL_INCREASING (not TOTAL).
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    @property
    def native_value(self) -> float:
        """Return the total grams eaten today."""
        return self._stats.total_grams

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return today's individual feeding events for graphing."""
        return {
            "count": self._stats.count,
            "total_wet_grams": self._stats.total_wet_grams,
            "total_dry_grams": self._stats.total_dry_grams,
            "events": self._events_attribute(),
        }


class SurePetCareHouseholdActivitySensor(
    CoordinatorEntity[SurePetCareTimelineCoordinator], SensorEntity
):
    """Household-wide chronological feed of feeding and bowl-maintenance activity today."""

    _attr_has_entity_name = True
    _attr_translation_key = "household_activity_today"
    _attr_icon = "mdi:timeline-clock-outline"
    _attr_native_unit_of_measurement = "events"
    # See SurePetCareFeedingsTodaySensor for why TOTAL_INCREASING (not TOTAL).
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(
        self,
        timeline_coordinator: SurePetCareTimelineCoordinator,
        household_id: int,
        pet_photos: dict[int, str | None],
        device_photos: dict[int, str | None],
    ) -> None:
        """Initialize the household activity sensor."""
        super().__init__(timeline_coordinator)
        self._household_id = household_id
        self._pet_photos = pet_photos
        self._device_photos = device_photos
        self._attr_unique_id = f"household-{household_id}-activity_today"

    @property
    def device_info(self) -> DeviceInfo:
        """Return a device description for the household itself."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"household-{self._household_id}")},
            manufacturer="SurePetCare",
            model="Household",
            name=self.coordinator.household_name or f"Household {self._household_id}",
        )

    @property
    def native_value(self) -> int:
        """Return the number of activity events recorded today."""
        data = self.coordinator.data
        return len(data.activity) if data else 0

    def _pet_photo(self, pet_id: int | None) -> str | None:
        """Return the pet's photo URL, if this event is tied to a known pet."""
        return self._pet_photos.get(pet_id) if pet_id is not None else None

    def _device_photo(self, device_id: int | None) -> str | None:
        """Return the device's photo URL, if this event is tied to a known device."""
        return self._device_photos.get(device_id) if device_id is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return today's combined feeding and bowl-maintenance activity feed."""
        data = self.coordinator.data
        events = data.activity if data else []
        return {
            "events": [
                {
                    **{key: value for key, value in event.items() if key != "at"},
                    "at": event["at"].isoformat(),
                    "pet_photo": self._pet_photo(event.get("pet_id")),
                    "device_photo": self._device_photo(event.get("device_id")),
                }
                for event in events
            ]
        }
