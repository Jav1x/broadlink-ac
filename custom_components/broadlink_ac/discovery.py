"""Device discovery for Broadlink AC devices."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import socket
import time

from .client import BroadlinkACClient
from .protocol import BroadlinkDeviceProtocol

DANHAM_BUSH_DEVICE_TYPE = 0x4E2A


@dataclass(frozen=True)
class BroadlinkACDiscoveryDevice:
    """A discovered Broadlink AC device."""

    host: str
    mac: bytes
    name: str
    devtype: int


def _get_default_bind_ip() -> str:
    """Return the local IP address used for UDP discovery."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 53))
        return probe.getsockname()[0]
    finally:
        probe.close()


def _build_discovery_packet(bind_to_ip: str, port: int) -> bytearray:
    """Build a Broadlink UDP discovery packet."""
    address = bind_to_ip.split(".")
    now = datetime.now()
    timezone = int(time.timezone / -3600)
    packet = bytearray(0x30)
    year = now.year

    if timezone < 0:
        packet[0x08] = 0xFF + timezone - 1
        packet[0x09] = 0xFF
        packet[0x0A] = 0xFF
        packet[0x0B] = 0xFF
    else:
        packet[0x08] = timezone
        packet[0x09] = 0
        packet[0x0A] = 0
        packet[0x0B] = 0
    packet[0x0C] = year & 0xFF
    packet[0x0D] = year >> 8
    packet[0x0E] = now.minute
    packet[0x0F] = now.hour
    packet[0x10] = int(str(year)[2:])
    packet[0x11] = now.isoweekday()
    packet[0x12] = now.day
    packet[0x13] = now.month
    packet[0x18] = int(address[0])
    packet[0x19] = int(address[1])
    packet[0x1A] = int(address[2])
    packet[0x1B] = int(address[3])
    packet[0x1C] = port & 0xFF
    packet[0x1D] = port >> 8
    packet[0x26] = 6

    checksum = 0xBEAF
    for byte in packet:
        checksum += byte
    checksum &= 0xFFFF
    packet[0x20] = checksum & 0xFF
    packet[0x21] = checksum >> 8
    return packet


def _open_discovery_socket(bind_to_ip: str | None = None) -> tuple[socket.socket, str]:
    """Open a bound UDP socket for Broadlink discovery."""
    if bind_to_ip is None:
        bind_to_ip = _get_default_bind_ip()

    cs = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    cs.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    cs.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    cs.bind((bind_to_ip, 0))
    return cs, bind_to_ip


def _device_from_response(
    response: tuple[bytes, tuple[str, int]]
) -> BroadlinkDeviceProtocol:
    """Create a device client from a Broadlink discovery response."""
    responsepacket = bytearray(response[0])
    host = response[1]
    devtype = responsepacket[0x34] | responsepacket[0x35] << 8
    mac = bytes(responsepacket[0x3A:0x40][::-1])
    name = responsepacket[0x40:].split(b"\x00")[0].decode("utf-8")
    if not name:
        name = mac.hex()
    cloud = bool(responsepacket[-1])

    if devtype == DANHAM_BUSH_DEVICE_TYPE:
        return BroadlinkACClient(
            host=host,
            mac=mac,
            name=name,
            cloud=cloud,
            devtype=devtype,
            update_interval=0,
        )

    return BroadlinkDeviceProtocol(
        host=host,
        mac=mac,
        name=name,
        cloud=cloud,
        devtype=devtype,
        update_interval=0,
    )


def _discovery_device_from_response(
    response: tuple[bytes, tuple[str, int]]
) -> BroadlinkACDiscoveryDevice | None:
    """Parse a Broadlink discovery response without opening a device client."""
    responsepacket = bytearray(response[0])
    devtype = responsepacket[0x34] | responsepacket[0x35] << 8
    if devtype != DANHAM_BUSH_DEVICE_TYPE:
        return None

    mac = bytes(responsepacket[0x3A:0x40][::-1])
    name = responsepacket[0x40:].split(b"\x00")[0].decode("utf-8")
    if not name:
        name = mac.hex()

    return BroadlinkACDiscoveryDevice(
        host=response[1][0],
        mac=mac,
        name=name,
        devtype=devtype,
    )


def discover_ac_devices(
    timeout: float = 5, bind_to_ip: str | None = None
) -> list[BroadlinkACDiscoveryDevice]:
    """Discover Broadlink AC devices on the local network."""
    cs, bind_to_ip = _open_discovery_socket(bind_to_ip)

    try:
        port = cs.getsockname()[1]
        starttime = time.time()
        devices_by_mac: dict[bytes, BroadlinkACDiscoveryDevice] = {}
        packet = _build_discovery_packet(bind_to_ip, port)

        cs.sendto(packet, ("255.255.255.255", 80))
        while (time.time() - starttime) < timeout:
            cs.settimeout(timeout - (time.time() - starttime))
            try:
                response = cs.recvfrom(1024)
            except socket.timeout:
                return list(devices_by_mac.values())

            device = _discovery_device_from_response(response)
            if device is not None:
                devices_by_mac[device.mac] = device

        return list(devices_by_mac.values())
    finally:
        cs.close()


def discover_devices(
    timeout: float | None = None, bind_to_ip: str | None = None
) -> list[BroadlinkDeviceProtocol] | BroadlinkDeviceProtocol:
    """Discover Broadlink devices on the local network."""
    cs, bind_to_ip = _open_discovery_socket(bind_to_ip)

    try:
        port = cs.getsockname()[1]
        starttime = time.time()
        devices = []
        packet = _build_discovery_packet(bind_to_ip, port)

        cs.sendto(packet, ("255.255.255.255", 80))
        if timeout is None:
            return _device_from_response(cs.recvfrom(1024))

        while (time.time() - starttime) < timeout:
            cs.settimeout(timeout - (time.time() - starttime))
            try:
                response = cs.recvfrom(1024)
            except socket.timeout:
                return devices
            devices.append(_device_from_response(response))

        return devices
    finally:
        cs.close()


def discover_mac(
    host: str, timeout: float = 5, bind_to_ip: str | None = None
) -> bytes | None:
    """Discover a Broadlink device MAC address by host."""
    cs, bind_to_ip = _open_discovery_socket(bind_to_ip)
    port = cs.getsockname()[1]
    starttime = time.time()
    packet = _build_discovery_packet(bind_to_ip, port)

    try:
        cs.sendto(packet, ("255.255.255.255", 80))
        while (time.time() - starttime) < timeout:
            cs.settimeout(timeout - (time.time() - starttime))
            try:
                response = cs.recvfrom(1024)
            except socket.timeout:
                return None

            if response[1][0] != host:
                continue

            responsepacket = bytearray(response[0])
            mac = responsepacket[0x3A:0x40]
            return bytes(mac[::-1])
    finally:
        cs.close()

    return None
