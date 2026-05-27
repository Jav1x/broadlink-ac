"""Switch platform for Broadlink AC integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import BroadlinkACData, BroadlinkACCoordinator
from .entity import BroadlinkACEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Broadlink AC switch entities from a config entry."""
    data: BroadlinkACData = entry.runtime_data
    async_add_entities(
        [BroadlinkACDisplaySwitch(device.coordinator) for device in data.devices]
    )


class BroadlinkACDisplaySwitch(BroadlinkACEntity, SwitchEntity):
    """Representation of the AC display board switch."""

    _attr_icon = "mdi:monitor"
    _attr_translation_key = "display"

    def __init__(self, coordinator: BroadlinkACCoordinator) -> None:
        """Initialize the display switch."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._mac_id}_display"
        self._attr_is_on = None
        self._update_attrs()

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_attrs()
        self.async_write_ha_state()

    def _update_attrs(self) -> None:
        """Update attributes from coordinator data."""
        status = self.coordinator.data
        if not isinstance(status, dict):
            return

        self._attr_is_on = status.get("display") == "ON"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the AC display board on."""
        await self.coordinator.async_call(self.coordinator.client.set_display, "ON")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the AC display board off."""
        await self.coordinator.async_call(self.coordinator.client.set_display, "OFF")
