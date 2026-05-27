"""Test Broadlink AC config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_MAC
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from homeassistant.helpers import area_registry as ar

from custom_components.broadlink_ac.config_flow import (
    CONF_ADD_MANUAL,
    CONF_DEVICE_AREAS,
    MENU_MANUAL_ADD_ANOTHER,
    MENU_MANUAL_CONTINUE,
    SECTION_MANUAL_DEVICES,
)
from custom_components.broadlink_ac.const import CONF_AREA_ID, DOMAIN
from custom_components.broadlink_ac.discovery import BroadlinkACDiscoveryDevice
from pytest_homeassistant_custom_component.common import MockConfigEntry

HOST = "192.168.1.100"
HOST_2 = "192.168.1.101"
MAC_BYTES = bytes.fromhex("34ea34f75866")
MAC_BYTES_2 = bytes.fromhex("34ea34f75867")
MAC_FORMATTED = "34:ea:34:f7:58:66"
MAC_FORMATTED_2 = "34:ea:34:f7:58:67"
DISCOVER_AC_DEVICES_PATH = "custom_components.broadlink_ac.config_flow.discover_ac_devices"
DISCOVER_MAC_PATH = "custom_components.broadlink_ac.config_flow.discover_mac"
TEST_CONNECTION_PATH = (
    "custom_components.broadlink_ac.config_flow._async_test_device_connection"
)


def _manual_device_input(host: str, mac: str = "") -> dict[str, str]:
    """Build user input for one manual device on the user/init step."""
    return {CONF_HOST: host, CONF_MAC: mac}


async def _configure_manual_device_step(
    hass: HomeAssistant, flow_id: str, host: str, mac: str = ""
):
    """Configure the dedicated manual device step."""
    return await hass.config_entries.flow.async_configure(
        flow_id,
        _manual_device_input(host, mac),
    )


async def _finish_manual_device_menu(hass: HomeAssistant, flow_id: str, *, add_another: bool):
    """Leave the manual device menu and return to the user/init step."""
    step = MENU_MANUAL_ADD_ANOTHER if add_another else MENU_MANUAL_CONTINUE
    return await hass.config_entries.flow.async_configure(flow_id, {"next_step_id": step})


async def _configure_area_step(hass: HomeAssistant, flow_id: str, macs: list[str]):
    """Complete the area assignment step for one or more devices."""
    area_registry = ar.async_get(hass)
    area = area_registry.async_get_area_by_name("Living Room")
    if area is None:
        area = area_registry.async_create("Living Room")

    if len(macs) == 1:
        return await hass.config_entries.flow.async_configure(
            flow_id, {CONF_AREA_ID: area.id}
        )

    return await hass.config_entries.flow.async_configure(
        flow_id,
        {
            CONF_DEVICE_AREAS: [
                {CONF_MAC: mac, CONF_AREA_ID: area.id} for mac in macs
            ]
        },
    )


@pytest.fixture(autouse=True)
def mock_test_device_connection():
    """Skip real Broadlink connections during config flow tests."""
    with patch(TEST_CONNECTION_PATH, return_value=None):
        yield


@pytest.fixture(autouse=True)
def mock_discover_ac_devices():
    """Disable network discovery unless a test opts in."""
    with patch(DISCOVER_AC_DEVICES_PATH, return_value=[]) as mock_discovery:
        yield mock_discovery


def _discovered_device(
    host: str = HOST,
    mac: bytes = MAC_BYTES,
    name: str = "Broadlink AC",
) -> BroadlinkACDiscoveryDevice:
    """Return a discovered AC device for config flow tests."""
    return BroadlinkACDiscoveryDevice(
        host=host,
        mac=mac,
        name=name,
        devtype=0x4E2A,
    )


async def test_form(hass: HomeAssistant) -> None:
    """Test the initial form is shown."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_user_flow_with_manual_mac(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """Test user flow with a manually entered MAC address."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        _manual_device_input(HOST, MAC_FORMATTED),
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "area"
    result = await _configure_area_step(hass, result["flow_id"], [MAC_FORMATTED])

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"Broadlink AC ({HOST})"
    assert result["data"][CONF_HOST] == HOST
    assert result["data"][CONF_MAC] == MAC_FORMATTED
    assert CONF_AREA_ID in result["data"]
    assert result["result"].unique_id == MAC_FORMATTED
    assert len(mock_setup_entry.mock_calls) == 1


async def test_user_flow_mac_without_separators(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """Test user flow accepts MAC addresses without separators."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        _manual_device_input(HOST, "34ea34f75866"),
    )

    result = await _configure_area_step(hass, result["flow_id"], [MAC_FORMATTED])

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_MAC] == MAC_FORMATTED


async def test_user_flow_discovered_mac(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """Test user flow discovers the MAC address automatically."""
    with patch(DISCOVER_MAC_PATH, return_value=MAC_BYTES):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            _manual_device_input(HOST, ""),
        )

    result = await _configure_area_step(hass, result["flow_id"], [MAC_FORMATTED])

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_HOST] == HOST
    assert result["data"][CONF_MAC] == MAC_FORMATTED


async def test_user_flow_with_discovered_devices(
    hass: HomeAssistant, mock_setup_entry: AsyncMock, mock_discover_ac_devices
) -> None:
    """Test user flow creates one entry containing selected discovered devices."""
    mock_discover_ac_devices.return_value = [
        _discovered_device(HOST, MAC_BYTES, "Living Room"),
        _discovered_device(HOST_2, MAC_BYTES_2, "Bedroom"),
    ]
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"discovered_devices": [MAC_FORMATTED, MAC_FORMATTED_2]},
    )

    result = await _configure_area_step(
        hass,
        result["flow_id"],
        [MAC_FORMATTED, MAC_FORMATTED_2],
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Broadlink AC (2 devices)"
    assert len(result["data"]["devices"]) == 2
    assert all(CONF_AREA_ID in device for device in result["data"]["devices"])
    assert len(mock_setup_entry.mock_calls) == 1


async def test_user_flow_with_multiple_manual_devices(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
    mock_discover_ac_devices,
) -> None:
    """Test user flow accepts multiple manually added devices."""
    mock_discover_ac_devices.return_value = [
        _discovered_device(HOST, MAC_BYTES, "Living Room"),
    ]

    def discover_side_effect(host: str) -> bytes | None:
        return {HOST: MAC_BYTES, HOST_2: MAC_BYTES_2}[host]

    with patch(DISCOVER_MAC_PATH, side_effect=discover_side_effect):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {SECTION_MANUAL_DEVICES: {CONF_ADD_MANUAL: True}},
        )
        result = await _configure_manual_device_step(hass, result["flow_id"], HOST, "")
        result = await _finish_manual_device_menu(
            hass, result["flow_id"], add_another=True
        )
        assert result["step_id"] == "manual_device"

        result = await _configure_manual_device_step(
            hass, result["flow_id"], HOST_2, ""
        )
        result = await _finish_manual_device_menu(
            hass, result["flow_id"], add_another=False
        )

        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    result = await _configure_area_step(
        hass,
        result["flow_id"],
        [MAC_FORMATTED, MAC_FORMATTED_2],
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Broadlink AC (2 devices)"
    assert len(result["data"]["devices"]) == 2
    assert all(CONF_AREA_ID in device for device in result["data"]["devices"])
    assert len(mock_setup_entry.mock_calls) == 1


async def test_user_flow_requires_selected_or_manual_device(
    hass: HomeAssistant, mock_discover_ac_devices
) -> None:
    """Test user flow requires either a selected discovered device or manual host."""
    mock_discover_ac_devices.return_value = [
        _discovered_device(HOST, MAC_BYTES, "Living Room"),
    ]
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"discovered_devices": []},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_device_selected"}


async def test_user_flow_recovers_after_mac_not_found(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """Test the flow recovers when discovery fails and MAC is entered manually."""
    with patch(DISCOVER_MAC_PATH, return_value=None):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            _manual_device_input(HOST, ""),
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_MAC: "mac_not_found"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        _manual_device_input(HOST, MAC_FORMATTED),
    )

    result = await _configure_area_step(hass, result["flow_id"], [MAC_FORMATTED])

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_MAC] == MAC_FORMATTED


async def test_invalid_host(hass: HomeAssistant) -> None:
    """Test we show an error for an invalid host."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        _manual_device_input("not-an-ip", MAC_FORMATTED),
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_HOST: "invalid_host"}


async def test_invalid_host_cyrillic(hass: HomeAssistant) -> None:
    """Test we reject non-IP host values such as arbitrary text."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        _manual_device_input("фывфыв", "фывфыв"),
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_HOST: "invalid_host"}


async def test_invalid_mac(hass: HomeAssistant) -> None:
    """Test we show an error for an invalid MAC address."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        _manual_device_input(HOST, "invalid-mac"),
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_MAC: "invalid_mac"}


async def test_invalid_mac_on_manual_device_step(
    hass: HomeAssistant, mock_discover_ac_devices
) -> None:
    """Test the dedicated manual step rejects invalid MAC values."""
    mock_discover_ac_devices.return_value = [
        _discovered_device(HOST, MAC_BYTES, "Living Room"),
    ]
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {SECTION_MANUAL_DEVICES: {CONF_ADD_MANUAL: True}},
    )
    assert result["step_id"] == "manual_device"

    result = await _configure_manual_device_step(
        hass, result["flow_id"], HOST, "фывфыв"
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "manual_device"
    assert result["errors"] == {CONF_MAC: "invalid_mac"}


async def test_mac_not_found(hass: HomeAssistant) -> None:
    """Test we show an error when MAC discovery fails."""
    with patch(DISCOVER_MAC_PATH, return_value=None):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            _manual_device_input(HOST, ""),
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_MAC: "mac_not_found"}


async def test_duplicate_entry(hass: HomeAssistant, mock_setup_entry: AsyncMock) -> None:
    """Test the same device cannot be configured twice."""
    existing = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: HOST, CONF_MAC: MAC_FORMATTED},
        unique_id=MAC_FORMATTED,
    )
    existing.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        _manual_device_input("192.168.1.200", MAC_FORMATTED),
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "already_configured"}
    assert len(mock_setup_entry.mock_calls) == 0


async def test_discovered_devices_skip_configured_devices(
    hass: HomeAssistant, mock_setup_entry: AsyncMock, mock_discover_ac_devices
) -> None:
    """Test discovered-device selection skips devices that are already configured."""
    existing = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: HOST, CONF_MAC: MAC_FORMATTED},
        unique_id=MAC_FORMATTED,
    )
    existing.add_to_hass(hass)

    mock_discover_ac_devices.return_value = [
        _discovered_device(HOST, MAC_BYTES, "Living Room"),
        _discovered_device(HOST_2, MAC_BYTES_2, "Bedroom"),
    ]
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"discovered_devices": [MAC_FORMATTED_2]},
    )

    result = await _configure_area_step(hass, result["flow_id"], [MAC_FORMATTED_2])

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_HOST] == HOST_2
    assert result["data"][CONF_MAC] == MAC_FORMATTED_2
    assert CONF_AREA_ID in result["data"]
    new_device_setups = [
        call
        for call in mock_setup_entry.call_args_list
        if call.args[1].data.get(CONF_MAC) == MAC_FORMATTED_2
    ]
    assert len(new_device_setups) == 1


async def test_options_flow_adds_discovered_device(
    hass: HomeAssistant, mock_setup_entry: AsyncMock, mock_discover_ac_devices
) -> None:
    """Test options flow adds another discovered AC to an existing entry."""
    existing = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: HOST, CONF_MAC: MAC_FORMATTED},
        unique_id=MAC_FORMATTED,
    )
    existing.add_to_hass(hass)
    mock_discover_ac_devices.return_value = [
        _discovered_device(HOST_2, MAC_BYTES_2, "Bedroom"),
    ]

    with patch.object(
        hass.config_entries, "async_reload", new_callable=AsyncMock
    ) as mock_reload:
        result = await hass.config_entries.options.async_init(existing.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {"discovered_devices": [MAC_FORMATTED_2]},
        )

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_AREA_ID: ar.async_get(hass).async_create("Bedroom").id},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert existing.data["devices"][0][CONF_MAC] == MAC_FORMATTED
    assert existing.data["devices"][1][CONF_HOST] == HOST_2
    assert existing.data["devices"][1][CONF_MAC] == MAC_FORMATTED_2
    assert CONF_AREA_ID in existing.data["devices"][1]
    mock_reload.assert_called_once_with(existing.entry_id)
