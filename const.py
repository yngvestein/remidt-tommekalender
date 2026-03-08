"""Constants for the Remidt Tømmekalender integration."""

from datetime import datetime
from homeassistant.util import dt as dt_util

DOMAIN = "remidt_tommekalender"

DEFAULT_UPDATE_INTERVAL_DAYS = 2

STORAGE_VERSION = 2
HISTORY_RETENTION_DAYS = 30  # Fjern historikk for fraksjoner som ikke er sett på X dager


def get_storage_key(address_id: str) -> str:
    """Get storage key for a specific address."""
    return f"{DOMAIN}_history_{address_id}"


def clean_fraction_name(fraction: str) -> str:
    """Clean fraction name to be consistent across the integration."""
    if not fraction:
        return ""
    return fraction.lower().replace(" ", "_")


def days_until(date_str: str) -> int | None:
    """Calculate days until a given date string (YYYY-MM-DD).

    Returns None if date string is invalid.
    """
    try:
        collection_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        today = dt_util.now().date()
        return (collection_date - today).days
    except (ValueError, TypeError):
        return None


def calculate_cycle_progress(forrige_dato: str, neste_dato: str) -> dict:
    """Beregn syklus-progress.

    Args:
        forrige_dato: Previous collection date (YYYY-MM-DD)
        neste_dato: Next collection date (YYYY-MM-DD)

    Returns:
        {"intervall": int, "progress": int (0-100)}
    """
    try:
        forrige = datetime.strptime(forrige_dato, "%Y-%m-%d").date()
        neste = datetime.strptime(neste_dato, "%Y-%m-%d").date()
        today = dt_util.now().date()

        intervall = (neste - forrige).days
        if intervall <= 0:
            return {"intervall": 0, "progress": 0}

        days_passed = (today - forrige).days
        progress = int((days_passed / intervall) * 100)
        # Clamp progress to 0-100
        progress = max(0, min(100, progress))

        return {"intervall": intervall, "progress": progress}
    except (ValueError, TypeError):
        return {"intervall": 0, "progress": 0}


def format_days_remaining(days: int, fraction: str) -> str:
    """Format days remaining as human-readable Norwegian string.

    Args:
        days: Number of days until collection
        fraction: Fraction name (cleaned, with underscores)

    Returns:
        Formatted string like "Restavfall i dag" or "Papir om 3 dager"
    """
    fraction_display = fraction.replace("_", " ").title()
    if days == 0:
        return f"{fraction_display} i dag"
    elif days == 1:
        return f"{fraction_display} i morgen"
    else:
        return f"{fraction_display} om {days} dager"