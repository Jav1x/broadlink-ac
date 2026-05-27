"""Platform for Broadlink AC climate integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import BroadlinkACData, BroadlinkACCoordinator
from .entity import BroadlinkACEntity

FAN_TURBO = "turbo"
FAN_MUTE = "mute"

SUPPORTED_FAN_MODES = [FAN_AUTO, FAN_LOW, FAN_MEDIUM, FAN_HIGH, FAN_TURBO, FAN_MUTE]
SUPPORTED_HVAC_MODES = [
    HVACMode.OFF,
    HVACMode.AUTO,
    HVACMode.COOL,
    HVACMode.HEAT,
    HVACMode.DRY,
    HVACMode.FAN_ONLY,
]
SUPPORTED_SWING_MODES = [
    "top",
    "middle1",
    "middle2",
    "middle3",
    "bottom",
    "swing",
    "auto",
]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Broadlink AC climate entity from a config entry."""
    data: BroadlinkACData = entry.runtime_data
    async_add_entities(
        [BroadlinkACClimate(device.coordinator) for device in data.devices]
    )


class BroadlinkACClimate(BroadlinkACEntity, ClimateEntity):
    """Representation of a Broadlink AC climate entity."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.SWING_MODE
    )
    _attr_hvac_modes = SUPPORTED_HVAC_MODES
    _attr_fan_modes = SUPPORTED_FAN_MODES
    _attr_swing_modes = SUPPORTED_SWING_MODES

    def __init__(self, coordinator: BroadlinkACCoordinator) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator)
        self._attr_name = None
        self._attr_unique_id = f"{self._mac_id}_climate"
        self._attr_current_temperature = None
        self._attr_target_temperature = None
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_fan_mode = FAN_AUTO
        self._attr_swing_mode = None
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

        self._attr_current_temperature = status.get("ambient_temp")
        self._attr_target_temperature = status.get("temp")
        if status.get("power") == "OFF":
            self._attr_hvac_mode = HVACMode.OFF
        else:
            self._attr_hvac_mode = self._map_mode_to_hvac(status.get("mode"))
        if fanspeed := status.get("fanspeed"):
            self._attr_fan_mode = fanspeed.lower()
        if swing_mode := status.get("fixation_v"):
            self._attr_swing_mode = swing_mode.lower()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the target temperature."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is not None:
            await self.coordinator.async_call(
                self.coordinator.client.set_temperature, temperature
            )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the HVAC mode."""
        await self.coordinator.async_call(
            self.coordinator.client.set_homeassistant_mode, str(hvac_mode)
        )

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set the fan mode."""
        if fan_mode == FAN_TURBO:
            await self.coordinator.async_call(self.coordinator.client.set_turbo, "ON")
        elif fan_mode == FAN_MUTE:
            await self.coordinator.async_call(self.coordinator.client.set_mute, "ON")
        else:
            await self.coordinator.async_call(
                self.coordinator.client.set_fanspeed, fan_mode.upper()
            )

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set the vertical swing mode."""
        await self.coordinator.async_call(
            self.coordinator.client.set_fixation_v, swing_mode
        )

    def _map_mode_to_hvac(self, mode: str | None) -> HVACMode:
        """Map AC mode to Home Assistant HVAC mode."""
        if mode is None:
            return HVACMode.OFF
        return {
            "COOLING": HVACMode.COOL,
            "HEATING": HVACMode.HEAT,
            "DRY": HVACMode.DRY,
            "FAN": HVACMode.FAN_ONLY,
            "AUTO": HVACMode.AUTO,
        }.get(mode.upper(), HVACMode.OFF)

    def _map_hvac_to_mode(self, hvac_mode: HVACMode) -> str:
        """Map Home Assistant HVAC mode to AC mode."""
        return {
            HVACMode.COOL: "COOLING",
            HVACMode.HEAT: "HEATING",
            HVACMode.DRY: "DRY",
            HVACMode.FAN_ONLY: "FAN",
            HVACMode.AUTO: "AUTO",
        }[hvac_mode]
