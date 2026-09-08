"""Felles basisklasse for alle entiteter i integrasjonen."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RemidtTommekalenderCoordinator


class RemidtEntity(CoordinatorEntity[RemidtTommekalenderCoordinator]):
    """Kobler entiteten til koordinatoren og adressens enhet."""

    def __init__(
        self, coordinator: RemidtTommekalenderCoordinator, address_name: str
    ) -> None:
        """Initialiser entiteten."""
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address_id)},
            name=f"Tømmekalender {address_name}",
            manufacturer="Remidt",
            model="Tømmekalender",
            configuration_url="https://www.remidt.no",
        )

    @property
    def available(self) -> bool:
        """Entiteten er tilgjengelig så lenge siste henting lyktes."""
        return self.coordinator.last_update_success
