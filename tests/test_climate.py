"""Tests for Broadlink AC climate entity."""

from __future__ import annotations

from unittest.mock import Mock

from homeassistant.components.climate import ClimateEntityFeature, HVACMode
from homeassistant.const import CONF_HOST, CONF_MAC
from homeassistant.core import HomeAssistant

from custom_components.broadlink_ac.climate import BroadlinkACClimate
from custom_components.broadlink_ac.const import DOMAIN
from custom_components.broadlink_ac.coordinator import BroadlinkACCoordinator
from pytest_homeassistant_custom_component.common import MockConfigEntry

HOST = "192.168.1.100"
MAC_FORMATTED = "34:ea:34:f7:58:66"
STATUS = {"power": "OFF", "mode": "cool", "temp": 23, "ambient_temp": 24}


def _coordinator(hass: HomeAssistant) -> tuple[Mock, BroadlinkACClimate]:
    """Create a climate entity with a mocked client."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: HOST, CONF_MAC: MAC_FORMATTED},
        unique_id=MAC_FORMATTED,
    )
    entry.add_to_hass(hass)
    client = Mock()
    client.switch_on.return_value = STATUS
    client.switch_off.return_value = STATUS
    client.set_homeassistant_mode.return_value = STATUS
    coordinator = BroadlinkACCoordinator(hass, entry, client, HOST, MAC_FORMATTED)
    return client, BroadlinkACClimate(coordinator)


async def test_climate_exposes_turn_on_off_features(hass: HomeAssistant) -> None:
    """Test climate entity supports turn_on and turn_off for assistants."""
    _, climate = _coordinator(hass)

    assert climate.supported_features & ClimateEntityFeature.TURN_ON
    assert climate.supported_features & ClimateEntityFeature.TURN_OFF


async def test_climate_turn_off_calls_switch_off(hass: HomeAssistant) -> None:
    """Test turn_off uses the device power off command."""
    client, climate = _coordinator(hass)

    await climate.async_turn_off()

    client.switch_off.assert_called_once()


async def test_climate_turn_on_calls_switch_on(hass: HomeAssistant) -> None:
    """Test turn_on uses the device power on command."""
    client, climate = _coordinator(hass)

    await climate.async_turn_on()

    client.switch_on.assert_called_once()


async def test_climate_set_hvac_off_calls_homeassistant_mode(hass: HomeAssistant) -> None:
    """Test setting HVAC mode OFF uses the homeassistant mode handler."""
    client, climate = _coordinator(hass)

    await climate.async_set_hvac_mode(HVACMode.OFF)

    client.set_homeassistant_mode.assert_called_once_with("off")
