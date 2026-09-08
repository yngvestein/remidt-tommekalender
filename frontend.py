"""Registrering av Lovelace-kortet som en dashbord-ressurs.

Hvorfor ikke `add_extra_js_url`?
--------------------------------
`add_extra_js_url` legger en `import()` av kortet rett inn i `index.html`, som
kjører *før* selve HA-appen. HA-frontenden installerer tidlig i `app.js` en
polyfill for scoped custom element registries som bytter ut
`window.customElements`. Kjører kortet før byttet, havner definisjonen i det
native registeret som HA sin polyfill ikke ser, og kortet får
«Custom element doesn't exist» helt tilfeldig avhengig av nedlastingsrekkefølge.

Lovelace-ressurser lastes derimot av dashbord-panelet lenge etter at appen og
polyfillen er på plass. Det er også slik HACS gjør det, og det er den eneste
måten HA tilbyr for at et kort skal dukke opp i kortvelgeren på lik linje med
de innebygde. Vi registrerer derfor kortet som en ressurs i storage-modus, og
faller bare tilbake til `add_extra_js_url` når dashbord-ressursene styres fra
YAML (da kan vi ikke skrive til dem).
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url, remove_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace.const import LOVELACE_DATA, MODE_STORAGE
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

CARD_FILENAME = "remidt-tommekalender-card.js"
URL_BASE = f"/{DOMAIN}"
CARD_URL = f"{URL_BASE}/{CARD_FILENAME}"
WWW_DIR = Path(__file__).parent / "www"


async def _async_card_url(hass: HomeAssistant) -> str:
    """Kort-URL med versjon som cache-bust, hentet fra manifest.json."""
    integration = await async_get_integration(hass, DOMAIN)
    return f"{CARD_URL}?v={integration.version}"


def _resource_mode(hass: HomeAssistant) -> str | None:
    """Returner 'storage' eller 'yaml' for dashbord-ressursene, eller None."""
    lovelace = hass.data.get(LOVELACE_DATA)
    if lovelace is None:
        return None
    # `resource_mode` ble skilt fra `mode` i nyere HA; fall tilbake for eldre.
    return getattr(lovelace, "resource_mode", getattr(lovelace, "mode", None))


async def async_register_card(hass: HomeAssistant) -> None:
    """Server kortfila og sørg for at den er registrert som dashbord-ressurs.

    Kalles én gang fra `async_setup`, ikke per config entry.
    """
    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(URL_BASE, str(WWW_DIR), cache_headers=True)]
        )
    except (RuntimeError, ValueError):
        # Stien er allerede registrert (f.eks. etter reload av integrasjonen).
        _LOGGER.debug("Static path %s already registered", URL_BASE)

    url = await _async_card_url(hass)

    if _resource_mode(hass) != MODE_STORAGE:
        # YAML-modus: ressursene ligger i configuration.yaml og kan ikke endres
        # herfra. Last kortet som ekstra modul så det i det minste fungerer –
        # kortet selv venter med å registrere elementet til HA er klar.
        add_extra_js_url(hass, url)
        _LOGGER.info(
            "Dashbord-ressursene styres fra YAML. Legg til kortet manuelt som "
            "ressurs: url: %s, type: module",
            url,
        )
        return

    resources = hass.data[LOVELACE_DATA].resources
    # async_get_info() sørger for at storage-samlingen er lastet før vi leser.
    await resources.async_get_info()

    for item in resources.async_items():
        if item["url"].split("?", 1)[0] != CARD_URL:
            continue
        if item["url"] != url:
            await resources.async_update_item(
                item["id"], {"res_type": "module", "url": url}
            )
            _LOGGER.info("Oppdaterte dashbord-ressurs for kortet til %s", url)
        else:
            _LOGGER.debug("Dashbord-ressurs for kortet finnes allerede: %s", url)
        return

    await resources.async_create_item({"res_type": "module", "url": url})
    _LOGGER.info("Registrerte kortet som dashbord-ressurs: %s", url)


async def async_unregister_card(hass: HomeAssistant) -> None:
    """Fjern dashbord-ressursen. Kalles når siste config entry slettes."""
    url = await _async_card_url(hass)

    if _resource_mode(hass) != MODE_STORAGE:
        remove_extra_js_url(hass, url)
        return

    resources = hass.data[LOVELACE_DATA].resources
    await resources.async_get_info()
    for item in list(resources.async_items()):
        if item["url"].split("?", 1)[0] == CARD_URL:
            await resources.async_delete_item(item["id"])
            _LOGGER.info("Fjernet dashbord-ressurs for kortet: %s", item["url"])
