"""Platform for sensor integration."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util
from aiohttp import ClientError

from .const import (
    DOMAIN,
    DEFAULT_UPDATE_INTERVAL_DAYS,
    HISTORY_RETENTION_DAYS,
    clean_fraction_name,
    days_until,
    format_days_remaining,
    calculate_cycle_progress,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    _LOGGER.debug("Starting async_setup_entry for sensor platform, entry %s", entry.entry_id)
    address_name = entry.title

    coordinator = hass.data[DOMAIN][entry.entry_id]

    if not coordinator.data:
        _LOGGER.error("No data received for address %s. Skipping entity creation.", address_name)
        return

    async_add_entities([RemidtTommekalenderSensor(coordinator, address_name)], True)
    _LOGGER.debug("Finished async_setup_entry for sensor platform, entry %s", entry.entry_id)


class RemidtTommekalenderCoordinator(DataUpdateCoordinator):
    """Coordinator to fetch data from the API."""

    def __init__(
        self,
        hass: HomeAssistant,
        address_id: str,
        update_interval_days: int = DEFAULT_UPDATE_INTERVAL_DAYS,
        store=None,
        stored_data=None,
    ):
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Remidt Tømmekalender",
            update_interval=timedelta(days=update_interval_days),
        )
        self.address_id = address_id
        self.store = store
        # Format: {"dates": {...}, "last_seen": {...}}
        if stored_data is None:
            stored_data = {}
        self.history = stored_data.get("dates", {})
        self.last_seen = stored_data.get("last_seen", {})
        _LOGGER.debug("Coordinator initialized with update_interval=%s days", update_interval_days)

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        _LOGGER.debug("Fetching data for address_id: %s", self.address_id)
        session = async_get_clientsession(self.hass)
        url = f"https://kalender.renovasjonsportal.no/api/address/{self.address_id}/details"

        try:
            async with session.get(url) as response:
                response.raise_for_status()
                data = await response.json()

            if not isinstance(data, dict):
                raise UpdateFailed("API response is not a dictionary")

            disposals = data.get("disposals")
            if disposals is None:
                _LOGGER.warning("No 'disposals' key in API response")
                return {}

            if not isinstance(disposals, list):
                raise UpdateFailed("'disposals' is not a list in API response")

            collection_schedule: dict[str, list[str]] = {}
            for disposal in disposals:
                fraction_raw = disposal.get("fraction")
                date_raw = disposal.get("date")

                if not fraction_raw or not date_raw:
                    _LOGGER.warning(
                        "Skipping disposal with missing data: fraction=%s, date=%s",
                        fraction_raw,
                        date_raw,
                    )
                    continue

                fraction = clean_fraction_name(fraction_raw)
                date = date_raw.split("T")[0]
                collection_schedule.setdefault(fraction, []).append(date)

            _LOGGER.info("Collection schedule processed: %s", collection_schedule)
            await self._update_history(collection_schedule)
            return collection_schedule

        except ClientError as err:
            raise UpdateFailed(f"Failed to communicate with Remidt: {err}") from err

    async def _update_history(self, collection_schedule: dict) -> None:
        """Update history when dates pass from future to past."""
        today = dt_util.now().date()
        today_str = today.isoformat()
        data_changed = False

        # Update last_seen for all fractions in current schedule
        for fraction in collection_schedule:
            if self.last_seen.get(fraction) != today_str:
                self.last_seen[fraction] = today_str
                data_changed = True

        # Check for passed dates and add to history
        for fraction, dates in collection_schedule.items():
            for date_str in dates:
                try:
                    date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
                except ValueError:
                    continue

                if date_obj < today:
                    history_list = self.history.setdefault(fraction, [])
                    if date_str not in history_list:
                        history_list.append(date_str)
                        # Keep only the last 2 dates
                        self.history[fraction] = sorted(history_list)[-2:]
                        data_changed = True
                        _LOGGER.info("Added %s to history for %s", date_str, fraction)

        # Clean up fractions not seen for HISTORY_RETENTION_DAYS
        fractions_to_remove = [
            fraction
            for fraction, last_seen_str in self.last_seen.items()
            if self._days_since(last_seen_str, today) > HISTORY_RETENTION_DAYS
        ]
        for fraction in fractions_to_remove:
            _LOGGER.info(
                "Removing history for '%s' - not seen for over %s days",
                fraction,
                HISTORY_RETENTION_DAYS,
            )
            self.history.pop(fraction, None)
            self.last_seen.pop(fraction, None)
            data_changed = True

        if data_changed and self.store:
            await self.store.async_save({"dates": self.history, "last_seen": self.last_seen})
            _LOGGER.debug("Saved updated history: %s", self.history)

    @staticmethod
    def _days_since(date_str: str, today) -> int:
        """Return number of days since date_str, or 0 on parse error."""
        try:
            return (today - datetime.strptime(date_str, "%Y-%m-%d").date()).days
        except ValueError:
            return 0


class RemidtTommekalenderSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Remidt Tømmekalender Sensor."""

    def __init__(self, coordinator: RemidtTommekalenderCoordinator, address_name: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_name = "Neste tømming"
        self._attr_unique_id = f"{DOMAIN}_{coordinator.address_id}_sensor"
        self._attr_icon = "mdi:calendar-check"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address_id)},
            name=f"Tømmekalender {address_name}",
            manufacturer="Remidt",
            model="Tømmekalender",
            sw_version="1.0",
        )

    async def async_added_to_hass(self) -> None:
        """Registrer midnatt-callback så 'dager igjen' holder seg oppdatert mellom API-hentinger."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_time_change(
                self.hass,
                self._handle_midnight_update,
                hour=0,
                minute=0,
                second=0,
            )
        )

    def _handle_midnight_update(self, now) -> None:
        """Skriv ny tilstand ved midnatt uten å hente nye data fra API."""
        self.async_write_ha_state()

    def _get_next_collections(self) -> list[dict]:
        """Return sorted list of upcoming collections across all fractions."""
        if not self.coordinator.data:
            return []
        result = []
        for fraction, dates in self.coordinator.data.items():
            for date_str in dates:
                days_left = days_until(date_str)
                if days_left is not None and days_left >= 0:
                    result.append({"fraction": fraction, "date": date_str, "days": days_left})
                    break  # Only the next date per fraction
        result.sort(key=lambda x: x["days"])
        return result

    @property
    def state(self):
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return "Ingen data"
        collections = self._get_next_collections()
        if not collections:
            return "Ingen kommende tømminger"
        soonest = collections[0]
        return format_days_remaining(soonest["days"], soonest["fraction"])

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = {}
        if not self.coordinator.data:
            return attributes

        all_next_collections = self._get_next_collections()

        for fraction, dates in self.coordinator.data.items():
            # All upcoming dates for this fraction
            attributes[f"{fraction}_datoer"] = ", ".join(dates)

            # Find next date for this fraction
            neste_dato = next(
                (d for d in dates if (days_left := days_until(d)) is not None and days_left >= 0),
                None,
            )
            if neste_dato is None:
                continue

            days_left = days_until(neste_dato)
            attributes[f"{fraction}_neste"] = neste_dato
            attributes[f"{fraction}_dager_igjen"] = days_left

            # Determine previous date for cycle progress
            forrige_dato: str | None = None
            stored_history = self.coordinator.history.get(fraction, [])
            if stored_history:
                forrige_dato = stored_history[-1]
            else:
                # Estimate from interval between the two next upcoming dates
                future_dates = [d for d in dates if (n := days_until(d)) is not None and n >= 0]
                if len(future_dates) >= 2:
                    try:
                        date1 = datetime.strptime(future_dates[0], "%Y-%m-%d").date()
                        date2 = datetime.strptime(future_dates[1], "%Y-%m-%d").date()
                        intervall = (date2 - date1).days
                        forrige_dato = (date1 - timedelta(days=intervall)).strftime("%Y-%m-%d")
                        _LOGGER.debug(
                            "Estimating previous date for %s from two future dates: %s",
                            fraction,
                            forrige_dato,
                        )
                    except ValueError:
                        pass
                elif len(future_dates) == 1:
                    # Only one future date known – assume we're halfway through the cycle.
                    # Progress will self-correct once history builds up or the API
                    # returns a second upcoming date.
                    try:
                        days_left = days_until(future_dates[0])
                        if days_left is not None and days_left > 0:
                            neste = datetime.strptime(future_dates[0], "%Y-%m-%d").date()
                            forrige_dato = (neste - timedelta(days=days_left * 2)).strftime(
                                "%Y-%m-%d"
                            )
                            _LOGGER.debug(
                                "Estimating previous date for %s (halfway assumption): %s",
                                fraction,
                                forrige_dato,
                            )
                    except ValueError:
                        pass

            if forrige_dato:
                progress_data = calculate_cycle_progress(forrige_dato, neste_dato)
                attributes[f"{fraction}_forrige"] = forrige_dato
                attributes[f"{fraction}_intervall"] = progress_data["intervall"]
                attributes[f"{fraction}_progress"] = progress_data["progress"]

        if all_next_collections:
            summary = [
                format_days_remaining(item["days"], item["fraction"])
                for item in all_next_collections[:3]
            ]
            attributes["kommende_tømminger"] = "; ".join(summary)

        return attributes

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success
