"""Constants for the Remidt Tømmekalender integration."""

from datetime import datetime
from homeassistant.util import dt as dt_util

DOMAIN = "remidt_tommekalender"

# Beholdt for bakoverkompatibilitet (ikke lenger brukt til polling).
DEFAULT_UPDATE_INTERVAL_DAYS = 2

# Daglig planlagt synk: starttime på døgnet (0–23). Selve tidspunktet jittres
# deterministisk per installasjon innenfor et vindu (se under), slik at ikke
# alle HA-instanser treffer API-et samtidig.
DEFAULT_REFRESH_HOUR = 3

# Bredden på vinduet (timer) som hentingen spres utover, fra DEFAULT_REFRESH_HOUR.
# Med start 03 og vindu 2 fordeles kallene jevnt mellom 03:00 og 04:59.
# 3000 installasjoner ⇒ ~25 kall/minutt i stedet for alle samtidig.
REFRESH_WINDOW_HOURS = 2

# Sikkerhetsnett-intervall: dersom den planlagte synken aldri skulle fyre,
# vil koordinatoren uansett hente på nytt etter dette.
SAFETY_NET_INTERVAL_HOURS = 24

# Hvor lenge etter en mislykket henting vi prøver igjen (til det lykkes).
RETRY_INTERVAL_HOURS = 1

# Binary sensor: slå på dagen før kl. 13, slå av på tømmedagen kl. 14.
BINARY_SENSOR_ON_HOUR = 13
BINARY_SENSOR_OFF_HOUR = 14

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