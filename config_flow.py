"""Config flow for Remidt Tømmekalender."""
import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from aiohttp import ClientSession, ClientError

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class RemidtTommekalenderConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Remidt Tømmekalender."""

    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        super().__init__()
        self._suggestions: list[dict] = []

    @staticmethod
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return RemidtTommekalenderOptionsFlow(config_entry)

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle the initial step."""
        _LOGGER.debug("Starting async_step_user")
        errors = {}

        if user_input is not None:
            address = user_input.get("address", "").strip()
            _LOGGER.debug("Fetching address suggestions for: %s", address)
            suggestions = await self._fetch_address_suggestions(address)

            if suggestions:
                _LOGGER.debug("Found %s suggestions", len(suggestions))
                return await self.async_step_select_address()
            else:
                _LOGGER.debug("No suggestions found")
                errors["base"] = "no_suggestions"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("address"): str,
            }),
            errors=errors,
        )

    async def async_step_select_address(self, user_input=None) -> FlowResult:
        """Handle the step where the user selects an address from the suggestions."""
        _LOGGER.debug("Starting async_step_select_address")
        errors = {}

        if user_input is not None:
            selected_address = user_input.get("address")
            _LOGGER.debug("User selected address: %s", selected_address)

            address_id = None
            for suggestion in self._suggestions:
                if suggestion["full_address"] == selected_address:
                    address_id = suggestion["id"]
                    break

            if address_id:
                _LOGGER.debug("Found address_id: %s", address_id)

                # Prevent duplicate entries for the same address
                await self.async_set_unique_id(address_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=selected_address,
                    data={"address": selected_address, "address_id": address_id},
                )
            else:
                _LOGGER.debug("Invalid address selected")
                errors["base"] = "invalid_address"

        address_options = [s["full_address"] for s in self._suggestions]
        suggestions_schema = vol.Schema({
            vol.Required("address"): vol.In(address_options)
        })

        return self.async_show_form(
            step_id="select_address",
            data_schema=suggestions_schema,
            errors=errors,
        )

    async def _fetch_address_suggestions(self, address: str) -> list[str]:
        """Fetch address suggestions from the API."""
        _LOGGER.debug("Fetching address suggestions for: %s", address)
        session: ClientSession = async_get_clientsession(self.hass)
        url = f"https://kalender.renovasjonsportal.no/api/address/{address}"

        headers = {
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.remidt.no",
            "Referer": "https://www.remidt.no/",
        }

        try:
            async with session.get(url, headers=headers) as response:
                response.raise_for_status()
                data = await response.json()

            search_results = data.get("searchResults", [])
            if not search_results:
                _LOGGER.debug("No search results found")
                self._suggestions = []
                return []

            self._suggestions = [
                {
                    "full_address": f"{result['title']} ({result['subTitle']})",
                    "id": result["id"],
                }
                for result in search_results
            ]

            _LOGGER.debug("Found %s suggestions", len(self._suggestions))
            return [s["full_address"] for s in self._suggestions]

        except ClientError as err:
            _LOGGER.error("Failed to fetch address suggestions: %s", err)
            self._suggestions = []
            return []


class RemidtTommekalenderOptionsFlow(config_entries.OptionsFlow):
    """Handle options for Remidt Tømmekalender."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(
                    "update_interval",
                    default=self.config_entry.options.get("update_interval", 2),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=7)),
            }),
        )
