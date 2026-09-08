"""Remidt Tømmekalender – oppsett av integrasjonen."""

from __future__ import annotations

from datetime import timedelta
import logging
import random

from aiohttp import ClientError
import voluptuous as vol

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ConfigEntryNotReady, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_call_later, async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from .const import (
    DEFAULT_REFRESH_HOUR,
    DOMAIN,
    REFRESH_WINDOW_HOURS,
    RETRY_INTERVAL_HOURS,
    STORAGE_VERSION,
    get_storage_key,
)
from .coordinator import RemidtConfigEntry, RemidtTommekalenderCoordinator
from .frontend import async_register_card, async_unregister_card

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.CALENDAR, Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SERVICE_REFRESH = "refresh_schedule"
SERVICE_REFRESH_SCHEMA = vol.Schema({vol.Required("address_id"): cv.string})


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Registrer det som skal finnes én gang: kortet og tjenesten."""
    await async_register_card(hass)

    async def _async_refresh_schedule(call: ServiceCall) -> None:
        address_id = call.data["address_id"]
        for entry in hass.config_entries.async_loaded_entries(DOMAIN):
            coordinator: RemidtTommekalenderCoordinator = entry.runtime_data
            if coordinator.address_id == address_id:
                await coordinator.async_request_refresh()
                _LOGGER.info("Manually refreshed schedule for address %s", address_id)
                return
        raise ServiceValidationError(
            f"Ingen konfigurert adresse med id {address_id}",
            translation_domain=DOMAIN,
            translation_key="unknown_address",
            translation_placeholders={"address_id": address_id},
        )

    hass.services.async_register(
        DOMAIN, SERVICE_REFRESH, _async_refresh_schedule, schema=SERVICE_REFRESH_SCHEMA
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: RemidtConfigEntry) -> bool:
    """Sett opp én adresse."""
    address_id = entry.data["address_id"]
    store = Store(hass, STORAGE_VERSION, get_storage_key(address_id))
    stored_data = await store.async_load() or {}

    # Migrer fra gammelt lagringsformat: {"fraksjon": ["dato", ...]}
    if stored_data and "dates" not in stored_data and "last_seen" not in stored_data:
        _LOGGER.info("Migrating history storage to new format")
        today_str = dt_util.now().date().isoformat()
        stored_data = {
            "dates": stored_data,
            "last_seen": {fraction: today_str for fraction in stored_data},
        }
        await store.async_save(stored_data)

    coordinator = RemidtTommekalenderCoordinator(
        hass, entry, address_id, store, stored_data
    )
    try:
        await coordinator.async_config_entry_first_refresh()
    except ClientError as exc:
        raise ConfigEntryNotReady(f"Remidt API not reachable: {exc}") from exc

    entry.runtime_data = coordinator
    _setup_scheduled_refresh(hass, entry, coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: RemidtConfigEntry) -> bool:
    """Last ut én adresse."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: RemidtConfigEntry) -> None:
    """Rydd opp når siste adresse slettes: fjern dashbord-ressursen."""
    remaining = [
        e for e in hass.config_entries.async_entries(DOMAIN) if e.entry_id != entry.entry_id
    ]
    if not remaining:
        await async_unregister_card(hass)


async def _async_update_listener(hass: HomeAssistant, entry: RemidtConfigEntry) -> None:
    """Last inn på nytt når innstillingene endres."""
    await hass.config_entries.async_reload(entry.entry_id)


def _setup_scheduled_refresh(
    hass: HomeAssistant,
    entry: RemidtConfigEntry,
    coordinator: RemidtTommekalenderCoordinator,
) -> None:
    """Planlegg én daglig henting på et jittret tidspunkt, med retry ved feil.

    Renovasjonsdata er svært statiske, så vi henter bare én gang per døgn på et
    fast (men per-installasjon jittret) tidspunkt for å være snill mot API-et.
    Slår en henting feil, prøver vi igjen hver time til den lykkes.
    """
    base_hour = entry.options.get("refresh_hour", DEFAULT_REFRESH_HOUR)
    window_minutes = max(1, REFRESH_WINDOW_HOURS * 60)
    offset = random.Random(coordinator.address_id).randrange(window_minutes)
    total_minutes = base_hour * 60 + offset
    refresh_hour = (total_minutes // 60) % 24
    refresh_minute = total_minutes % 60
    _LOGGER.debug(
        "Scheduling daily refresh for %s at %02d:%02d",
        entry.entry_id,
        refresh_hour,
        refresh_minute,
    )

    @callback
    def _scheduled_refresh(now) -> None:
        entry.async_create_background_task(
            hass, coordinator.async_request_refresh(), "remidt_scheduled_refresh"
        )

    entry.async_on_unload(
        async_track_time_change(
            hass, _scheduled_refresh, hour=refresh_hour, minute=refresh_minute, second=0
        )
    )

    retry_canceller: list = [None]

    @callback
    def _cancel_retry() -> None:
        if retry_canceller[0] is not None:
            retry_canceller[0]()
            retry_canceller[0] = None

    @callback
    def _handle_update() -> None:
        _cancel_retry()
        if coordinator.last_update_success:
            return
        _LOGGER.debug(
            "Refresh failed for %s, retrying in %sh", entry.entry_id, RETRY_INTERVAL_HOURS
        )

        @callback
        def _do_retry(now) -> None:
            retry_canceller[0] = None
            entry.async_create_background_task(
                hass, coordinator.async_request_refresh(), "remidt_retry_refresh"
            )

        retry_canceller[0] = async_call_later(
            hass, timedelta(hours=RETRY_INTERVAL_HOURS), _do_retry
        )

    entry.async_on_unload(coordinator.async_add_listener(_handle_update))
    entry.async_on_unload(_cancel_retry)
