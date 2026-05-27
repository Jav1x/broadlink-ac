from __future__ import annotations

import re
from dataclasses import dataclass
from ipaddress import ip_address
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_MAC
from homeassistant.data_entry_flow import FlowResult, SectionConfig, section
from homeassistant.helpers import selector
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig

from .client import BroadlinkACClient
from .const import CONF_AREA_ID, DOMAIN
from .discovery import BroadlinkACDiscoveryDevice, discover_ac_devices, discover_mac
from .exceptions import BroadlinkACConnectionError

CONF_DEVICES = "devices"
CONF_DISCOVERED_DEVICES = "discovered_devices"
CONF_ADD_MANUAL = "add_manual_device"
CONF_DEVICE_AREAS = "device_areas"
SECTION_MANUAL_DEVICES = "manual_devices_section"
DISCOVERY_TIMEOUT = 5
MAX_MANUAL_DEVICES = 10
MENU_MANUAL_ADD_ANOTHER = "add_another"
MENU_MANUAL_CONTINUE = "continue_setup"

_IPV4_PATTERN = re.compile(
    r"^(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)$"
)
_MAC_PATTERN = re.compile(
    r"^(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}$|^[0-9a-fA-F]{12}$"
)


def _format_mac(mac: str | bytes) -> str:
    """Normalize a MAC address to Home Assistant's colon-separated format."""
    if isinstance(mac, bytes):
        cleaned = mac.hex()
    else:
        cleaned = mac.replace(":", "").replace("-", "").strip().lower()

    if len(cleaned) != 12:
        raise ValueError

    return format_mac(
        ":".join(cleaned[index : index + 2] for index in range(0, 12, 2))
    )


def _is_valid_ipv4(host: str) -> bool:
    """Return True if host is a valid IPv4 address."""
    if not _IPV4_PATTERN.match(host):
        return False
    try:
        ip_address(host)
    except ValueError:
        return False
    return True


def _is_valid_mac(mac: str) -> bool:
    """Return True if mac looks like a MAC address."""
    return bool(_MAC_PATTERN.match(mac.strip()))


def _host_text_selector() -> TextSelector:
    """Return a text selector for an IPv4 host field."""
    return TextSelector(
        TextSelectorConfig(
            type=selector.TextSelectorType.TEXT,
            autocomplete="off",
        )
    )


def _mac_text_selector() -> TextSelector:
    """Return a text selector for an optional MAC address field."""
    return TextSelector(
        TextSelectorConfig(
            type=selector.TextSelectorType.TEXT,
            autocomplete="off",
        )
    )


def _manual_device_schema() -> vol.Schema:
    """Return the schema for entering one manual device."""
    return vol.Schema(
        {
            vol.Required(CONF_HOST): _host_text_selector(),
            vol.Optional(CONF_MAC, default=""): _mac_text_selector(),
        }
    )


async def _async_device_from_manual_input(
    hass,
    host_input: str | None,
    mac: str,
    host_error_key: str = CONF_HOST,
    mac_error_key: str = CONF_MAC,
) -> tuple[dict[str, str] | None, dict[str, str]]:
    """Parse and validate manual input into one device config dictionary."""
    if not host_input:
        if mac:
            return None, {host_error_key: "invalid_host"}
        return None, {}

    if not isinstance(host_input, str):
        return None, {host_error_key: "invalid_host"}

    host = host_input.strip()
    if not host:
        return None, {}

    if not _is_valid_ipv4(host):
        return None, {host_error_key: "invalid_host"}

    if mac:
        if not _is_valid_mac(mac):
            return None, {mac_error_key: "invalid_mac"}
        try:
            return {CONF_HOST: host, CONF_MAC: _format_mac(mac)}, {}
        except ValueError:
            return None, {mac_error_key: "invalid_mac"}

    discovered_mac = await hass.async_add_executor_job(discover_mac, host)
    if discovered_mac is None:
        return None, {mac_error_key: "mac_not_found"}

    return {CONF_HOST: host, CONF_MAC: _format_mac(discovered_mac)}, {}


def _entry_devices(entry: config_entries.ConfigEntry) -> list[dict[str, str]]:
    """Return devices stored in a config entry."""
    if CONF_DEVICES in entry.data:
        return list(entry.data[CONF_DEVICES])
    device = {CONF_HOST: entry.data[CONF_HOST], CONF_MAC: entry.data[CONF_MAC]}
    if CONF_AREA_ID in entry.data:
        device[CONF_AREA_ID] = entry.data[CONF_AREA_ID]
    return [device]


def _test_device_connection(host: str, mac: str) -> None:
    """Verify that a Broadlink AC device accepts a connection."""
    mac_bytes = bytes.fromhex(mac.replace(":", ""))
    client = BroadlinkACClient(host=(host, 80), mac=mac_bytes, update_interval=0)
    client.close()


async def _async_test_device_connection(hass, host: str, mac: str) -> None:
    """Verify device connectivity in an executor."""
    await hass.async_add_executor_job(_test_device_connection, host, mac)


@dataclass
class DeviceConnectionResult:
    """Connection test results for a batch of devices."""

    reachable: list[dict[str, str]]
    failed: dict[str, str]


async def _async_test_device_connections(
    hass, devices: list[dict[str, str]]
) -> DeviceConnectionResult:
    """Test connectivity for each device and return reachable and failed devices."""
    reachable: list[dict[str, str]] = []
    failed: dict[str, str] = {}

    for device in devices:
        try:
            await _async_test_device_connection(
                hass, device[CONF_HOST], device[CONF_MAC]
            )
        except BroadlinkACConnectionError:
            failed[device[CONF_MAC]] = "cannot_connect"
        except OSError:
            failed[device[CONF_MAC]] = "cannot_connect"
        else:
            reachable.append(device)

    return DeviceConnectionResult(reachable=reachable, failed=failed)


def _setup_data_schema(
    discovered_devices: dict[str, BroadlinkACDiscoveryDevice] | None,
    *,
    failed_macs: set[str] | None = None,
    manual_devices_collected: list[dict[str, str]] | None = None,
) -> vol.Schema:
    """Return the setup/options form schema with translated selectors."""
    schema: dict = {}
    failed_macs = failed_macs or set()

    if discovered_devices:
        options = [
            {
                "value": mac,
                "label": f"{device.name} ({device.host})",
            }
            for mac, device in discovered_devices.items()
            if mac not in failed_macs
        ]
        if options:
            schema[
                vol.Optional(CONF_DISCOVERED_DEVICES, default=[])
            ] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options,
                    multiple=True,
                    mode=selector.SelectSelectorMode.LIST,
                    translation_key=CONF_DISCOVERED_DEVICES,
                )
            )
        schema[vol.Optional(SECTION_MANUAL_DEVICES)] = section(
            vol.Schema(
                {
                    vol.Optional(CONF_ADD_MANUAL, default=False): selector.BooleanSelector()
                }
            ),
            SectionConfig(collapsed=True),
        )
    elif manual_devices_collected:
        schema[vol.Optional(CONF_ADD_MANUAL, default=False)] = selector.BooleanSelector()
    else:
        schema.update(_manual_device_schema().schema)

    return vol.Schema(schema)


def _wants_manual_device(user_input: dict) -> bool:
    """Return True when the user asked to add a device manually."""
    if user_input.get(CONF_ADD_MANUAL):
        return True
    section_data = user_input.get(SECTION_MANUAL_DEVICES)
    return isinstance(section_data, dict) and bool(
        section_data.get(CONF_ADD_MANUAL)
    )


def _configured_macs(hass) -> set[str]:
    """Return all MAC addresses already configured for this integration."""
    macs: set[str] = set()
    for entry in hass.config_entries.async_entries(DOMAIN):
        for device in _entry_devices(entry):
            macs.add(device[CONF_MAC])
    return macs


def _manual_devices_placeholder(devices: list[dict[str, str]]) -> str:
    """Return a user-facing summary of manually added devices."""
    if not devices:
        return ""
    lines = "\n".join(
        f"• {device[CONF_HOST]} ({device[CONF_MAC]})" for device in devices
    )
    return f"\n\nManually added:\n{lines}"


def _device_label(
    device: dict[str, str],
    discovered_devices: dict[str, BroadlinkACDiscoveryDevice] | None,
) -> str:
    """Return a user-facing label for a device."""
    mac = device[CONF_MAC]
    if discovered_devices and mac in discovered_devices:
        discovered = discovered_devices[mac]
        return f"{discovered.name} ({discovered.host})"
    return f"{device[CONF_HOST]} ({mac})"


class _BroadlinkACFlowMixin:
    """Shared config/options flow logic."""

    hass: Any
    _discovered_devices: dict[str, BroadlinkACDiscoveryDevice] | None
    _manual_devices_collected: list[dict[str, str]]
    _pending_devices: list[dict[str, str]]
    _failed_connections: dict[str, str]
    _last_user_input: dict | None
    _tested_devices_by_mac: dict[str, dict[str, str]]

    def _init_flow_state(self) -> None:
        """Initialize mutable flow state."""
        self._discovered_devices = None
        self._manual_devices_collected = []
        self._pending_devices = []
        self._failed_connections = {}
        self._last_user_input = None
        self._tested_devices_by_mac = {}

    async def _async_discover(self) -> None:
        """Discover devices once for this flow."""
        if self._discovered_devices is not None:
            return

        discovered = await self.hass.async_add_executor_job(
            discover_ac_devices, DISCOVERY_TIMEOUT
        )
        configured_macs = self._configured_macs()
        self._discovered_devices = {
            _format_mac(device.mac): device
            for device in discovered
            if _format_mac(device.mac) not in configured_macs
        }

    async def _async_devices_from_user_input(
        self, user_input: dict
    ) -> tuple[list[dict[str, str]], dict[str, str]]:
        """Return selected discovered devices plus optional manual devices."""
        devices = []
        for mac in user_input.get(CONF_DISCOVERED_DEVICES, []) or []:
            if self._discovered_devices is None or mac not in self._discovered_devices:
                continue
            discovered = self._discovered_devices[mac]
            devices.append({CONF_HOST: discovered.host, CONF_MAC: mac})

        devices.extend(self._manual_devices_collected)

        if self._discovered_devices:
            if not devices:
                return devices, {"base": "no_device_selected"}
            return devices, {}

        if self._manual_devices_collected and not (user_input.get(CONF_HOST) or "").strip():
            return devices, {}

        manual_device, errors = await _async_device_from_manual_input(
            self.hass,
            user_input.get(CONF_HOST),
            (user_input.get(CONF_MAC) or "").strip(),
        )
        if errors:
            return devices, errors
        if manual_device is not None:
            devices.append(manual_device)

        if not devices:
            return devices, {"base": "no_device_selected"}

        return devices, {}

    def _connection_errors_for_user_step(
        self,
        devices: list[dict[str, str]],
        failed: dict[str, str],
        user_input: dict,
    ) -> dict[str, str]:
        """Map connection failures back to the user step form."""
        errors: dict[str, str] = {}
        if not any(device[CONF_MAC] not in failed for device in devices):
            errors["base"] = "cannot_connect"
            return errors

        if not self._discovered_devices:
            for device in devices:
                if device[CONF_MAC] in failed:
                    errors[CONF_HOST] = failed[device[CONF_MAC]]
                    break
            return errors

        return errors

    def _connection_placeholders(self) -> dict[str, str]:
        """Build placeholders for the connection result step."""
        successful = "\n".join(
            f"• {_device_label(device, self._discovered_devices)}"
            for device in self._pending_devices
        )
        failed = "\n".join(
            f"• {_device_label(self._tested_devices_by_mac[mac], self._discovered_devices)}"
            for mac in sorted(self._failed_connections)
        )
        return {
            "successful_devices": successful or "—",
            "failed_devices": failed or "—",
        }

    def _user_step_placeholders(self) -> dict[str, str]:
        """Build placeholders for the user/init step."""
        return {
            "failed_devices": (
                f"\nCould not connect to:\n"
                f"{self._connection_placeholders()['failed_devices']}"
                if self._failed_connections
                else ""
            ),
            "manual_devices_list": _manual_devices_placeholder(
                self._manual_devices_collected
            ),
        }

    def _area_schema(self) -> vol.Schema:
        """Return the area assignment schema."""
        if len(self._pending_devices) == 1:
            return vol.Schema(
                {
                    vol.Required(CONF_AREA_ID): selector.AreaSelector(),
                }
            )

        return vol.Schema(
            {
                vol.Required(CONF_DEVICE_AREAS): selector.ObjectSelector(
                    selector.ObjectSelectorConfig(
                        multiple=True,
                        translation_key=CONF_DEVICE_AREAS,
                        fields={
                            CONF_MAC: {
                                "required": True,
                                "selector": {"text": None},
                            },
                            CONF_AREA_ID: {
                                "required": True,
                                "selector": {"area": None},
                            },
                        },
                    )
                )
            }
        )

    def _area_suggested_values(self) -> dict[str, Any]:
        """Return suggested values for the area step."""
        if len(self._pending_devices) == 1:
            return {}

        return {
            CONF_DEVICE_AREAS: [
                {CONF_MAC: device[CONF_MAC], CONF_AREA_ID: None}
                for device in self._pending_devices
            ]
        }

    def _devices_with_areas(self, user_input: dict) -> list[dict[str, str]]:
        """Attach selected areas to pending devices."""
        devices = [dict(device) for device in self._pending_devices]

        if len(devices) == 1:
            devices[0][CONF_AREA_ID] = user_input[CONF_AREA_ID]
            return devices

        areas_by_mac = {
            row[CONF_MAC]: row[CONF_AREA_ID]
            for row in user_input[CONF_DEVICE_AREAS]
        }
        for device in devices:
            device[CONF_AREA_ID] = areas_by_mac[device[CONF_MAC]]
        return devices

    def _entry_data(self, devices: list[dict[str, str]]) -> dict:
        """Return config entry data."""
        if len(devices) == 1:
            return {
                CONF_HOST: devices[0][CONF_HOST],
                CONF_MAC: devices[0][CONF_MAC],
                CONF_AREA_ID: devices[0][CONF_AREA_ID],
            }
        return {CONF_DEVICES: devices}

    async def _async_continue_with_devices(
        self, devices: list[dict[str, str]], user_input: dict
    ) -> tuple[FlowResult | None, dict[str, str]]:
        """Test connections and advance the flow, or return field errors."""
        result = await _async_test_device_connections(self.hass, devices)
        self._tested_devices_by_mac = {device[CONF_MAC]: device for device in devices}
        self._pending_devices = result.reachable
        self._failed_connections = result.failed

        if not self._pending_devices:
            return None, self._connection_errors_for_user_step(
                devices, result.failed, user_input
            )

        if result.failed:
            return await self.async_step_connection_result(), {}

        return await self.async_step_area(), {}

    async def async_step_manual_device(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Add one manual device using validated text fields."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if len(self._manual_devices_collected) >= MAX_MANUAL_DEVICES:
                errors["base"] = "too_many_manual_devices"
            else:
                manual_device, errors = await _async_device_from_manual_input(
                    self.hass,
                    user_input.get(CONF_HOST),
                    (user_input.get(CONF_MAC) or "").strip(),
                )
                if not errors and manual_device is not None:
                    self._manual_devices_collected.append(manual_device)
                    return await self.async_step_manual_device_menu()

        schema = _manual_device_schema()
        return self.async_show_form(
            step_id="manual_device",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_manual_device_menu(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Let the user add another manual device or continue setup."""
        return self.async_show_menu(
            step_id="manual_device_menu",
            menu_options=[MENU_MANUAL_ADD_ANOTHER, MENU_MANUAL_CONTINUE],
        )

    async def async_step_add_another(self, user_input: dict | None = None) -> FlowResult:
        """Add another manually entered device."""
        if len(self._manual_devices_collected) >= MAX_MANUAL_DEVICES:
            return await self.async_step_user()
        return await self.async_step_manual_device()

    async def async_step_continue_setup(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Return to the main setup step."""
        return await self.async_step_user()

    async def _async_process_user_step(
        self, user_input: dict
    ) -> tuple[FlowResult | None, dict[str, str]]:
        """Validate the user/init step and advance the flow."""
        if _wants_manual_device(user_input):
            return await self.async_step_manual_device(), {}

        if len(self._manual_devices_collected) >= MAX_MANUAL_DEVICES:
            return None, {"base": "too_many_manual_devices"}

        devices, errors = await self._async_devices_from_user_input(user_input)
        if errors:
            return None, errors

        devices = self._filter_configured_devices(devices)
        if not devices:
            return None, {"base": "already_configured"}

        return await self._async_continue_with_devices(devices, user_input)


class BroadlinkACConfigFlow(_BroadlinkACFlowMixin, config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Broadlink AC."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._init_flow_state()

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return BroadlinkACOptionsFlow()

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Handle the initial step."""
        await self._async_discover()
        errors: dict[str, str] = {}

        if user_input is not None:
            self._last_user_input = user_input
            flow_result, errors = await self._async_process_user_step(user_input)
            if flow_result is not None:
                return flow_result

        return self.async_show_form(
            step_id="user",
            data_schema=_setup_data_schema(
                self._discovered_devices,
                failed_macs=set(self._failed_connections),
                manual_devices_collected=self._manual_devices_collected,
            ),
            errors=errors,
            description_placeholders=self._user_step_placeholders(),
        )

    async def async_step_connection_result(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Show which devices connected successfully or failed."""
        if user_input is not None:
            if not self._pending_devices:
                return await self.async_step_user()
            return await self.async_step_area()

        return self.async_show_form(
            step_id="connection_result",
            description_placeholders=self._connection_placeholders(),
        )

    async def async_step_area(self, user_input: dict | None = None) -> FlowResult:
        """Assign an area to each device that will be added."""
        if user_input is not None:
            devices = self._devices_with_areas(user_input)
            unique_id = ",".join(sorted(device[CONF_MAC] for device in devices))
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=self._entry_title(devices),
                data=self._entry_data(devices),
            )

        schema = self._area_schema()
        schema = self.add_suggested_values_to_schema(
            schema, self._area_suggested_values()
        )
        return self.async_show_form(step_id="area", data_schema=schema)

    def _configured_macs(self) -> set[str]:
        """Return all MAC addresses already configured for this integration."""
        return _configured_macs(self.hass)

    def _filter_configured_devices(
        self, devices: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        """Remove devices already configured in Home Assistant."""
        configured_macs = self._configured_macs()
        return [
            device for device in devices if device[CONF_MAC] not in configured_macs
        ]

    def _entry_title(self, devices: list[dict[str, str]]) -> str:
        """Return a title for a config entry."""
        if len(devices) == 1:
            return f"Broadlink AC ({devices[0][CONF_HOST]})"
        return f"Broadlink AC ({len(devices)} devices)"


class BroadlinkACOptionsFlow(_BroadlinkACFlowMixin, config_entries.OptionsFlow):
    """Handle options for Broadlink AC."""

    def __init__(self) -> None:
        """Initialize the options flow."""
        self._init_flow_state()

    async def async_step_init(self, user_input: dict | None = None) -> FlowResult:
        """Add one or more devices to an existing config entry."""
        await self._async_discover()
        errors: dict[str, str] = {}

        if user_input is not None:
            self._last_user_input = user_input
            flow_result, errors = await self._async_process_user_step(user_input)
            if flow_result is not None:
                return flow_result

        return self.async_show_form(
            step_id="init",
            data_schema=_setup_data_schema(
                self._discovered_devices,
                failed_macs=set(self._failed_connections),
                manual_devices_collected=self._manual_devices_collected,
            ),
            errors=errors,
            description_placeholders=self._user_step_placeholders(),
        )

    async def async_step_connection_result(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Show which devices connected successfully or failed."""
        if user_input is not None:
            if not self._pending_devices:
                return await self.async_step_init()
            return await self.async_step_area()

        return self.async_show_form(
            step_id="connection_result",
            description_placeholders=self._connection_placeholders(),
        )

    async def async_step_area(self, user_input: dict | None = None) -> FlowResult:
        """Assign an area to each new device."""
        if user_input is not None:
            new_devices = self._devices_with_areas(user_input)
            new_data = {
                **self.config_entry.data,
                CONF_DEVICES: _entry_devices(self.config_entry) + new_devices,
            }
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=new_data
            )
            self.hass.async_create_task(
                self.hass.config_entries.async_reload(self.config_entry.entry_id)
            )
            return self.async_create_entry(title="", data={})

        schema = self._area_schema()
        schema = self.add_suggested_values_to_schema(
            schema, self._area_suggested_values()
        )
        return self.async_show_form(step_id="area", data_schema=schema)

    def _configured_macs(self) -> set[str]:
        """Return all MAC addresses already configured for this integration."""
        return _configured_macs(self.hass)

    def _filter_configured_devices(
        self, devices: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        """Remove devices already configured in Home Assistant."""
        configured_macs = self._configured_macs()
        return [
            device for device in devices if device[CONF_MAC] not in configured_macs
        ]
