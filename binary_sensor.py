"""Binære sensorer: én per fraksjon, på fra dagen før kl. 13 til tømmedagen kl. 14."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from .const import BINARY_SENSOR_OFF_HOUR, BINARY_SENSOR_ON_HOUR, DOMAIN
from .coordinator import RemidtConfigEntry
from .entity import RemidtEntity

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RemidtConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Opprett én binær sensor per fraksjon, også for fraksjoner som dukker opp senere."""
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _add_new_fractions() -> None:
        if not coordinator.data:
            return
        new = [
            RemidtCollectionBinarySensor(coordinator, entry.title, fraction)
            for fraction in coordinator.data
            if fraction not in known
        ]
        if new:
            known.update(e.fraction for e in new)
            async_add_entities(new)

    _add_new_fractions()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_fractions))


class RemidtCollectionBinarySensor(RemidtEntity, BinarySensorEntity):
    """På når det er på tide å sette ut dunken for denne fraksjonen."""

    _attr_icon = "mdi:delete-alert"

    def __init__(self, coordinator, address_name: str, fraction: str) -> None:
        """Initialiser sensoren."""
        super().__init__(coordinator, address_name)
        self.fraction = fraction
        self._attr_name = f"{fraction.replace('_', ' ').title()} tømming"
        self._attr_unique_id = f"{DOMAIN}_{coordinator.address_id}_{fraction}_binary_sensor"

    async def async_added_to_hass(self) -> None:
        """Skriv ny tilstand ved midnatt og ved på-/av-tidspunktene."""
        await super().async_added_to_hass()
        for hour in (0, BINARY_SENSOR_ON_HOUR, BINARY_SENSOR_OFF_HOUR):
            self.async_on_remove(
                async_track_time_change(
                    self.hass, self._handle_time_update, hour=hour, minute=0, second=0
                )
            )

    @callback
    def _handle_time_update(self, now) -> None:
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        """Sann fra dagen før kl. BINARY_SENSOR_ON_HOUR til tømmedagen kl. BINARY_SENSOR_OFF_HOUR."""
        if not self.coordinator.data:
            return False

        now = dt_util.now()
        today = now.date()
        tomorrow = today + timedelta(days=1)

        for date_str in self.coordinator.data.get(self.fraction, []):
            try:
                collection_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                _LOGGER.warning("Invalid date format for %s: %s", self.fraction, date_str)
                continue
            if collection_date > tomorrow:
                break  # datoene er sortert
            if today == collection_date - timedelta(days=1) and now.hour >= BINARY_SENSOR_ON_HOUR:
                return True
            if today == collection_date and now.hour < BINARY_SENSOR_OFF_HOUR:
                return True
        return False
