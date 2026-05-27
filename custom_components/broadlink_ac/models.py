"""Protocol constants and pure helpers for Broadlink AC devices."""

from __future__ import annotations

import struct
from typing import Any


MIN_TEMPERATURE = 16
MAX_TEMPERATURE = 32

COMMAND_AUTH = 0x65
COMMAND_AC = 0x6A
PACKET_TYPE_RESULT = 0x07
PACKET_TYPE_SET_ACK = 0x01
STATE_PACKET_LENGTH = 0x19

GET_AC_INFO = bytearray.fromhex("0C00BB0006800000020021011B7E0000")
GET_STATES = bytearray.fromhex("0C00BB0006800000020011012B7E0000")


class ACStatic:
    """Broadlink AC protocol enum values."""

    class FIXATION:
        """Fixation protocol values."""

        class VERTICAL:
            """Vertical fixation protocol values."""

            TOP = 0b00000001
            MIDDLE1 = 0b00000010
            MIDDLE2 = 0b00000011
            MIDDLE3 = 0b00000100
            BOTTOM = 0b00000101
            SWING = 0b00000110
            AUTO = 0b00000111

        class HORIZONTAL:
            """Horizontal fixation protocol values."""

            LEFT_FIX = 2
            LEFT_FLAP = 1
            LEFT_RIGHT_FIX = 7
            LEFT_RIGHT_FLAP = 0
            RIGHT_FIX = 6
            RIGHT_FLAP = 5
            ON = 0
            OFF = 1

    class FAN:
        """Fan speed protocol values."""

        LOW = 0b00000011
        MEDIUM = 0b00000010
        HIGH = 0b00000001
        AUTO = 0b00000101
        NONE = 0b00000000

    class MODE:
        """HVAC mode protocol values."""

        COOLING = 0b00000001
        DRY = 0b00000010
        HEATING = 0b00000100
        AUTO = 0b00000000
        FAN = 0b00000110

    class ONOFF:
        """On/off protocol values."""

        OFF = 0
        ON = 1


def get_key(values: dict[str, Any], search_value: Any) -> Any:
    """Return the first key whose value matches search_value."""
    for key, value in values.items():
        if value == search_value:
            return key
    return search_value


def checksum(data: bytes | bytearray) -> int:
    """Calculate the UDP payload checksum used by the AC protocol."""
    payload = bytearray(data)
    if len(payload) % 2 == 1:
        payload += struct.pack("!B", 0)

    result = 0
    for index in range(0, len(payload), 2):
        result += (payload[index] << 8) + payload[index + 1]

    result = (result >> 16) + (result & 0xFFFF)
    return ~result & 0xFFFF


def encode_temperature(value: float) -> tuple[int, int, float]:
    """Return the protocol temperature, half-degree flag, and clamped value."""
    temperature = float(value)
    if temperature < MIN_TEMPERATURE:
        return MIN_TEMPERATURE - 8, 0, float(MIN_TEMPERATURE)
    if temperature > MAX_TEMPERATURE:
        return MAX_TEMPERATURE - 8, 0, float(MAX_TEMPERATURE)
    if temperature.is_integer():
        return int(temperature - 8), 0, temperature
    return int(temperature - 8), 1, temperature


def default_status() -> dict[str, Any]:
    """Return the default raw AC status."""
    return {
        "temp": float(19),
        "fixation_v": ACStatic.FIXATION.VERTICAL.AUTO,
        "power": ACStatic.ONOFF.ON,
        "mode": ACStatic.MODE.AUTO,
        "sleep": ACStatic.ONOFF.OFF,
        "display": ACStatic.ONOFF.ON,
        "health": ACStatic.ONOFF.OFF,
        "ifeel": ACStatic.ONOFF.OFF,
        "fixation_h": ACStatic.FIXATION.HORIZONTAL.LEFT_RIGHT_FIX,
        "fanspeed": ACStatic.FAN.AUTO,
        "turbo": ACStatic.ONOFF.OFF,
        "mute": ACStatic.ONOFF.OFF,
        "clean": ACStatic.ONOFF.OFF,
        "mildew": ACStatic.ONOFF.OFF,
        "macaddress": None,
        "hostip": None,
        "lastupdate": None,
        "ambient_temp": None,
        "devicename": None,
    }


def make_nice_status(status: dict[str, Any]) -> dict[str, Any]:
    """Convert raw AC status values to the existing Home Assistant-facing dict."""
    status_nice = {
        "temp": status["temp"],
        "ambient_temp": status["ambient_temp"],
        "power": get_key(ACStatic.ONOFF.__dict__, status["power"]),
        "fixation_v": get_key(
            ACStatic.FIXATION.VERTICAL.__dict__, status["fixation_v"]
        ),
        "mode": get_key(ACStatic.MODE.__dict__, status["mode"]),
        "sleep": get_key(ACStatic.ONOFF.__dict__, status["sleep"]),
        "mildew": get_key(ACStatic.ONOFF.__dict__, status["mildew"]),
        "health": get_key(ACStatic.ONOFF.__dict__, status["health"]),
        "fixation_h": get_key(
            ACStatic.FIXATION.HORIZONTAL.__dict__, status["fixation_h"]
        ),
        "ifeel": get_key(ACStatic.ONOFF.__dict__, status["ifeel"]),
        "mute": get_key(ACStatic.ONOFF.__dict__, status["mute"]),
        "turbo": get_key(ACStatic.ONOFF.__dict__, status["turbo"]),
        "clean": get_key(ACStatic.ONOFF.__dict__, status["clean"]),
        "macaddress": status["macaddress"],
        "device_name": status["devicename"],
    }

    display = ACStatic.ONOFF.OFF if status["display"] else ACStatic.ONOFF.ON
    status_nice["display"] = get_key(ACStatic.ONOFF.__dict__, display)

    if status["power"] == ACStatic.ONOFF.OFF:
        status_nice["mode_homekit"] = "Off"
        status_nice["mode_homeassistant"] = "off"
    elif status["mode"] == ACStatic.MODE.AUTO:
        status_nice["mode_homekit"] = "Auto"
        status_nice["mode_homeassistant"] = "auto"
    elif status["mode"] == ACStatic.MODE.HEATING:
        status_nice["mode_homekit"] = "HeatOn"
        status_nice["mode_homeassistant"] = "heat"
    elif status["mode"] == ACStatic.MODE.COOLING:
        status_nice["mode_homekit"] = "CoolOn"
        status_nice["mode_homeassistant"] = "cool"
    elif status["mode"] == ACStatic.MODE.DRY:
        status_nice["mode_homekit"] = "Error"
        status_nice["mode_homeassistant"] = "dry"
    elif status["mode"] == ACStatic.MODE.FAN:
        status_nice["mode_homekit"] = "Error"
        status_nice["mode_homeassistant"] = "fan_only"
    else:
        status_nice["mode_homekit"] = "Error"
        status_nice["mode_homeassistant"] = "Error"

    status_nice["fanspeed"] = get_key(ACStatic.FAN.__dict__, status["fanspeed"])
    status_nice["fanspeed_homeassistant"] = status_nice["fanspeed"].title()

    if status_nice["mute"] == "ON":
        status_nice["fanspeed_homeassistant"] = "Mute"
        status_nice["fanspeed"] = "MUTE"
    elif status_nice["turbo"] == "ON":
        status_nice["fanspeed_homeassistant"] = "Turbo"
        status_nice["fanspeed"] = "TURBO"

    return status_nice
