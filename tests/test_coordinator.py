"""Tests for Broadlink AC coordinator error handling."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from custom_components.broadlink_ac.const import DOMAIN
from custom_components.broadlink_ac.coordinator import BroadlinkACCoordinator
from custom_components.broadlink_ac.exceptions import BroadlinkACConnectionError
from homeassistant.const import CONF_HOST, CONF_MAC
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import UpdateFailed

from pytest_homeassistant_custom_component.common import MockConfigEntry

HOST = "192.168.1.100"
MAC_FORMATTED = "34:ea:34:f7:58:66"


def _mock_entry() -> MockConfigEntry:
    """Create a Broadlink AC config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: HOST, CONF_MAC: MAC_FORMATTED},
        unique_id=MAC_FORMATTED,
    )


async def test_coordinator_update_wraps_connection_error(
    hass: HomeAssistant,
) -> None:
    """Test polling connection errors are exposed as UpdateFailed."""
    entry = _mock_entry()
    entry.add_to_hass(hass)
    client = Mock()
    client.get_ac_status.side_effect = BroadlinkACConnectionError("offline")
    coordinator = BroadlinkACCoordinator(hass, entry, client, HOST, MAC_FORMATTED)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_coordinator_command_wraps_connection_error(
    hass: HomeAssistant,
) -> None:
    """Test command connection errors are exposed as HomeAssistantError."""
    entry = _mock_entry()
    entry.add_to_hass(hass)
    client = Mock()
    coordinator = BroadlinkACCoordinator(hass, entry, client, HOST, MAC_FORMATTED)
    command = Mock(side_effect=BroadlinkACConnectionError("offline"))

    with pytest.raises(HomeAssistantError):
        await coordinator.async_call(command)
