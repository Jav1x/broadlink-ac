"""Base entities for Broadlink AC integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BroadlinkACCoordinator


class BroadlinkACEntity(CoordinatorEntity[BroadlinkACCoordinator]):
    """Base class for Broadlink AC entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: BroadlinkACCoordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._mac = coordinator.mac
        self._mac_id = coordinator.mac_id
        self._attr_device_info = {
            "connections": {(CONNECTION_NETWORK_MAC, self._mac)},
            "identifiers": {(DOMAIN, self._mac_id)},
            "manufacturer": "Broadlink",
            "name": f"Broadlink AC ({coordinator.host})",
        }
