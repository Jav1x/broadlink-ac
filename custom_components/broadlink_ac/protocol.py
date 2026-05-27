"""Low-level Broadlink UDP protocol support."""

from __future__ import annotations

import random
import socket
import threading
import time

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .exceptions import BroadlinkACTimeoutError
from .models import COMMAND_AUTH

_INIT_KEY = "097628343fe99e23765c1513accf8b02"


class BroadlinkDeviceProtocol:
    """Low-level encrypted UDP transport for Broadlink devices."""

    def __init__(
        self,
        host: tuple[str, int],
        mac: bytes,
        timeout: int = 10,
        name: str | None = None,
        cloud: bool | None = None,
        devtype: int | None = None,
        update_interval: int = 0,
        bind_to_ip: str | None = None,
    ) -> None:
        """Initialize the protocol transport."""
        self.host = host
        self.mac = mac
        self.name = name
        self.cloud = cloud
        self.timeout = timeout
        self.devtype = devtype
        self.count = random.randrange(0xFFFF)
        self.key = bytearray(
            [
                0x09,
                0x76,
                0x28,
                0x34,
                0x3F,
                0xE9,
                0x9E,
                0x23,
                0x76,
                0x5C,
                0x15,
                0x13,
                0xAC,
                0xCF,
                0x8B,
                0x02,
            ]
        )
        self.iv = bytearray(
            [
                0x56,
                0x2E,
                0x17,
                0x99,
                0x6D,
                0x09,
                0x3D,
                0x28,
                0xDD,
                0xB3,
                0xBA,
                0x69,
                0x5A,
                0x2E,
                0x6F,
                0x58,
            ]
        )
        self.id = bytearray([0, 0, 0, 0])
        self.cs = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.cs.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.cs.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.type = "Unknown"
        self.lock = threading.Lock()
        self.update_interval = update_interval
        self.bind_to_ip = bind_to_ip
        self.aes = None
        self.update_aes(bytes.fromhex(_INIT_KEY))

    def update_aes(self, key: bytes) -> None:
        """Update AES."""
        self.aes = Cipher(
            algorithms.AES(bytes(key)), modes.CBC(self.iv), backend=default_backend()
        )

    def encrypt(self, payload: bytes) -> bytes:
        """Encrypt the payload."""
        encryptor = self.aes.encryptor()
        return encryptor.update(bytes(payload)) + encryptor.finalize()

    def decrypt(self, payload: bytes) -> bytes:
        """Decrypt the payload."""
        decryptor = self.aes.decryptor()
        return decryptor.update(bytes(payload)) + decryptor.finalize()

    def close(self) -> None:
        """Close the device socket."""
        self.cs.close()

    def auth(self) -> bool:
        """Authenticate with the Broadlink device."""
        payload = bytearray(0x50)
        payload[0x04:0x13] = b"111111111111111"
        payload[0x1E] = 0x01
        payload[0x2D] = 0x01
        payload[0x30:0x37] = b"Test  1"

        response = self.send_packet(COMMAND_AUTH, payload)
        decrypted_payload = self.decrypt(bytes(response[0x38:]))

        if not decrypted_payload:
            return False

        key = decrypted_payload[0x04:0x14]
        if len(key) % 16 != 0:
            return False

        self.id = decrypted_payload[0x00:0x04]
        self.key = key
        self.update_aes(key)
        return True

    def get_type(self) -> str:
        """Return the device type string."""
        return self.type

    def send_packet(self, command: int, payload: bytes | bytearray) -> bytearray:
        """Send an encrypted Broadlink packet and return the raw response."""
        self.count = (self.count + 1) & 0xFFFF
        packet = bytearray(0x38)
        packet[0x00] = 0x5A
        packet[0x01] = 0xA5
        packet[0x02] = 0xAA
        packet[0x03] = 0x55
        packet[0x04] = 0x5A
        packet[0x05] = 0xA5
        packet[0x06] = 0xAA
        packet[0x07] = 0x55
        packet[0x24] = 0x2A
        packet[0x25] = 0x4E
        packet[0x26] = command
        packet[0x28] = self.count & 0xFF
        packet[0x29] = self.count >> 8
        packet[0x2A:0x30] = self.mac[0:6]
        packet[0x30:0x34] = self.id[0:4]

        packet_checksum = 0xBEAF
        for byte in payload:
            packet_checksum += byte
            packet_checksum &= 0xFFFF

        encrypted_payload = self.encrypt(bytes(payload))

        packet[0x34] = packet_checksum & 0xFF
        packet[0x35] = packet_checksum >> 8
        packet.extend(encrypted_payload)

        packet_checksum = 0xBEAF
        for byte in packet:
            packet_checksum += byte
            packet_checksum &= 0xFFFF
        packet[0x20] = packet_checksum & 0xFF
        packet[0x21] = packet_checksum >> 8

        starttime = time.time()
        with self.lock:
            while True:
                try:
                    self.cs.sendto(packet, self.host)
                    self.cs.settimeout(5)
                    response = self.cs.recvfrom(1024)
                    break
                except socket.timeout as err:
                    if (time.time() - starttime) < self.timeout:
                        continue
                    raise BroadlinkACTimeoutError(200, self.host) from err

        return bytearray(response[0])
