"""Kalender med alle tømmedatoer som heldagshendelser."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import RemidtConfigEntry
from .entity import RemidtEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RemidtConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Sett opp kalenderen for én adresse."""
    async_add_entities([RemidtCalendar(entry.runtime_data, entry.title)])


def _to_date(value: date | datetime) -> date:
    """Normaliser date/datetime til date."""
    return value.date() if isinstance(value, datetime) else value


class RemidtCalendar(RemidtEntity, CalendarEntity):
    """Alle kjente tømmedatoer som heldagshendelser."""

    _attr_icon = "mdi:calendar-recycle"

    def __init__(self, coordinator, address_name: str) -> None:
        """Initialiser kalenderen."""
        super().__init__(coordinator, address_name)
        self._attr_name = "Tømmekalender"
        self._attr_unique_id = f"{DOMAIN}_{coordinator.address_id}_calendar"

    def _build_events(self) -> list[CalendarEvent]:
        events: list[CalendarEvent] = []
        if not self.coordinator.data:
            return events
        for fraction, dates in self.coordinator.data.items():
            summary = f"{fraction.replace('_', ' ').title()} tømming"
            for date_str in dates:
                try:
                    day = datetime.strptime(date_str, "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    continue
                # Heldagshendelse: end er eksklusiv (dagen etter).
                events.append(CalendarEvent(summary=summary, start=day, end=day + timedelta(days=1)))
        events.sort(key=lambda e: _to_date(e.start))
        return events

    @property
    def event(self) -> CalendarEvent | None:
        """Neste kommende tømming."""
        today = dt_util.now().date()
        upcoming = [e for e in self._build_events() if _to_date(e.end) > today]
        return upcoming[0] if upcoming else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Hendelser innenfor vinduet."""
        window_start = _to_date(start_date)
        window_end = _to_date(end_date)
        return [
            e
            for e in self._build_events()
            if _to_date(e.start) < window_end and _to_date(e.end) > window_start
        ]
