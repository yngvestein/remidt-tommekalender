"""Platform for binary sensor integration."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary sensor platform."""
    _LOGGER.debug(
        "Starting async_setup_entry for binary sensor platform, entry %s", entry.entry_id
    )

    if DOMAIN not in hass.data or entry.entry_id not in hass.data[DOMAIN]:
        _LOGGER.error("Coordinator not found in hass.data for entry %s.", entry.entry_id)
        return

    coordinator = hass.data[DOMAIN][entry.entry_id]

    if not coordinator.data:
        _LOGGER.error("No data received for entry %s. Skipping entity creation.", entry.entry_id)
        return

    async_add_entities(
        [
            RemidtCollectionBinarySensor(coordinator, entry.title, fraction)
            for fraction in coordinator.data
        ],
        True,
    )


class RemidtCollectionBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor representing collection day status."""

    def __init__(self, coordinator, address_name: str, fraction: str) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.fraction = fraction
        fraction_display = fraction.replace("_", " ").title()
        self._attr_name = f"{fraction_display} tømming"
        self._attr_unique_id = f"{DOMAIN}_{coordinator.address_id}_{fraction}_binary_sensor"
        self._attr_icon = "mdi:delete-alert"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address_id)},
            name=f"Tømmekalender {address_name}",
            manufacturer="Remidt",
            model="Tømmekalender",
            sw_version="1.0",
        )

    @property
    def is_on(self) -> bool:
        """Return true from day before at 13:00 until collection day at 14:00."""
        if not self.coordinator.data:
            return False

        dates = self.coordinator.data.get(self.fraction, [])
        now = dt_util.now()
        today = now.date()
        tomorrow = today + timedelta(days=1)

        for date_str in dates:
            try:
                collection_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                _LOGGER.warning("Invalid date format for %s: %s", self.fraction, date_str)
                continue

            if collection_date > tomorrow:
                # Dates are sorted; no later date can match either
                break

            # Turn on day before at 13:00
            if today == collection_date - timedelta(days=1) and now.hour >= 13:
                return True
            # Active on collection day until 14:00
            if today == collection_date and now.hour < 14:
                return True

        return False

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success
