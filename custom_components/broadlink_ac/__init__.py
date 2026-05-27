"""The broadlink_ac integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_MAC, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.typing import ConfigType

from .client import BroadlinkACClient
from .const import CONF_AREA_ID, DOMAIN
from .coordinator import BroadlinkACCoordinator, BroadlinkACData, BroadlinkACDeviceData
from .exceptions import BroadlinkACConnectionError

_PLATFORMS: list[Platform] = [Platform.CLIMATE, Platform.SWITCH]
CONF_DEVICES = "devices"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Broadlink integration."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up broadlink_ac from a config entry."""
    devices = entry.data.get(CONF_DEVICES)
    if devices is None:
        device = {CONF_HOST: entry.data[CONF_HOST], CONF_MAC: entry.data[CONF_MAC]}
        if CONF_AREA_ID in entry.data:
            device[CONF_AREA_ID] = entry.data[CONF_AREA_ID]
        devices = [device]

    runtime_devices: list[BroadlinkACDeviceData] = []
    try:
        for device in devices:
            host = device[CONF_HOST]
            mac = device[CONF_MAC]
            mac_bytes = bytes.fromhex(mac.replace(":", ""))
            client = await hass.async_add_executor_job(
                lambda host=host, mac_bytes=mac_bytes: BroadlinkACClient(
                    host=(host, 80),
                    mac=mac_bytes,
                    update_interval=30,
                )
            )
            coordinator = BroadlinkACCoordinator(hass, entry, client, host, mac)
            runtime_devices.append(
                BroadlinkACDeviceData(client=client, coordinator=coordinator)
            )
    except BroadlinkACConnectionError as err:
        for runtime_device in runtime_devices:
            runtime_device.client.close()
        raise ConfigEntryNotReady(
            f"Failed to communicate with Broadlink AC: {err}"
        ) from err

    await _async_migrate_entity_unique_ids(hass, entry)

    entry.runtime_data = BroadlinkACData(devices=runtime_devices)
    for runtime_device in runtime_devices:
        await runtime_device.coordinator.async_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)
    _async_apply_device_areas(hass, devices)

    return True


def _async_apply_device_areas(
    hass: HomeAssistant, devices: list[dict[str, str]]
) -> None:
    """Assign configured areas to Broadlink AC devices in the device registry."""
    device_registry = dr.async_get(hass)

    for device in devices:
        area_id = device.get(CONF_AREA_ID)
        if not area_id:
            continue

        mac_id = device[CONF_MAC].replace(":", "")
        device_entry = device_registry.async_get_device(
            identifiers={(DOMAIN, mac_id)}
        )
        if device_entry is not None:
            device_registry.async_update_device(device_entry.id, area_id=area_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)

    if unload_ok:
        data: BroadlinkACData = entry.runtime_data
        for device in data.devices:
            await device.coordinator.async_shutdown()
            device.client.close()

    return unload_ok


async def _async_migrate_entity_unique_ids(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Migrate old entry-id based entity unique IDs to MAC based IDs."""
    registry = er.async_get(hass)
    if CONF_MAC not in entry.data:
        return

    mac_id = entry.data[CONF_MAC].replace(":", "")

    migrations = (
        (Platform.CLIMATE, entry.entry_id, f"{mac_id}_climate"),
        (Platform.SWITCH, f"{entry.entry_id}_display", f"{mac_id}_display"),
    )

    for platform, old_unique_id, new_unique_id in migrations:
        entity_id = registry.async_get_entity_id(platform, DOMAIN, old_unique_id)
        if entity_id is None:
            continue
        if registry.async_get_entity_id(platform, DOMAIN, new_unique_id) is not None:
            continue
        registry.async_update_entity(entity_id, new_unique_id=new_unique_id)
