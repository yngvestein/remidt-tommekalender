"""Diagnostikk: last ned tilstand fra Innstillinger → Enheter og tjenester."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .coordinator import RemidtConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: RemidtConfigEntry
) -> dict[str, Any]:
    """Returner diagnostikk for én adresse."""
    coordinator = entry.runtime_data
    return {
        "entry": {
            "title": entry.title,
            "data": dict(entry.data),
            "options": dict(entry.options),
        },
        "last_update_success": coordinator.last_update_success,
        "schedule": coordinator.data,
        "history": coordinator.history,
        "last_seen": coordinator.last_seen,
    }
