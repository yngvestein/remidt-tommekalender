"""Remidt Tømmekalender integration initialization."""
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.util import dt as dt_util

from .const import DOMAIN, DEFAULT_UPDATE_INTERVAL_DAYS, STORAGE_VERSION, get_storage_key
from .sensor import RemidtTommekalenderCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Remidt Tømmekalender from a config entry."""
    _LOGGER.debug("Starting async_setup_entry for entry %s", entry.entry_id)
    hass.data.setdefault(DOMAIN, {})

    try:
        # Get update_interval from options (or use default)
        update_interval = entry.options.get("update_interval", DEFAULT_UPDATE_INTERVAL_DAYS)
        _LOGGER.debug("Using update_interval: %s days", update_interval)

        # Initialize persistent storage for history (per-address)
        address_id = entry.data["address_id"]
        storage_key = get_storage_key(address_id)
        store = Store(hass, STORAGE_VERSION, storage_key)
        stored_data = await store.async_load() or {}

        # Migrate from old format (version 1) if needed
        if stored_data and "dates" not in stored_data and "last_seen" not in stored_data:
            # Old format: {"fraction": ["date1", "date2"]}
            # New format: {"dates": {...}, "last_seen": {...}}
            _LOGGER.info("Migrating history storage to new format")
            today_str = dt_util.now().date().isoformat()
            stored_data = {
                "dates": stored_data,
                "last_seen": {fraction: today_str for fraction in stored_data}
            }
            await store.async_save(stored_data)

        _LOGGER.debug("Loaded history from storage: %s", stored_data)

        # Initialize coordinator and store it in hass.data
        coordinator = RemidtTommekalenderCoordinator(
            hass, address_id, update_interval_days=update_interval,
            store=store, stored_data=stored_data
        )
        await coordinator.async_config_entry_first_refresh()

        # Store the coordinator for later use
        hass.data[DOMAIN][entry.entry_id] = coordinator

        # Register service once (when first entry is set up)
        if not hass.services.has_service(DOMAIN, "refresh_schedule"):
            async def refresh_schedule_service(call):
                """Handle refresh schedule service call."""
                address_id_call = call.data.get("address_id")
                for coordinator_item in hass.data[DOMAIN].values():
                    if (
                        hasattr(coordinator_item, "address_id")
                        and coordinator_item.address_id == address_id_call
                    ):
                        await coordinator_item.async_request_refresh()
                        _LOGGER.info(
                            "Manually refreshed schedule for address %s", address_id_call
                        )
                        return
                _LOGGER.warning("No coordinator found for address %s", address_id_call)

            hass.services.async_register(DOMAIN, "refresh_schedule", refresh_schedule_service)

        # Set up platforms
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    except ConfigEntryNotReady:
        raise
    except Exception as exc:
        _LOGGER.error("Unexpected error setting up entry %s: %s", entry.entry_id, exc)
        raise ConfigEntryNotReady(f"Unexpected error during setup: {exc}") from exc

    entry.async_on_unload(entry.add_update_listener(update_listener))
    _LOGGER.debug("Finished async_setup_entry for entry %s", entry.entry_id)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Starting async_unload_entry for entry %s", entry.entry_id)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        # Remove service when last entry is unloaded
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, "refresh_schedule")
    _LOGGER.debug("Finished async_unload_entry for entry %s", entry.entry_id)
    return unload_ok


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    _LOGGER.debug("Updating entry %s", entry.entry_id)
    await hass.config_entries.async_reload(entry.entry_id)
