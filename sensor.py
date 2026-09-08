"""Sensorer: neste tømming som tekst og som tidsstempel."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    calculate_cycle_progress,
    days_until,
    format_days_remaining,
)
from .coordinator import RemidtConfigEntry
from .entity import RemidtEntity

_LOGGER = logging.getLogger(__name__)

# Koordinatoren styrer all henting; entitetene poller ikke selv.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RemidtConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Sett opp sensorene for én adresse."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            RemidtTommekalenderSensor(coordinator, entry.title),
            RemidtNextCollectionTimestampSensor(coordinator, entry.title),
        ]
    )


class _MidnightRefreshMixin(RemidtEntity):
    """Skriv ny tilstand ved midnatt, så «dager igjen» rykker fram uten API-kall."""

    async def async_added_to_hass(self) -> None:
        """Registrer midnatt-callback."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_time_change(
                self.hass, self._handle_midnight, hour=0, minute=0, second=0
            )
        )

    @callback
    def _handle_midnight(self, now) -> None:
        self.async_write_ha_state()


class RemidtTommekalenderSensor(_MidnightRefreshMixin, SensorEntity):
    """Neste tømming som lesbar tekst, med alle fraksjoner som attributter."""

    _attr_icon = "mdi:calendar-check"

    def __init__(self, coordinator, address_name: str) -> None:
        """Initialiser sensoren."""
        super().__init__(coordinator, address_name)
        self._attr_name = "Neste tømming"
        self._attr_unique_id = f"{DOMAIN}_{coordinator.address_id}_sensor"

    def _next_collections(self) -> list[dict[str, Any]]:
        """Neste kommende tømming per fraksjon, sortert etter dager igjen."""
        if not self.coordinator.data:
            return []
        result = []
        for fraction, dates in self.coordinator.data.items():
            for date_str in dates:
                days_left = days_until(date_str)
                if days_left is not None and days_left >= 0:
                    result.append({"fraction": fraction, "date": date_str, "days": days_left})
                    break
        result.sort(key=lambda x: x["days"])
        return result

    @property
    def native_value(self) -> str:
        """Tilstanden er den nærmeste tømmingen."""
        if not self.coordinator.data:
            return "Ingen data"
        collections = self._next_collections()
        if not collections:
            return "Ingen kommende tømminger"
        soonest = collections[0]
        return format_days_remaining(soonest["days"], soonest["fraction"])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Per fraksjon: datoer, neste, dager igjen, forrige, intervall, progress."""
        attributes: dict[str, Any] = {}
        if not self.coordinator.data:
            return attributes

        for fraction, dates in self.coordinator.data.items():
            attributes[f"{fraction}_datoer"] = ", ".join(dates)

            neste_dato = next(
                (d for d in dates if (n := days_until(d)) is not None and n >= 0),
                None,
            )
            if neste_dato is None:
                continue

            attributes[f"{fraction}_neste"] = neste_dato
            attributes[f"{fraction}_dager_igjen"] = days_until(neste_dato)

            forrige_dato = self._previous_date(fraction, dates)
            if forrige_dato:
                progress = calculate_cycle_progress(forrige_dato, neste_dato)
                attributes[f"{fraction}_forrige"] = forrige_dato
                attributes[f"{fraction}_intervall"] = progress["intervall"]
                attributes[f"{fraction}_progress"] = progress["progress"]

        upcoming = self._next_collections()
        if upcoming:
            attributes["kommende_tømminger"] = "; ".join(
                format_days_remaining(item["days"], item["fraction"])
                for item in upcoming[:3]
            )
        return attributes

    def _previous_date(self, fraction: str, dates: list[str]) -> str | None:
        """Forrige tømmedato: fra historikk, ellers estimert fra kommende datoer."""
        history = self.coordinator.history.get(fraction, [])
        if history:
            return history[-1]

        future = [d for d in dates if (n := days_until(d)) is not None and n >= 0]
        try:
            if len(future) >= 2:
                date1 = datetime.strptime(future[0], "%Y-%m-%d").date()
                date2 = datetime.strptime(future[1], "%Y-%m-%d").date()
                interval = (date2 - date1).days
                return (date1 - timedelta(days=interval)).strftime("%Y-%m-%d")
            if len(future) == 1:
                # Én kjent dato: anta at vi er halvveis i syklusen. Korrigerer
                # seg selv når historikk bygges opp.
                days_left = days_until(future[0])
                if days_left is not None and days_left > 0:
                    neste = datetime.strptime(future[0], "%Y-%m-%d").date()
                    return (neste - timedelta(days=days_left * 2)).strftime("%Y-%m-%d")
        except ValueError:
            pass
        return None


class RemidtNextCollectionTimestampSensor(_MidnightRefreshMixin, SensorEntity):
    """Neste tømming (uansett fraksjon) som ekte tidsstempel, lokal midnatt."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator, address_name: str) -> None:
        """Initialiser sensoren."""
        super().__init__(coordinator, address_name)
        self._attr_name = "Neste tømming tidspunkt"
        self._attr_unique_id = f"{DOMAIN}_{coordinator.address_id}_next_timestamp"

    def _next_collection(self) -> dict[str, str] | None:
        if not self.coordinator.data:
            return None
        best: dict[str, str] | None = None
        for fraction, dates in self.coordinator.data.items():
            for date_str in dates:
                days_left = days_until(date_str)
                if days_left is not None and days_left >= 0:
                    if best is None or date_str < best["date"]:
                        best = {"fraction": fraction, "date": date_str}
                    break
        return best

    @property
    def native_value(self) -> datetime | None:
        """Lokal midnatt på tømmedagen."""
        nxt = self._next_collection()
        if not nxt:
            return None
        try:
            day = datetime.strptime(nxt["date"], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None
        return dt_util.start_of_local_day(day)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Hvilken fraksjon, og datoen som streng."""
        nxt = self._next_collection()
        if not nxt:
            return {}
        return {
            "fraksjon": nxt["fraction"].replace("_", " ").title(),
            "dato": nxt["date"],
        }
