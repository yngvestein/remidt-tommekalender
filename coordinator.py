"""Koordinator som henter tømmekalenderen fra Remidt sitt API."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from aiohttp import ClientError

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import HISTORY_RETENTION_DAYS, clean_fraction_name

_LOGGER = logging.getLogger(__name__)

API_URL = "https://kalender.renovasjonsportal.no/api/address/{address_id}/details"

# Fraksjon -> sorterte datoer (YYYY-MM-DD)
type Schedule = dict[str, list[str]]

type RemidtConfigEntry = ConfigEntry[RemidtTommekalenderCoordinator]


class RemidtTommekalenderCoordinator(DataUpdateCoordinator[Schedule]):
    """Henter og cacher tømmeplanen for én adresse.

    Bevisst ingen `update_interval`: synk drives av en planlagt, jittret daglig
    henting i `__init__.py` (pluss retry ved feil). Det gir forutsigbare
    tidspunkter og minimal last på Remidt sitt API.
    """

    config_entry: RemidtConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: RemidtConfigEntry,
        address_id: str,
        store: Store,
        stored_data: dict[str, Any],
    ) -> None:
        """Initialiser koordinatoren."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name="Remidt Tømmekalender",
            update_interval=None,
        )
        self.address_id = address_id
        self.store = store
        # Format: {"dates": {fraksjon: [dato, ...]}, "last_seen": {fraksjon: dato}}
        self.history: dict[str, list[str]] = stored_data.get("dates", {})
        self.last_seen: dict[str, str] = stored_data.get("last_seen", {})

    async def _async_update_data(self) -> Schedule:
        """Hent tømmeplanen fra API-et."""
        session = async_get_clientsession(self.hass)
        url = API_URL.format(address_id=self.address_id)
        _LOGGER.debug("Fetching %s", url)

        try:
            async with session.get(url) as response:
                response.raise_for_status()
                data = await response.json()
        except ClientError as err:
            raise UpdateFailed(f"Failed to communicate with Remidt: {err}") from err

        if not isinstance(data, dict):
            raise UpdateFailed("API response is not a dictionary")

        disposals = data.get("disposals")
        if disposals is None:
            _LOGGER.warning("No 'disposals' key in API response")
            return {}
        if not isinstance(disposals, list):
            raise UpdateFailed("'disposals' is not a list in API response")

        schedule: Schedule = {}
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
            schedule.setdefault(fraction, []).append(date_raw.split("T")[0])

        for dates in schedule.values():
            dates.sort()

        _LOGGER.debug("Collection schedule processed: %s", schedule)
        await self._async_update_history(schedule)
        return schedule

    async def _async_update_history(self, schedule: Schedule) -> None:
        """Flytt passerte datoer inn i historikken og rydd gamle fraksjoner."""
        today = dt_util.now().date()
        today_str = today.isoformat()
        changed = False

        for fraction in schedule:
            if self.last_seen.get(fraction) != today_str:
                self.last_seen[fraction] = today_str
                changed = True

        for fraction, dates in schedule.items():
            for date_str in dates:
                try:
                    date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
                except ValueError:
                    continue
                if date_obj < today:
                    history = self.history.setdefault(fraction, [])
                    if date_str not in history:
                        history.append(date_str)
                        # Behold bare de to siste datoene
                        self.history[fraction] = sorted(history)[-2:]
                        changed = True
                        _LOGGER.debug("Added %s to history for %s", date_str, fraction)

        stale = [
            fraction
            for fraction, seen in self.last_seen.items()
            if self._days_since(seen, today) > HISTORY_RETENTION_DAYS
        ]
        for fraction in stale:
            _LOGGER.info(
                "Removing history for '%s' - not seen for over %s days",
                fraction,
                HISTORY_RETENTION_DAYS,
            )
            self.history.pop(fraction, None)
            self.last_seen.pop(fraction, None)
            changed = True

        if changed:
            await self.store.async_save(
                {"dates": self.history, "last_seen": self.last_seen}
            )

    @staticmethod
    def _days_since(date_str: str, today) -> int:
        """Antall dager siden date_str, eller 0 ved ugyldig dato."""
        try:
            return (today - datetime.strptime(date_str, "%Y-%m-%d").date()).days
        except ValueError:
            return 0
