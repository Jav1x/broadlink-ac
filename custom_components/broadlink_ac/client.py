"""Broadlink AC client."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from .exceptions import BroadlinkACConnectionError
from .models import (
    ACStatic,
    COMMAND_AC,
    GET_AC_INFO,
    GET_STATES,
    PACKET_TYPE_RESULT,
    PACKET_TYPE_SET_ACK,
    STATE_PACKET_LENGTH,
    checksum,
    default_status,
    encode_temperature,
    make_nice_status,
)
from .protocol import BroadlinkDeviceProtocol

_LOGGER = logging.getLogger(__name__)


class BroadlinkACClient(BroadlinkDeviceProtocol):
    """Client for Broadlink AC DB devices."""

    type = "ac_db"
    STATIC = ACStatic

    def __init__(
        self,
        host: tuple[str, int],
        mac: bytes,
        name: str | None = None,
        cloud: bool | None = None,
        update_interval: int = 0,
        devtype: int | None = None,
        bind_to_ip: str | None = None,
    ) -> None:
        """Initialize the AC client."""
        super().__init__(
            host,
            mac,
            name=name,
            cloud=cloud,
            devtype=devtype,
            update_interval=update_interval,
            bind_to_ip=bind_to_ip,
        )

        self.status = default_status()
        self.logger = _LOGGER
        self.type = "ac_db"
        self.operation_lock = threading.RLock()
        self.update_interval = update_interval
        self.status["macaddress"] = "".join(format(x, "02x") for x in mac)
        self.status["hostip"] = host
        self.status["name"] = name
        self.status["lastupdate"] = 0

        self.logger.debug("Authenticating with Broadlink AC")
        try:
            if self.auth() is False:
                raise BroadlinkACConnectionError("Authentication failed")
        except BroadlinkACConnectionError:
            self.close()
            raise

        self.logger.debug("Broadlink AC authenticated")

    def get_ac_status(self, force_update: bool = False) -> dict[str, Any] | int | bool:
        """Get current AC status."""
        with self.operation_lock:
            return self._get_ac_status(force_update)

    def _get_ac_status(self, force_update: bool = False) -> dict[str, Any] | int | bool:
        """Get current AC status without acquiring the operation lock."""
        self.logger.debug("Last update was: %s", self.status["lastupdate"])
        if (
            force_update is False
            and (self.status["lastupdate"] + self.update_interval) > time.time()
        ):
            return make_nice_status(self.status)

        self.logger.debug("Getting AC info")
        self.get_ac_info()
        self.logger.debug("AC info retrieved")
        self.logger.debug("Getting AC states")
        status = self.get_ac_states(True)
        self.logger.debug("AC states retrieved")
        return status

    def set_temperature(self, temperature: float) -> dict[str, Any]:
        """Set target temperature."""
        with self.operation_lock:
            self.logger.debug("Setting temperature to %s", temperature)
            self.get_ac_states()
            self.status["temp"] = float(temperature)
            return self._send_status_and_refresh()

    def switch_off(self) -> dict[str, Any]:
        """Switch the AC off."""
        with self.operation_lock:
            self.get_ac_states()
            self.status["power"] = ACStatic.ONOFF.OFF
            return self._send_status_and_refresh()

    def switch_on(self) -> dict[str, Any]:
        """Switch the AC on."""
        with self.operation_lock:
            self.get_ac_states()
            self.status["power"] = ACStatic.ONOFF.ON
            return self._send_status_and_refresh()

    def set_mode(self, mode_text: str) -> dict[str, Any] | bool:
        """Set raw AC mode."""
        with self.operation_lock:
            self.get_ac_states()
            mode = ACStatic.MODE.__dict__.get(mode_text.upper())
            if mode is not None:
                self.status["mode"] = mode
                return self._send_status_and_refresh()
            self.logger.debug("Not found mode value %s", mode_text)
            return False

    def set_fanspeed(self, mode_text: str) -> dict[str, Any] | bool:
        """Set fan speed."""
        with self.operation_lock:
            self.get_ac_states()
            mode = ACStatic.FAN.__dict__.get(mode_text.upper())
            if mode is not None:
                self.status["fanspeed"] = mode
                self.status["turbo"] = ACStatic.ONOFF.OFF
                self.status["mute"] = ACStatic.ONOFF.OFF
                return self._send_status_and_refresh()
            self.logger.debug("Not found fan speed value %s", mode_text)
            return False

    def set_mute(self, value: str) -> dict[str, Any] | bool:
        """Set mute fan mode."""
        with self.operation_lock:
            self.get_ac_states()
            mode = ACStatic.ONOFF.__dict__.get(value)
            if mode is not None:
                self.status["mute"] = mode
                self.status["turbo"] = ACStatic.ONOFF.OFF
                self.status["fanspeed"] = ACStatic.FAN.NONE
                return self._send_status_and_refresh()
            self.logger.debug("Not found mute value %s", value)
            return False

    def set_turbo(self, value: str) -> dict[str, Any] | bool:
        """Set turbo fan mode."""
        with self.operation_lock:
            self.get_ac_states()
            mode = ACStatic.ONOFF.__dict__.get(value)
            if mode is not None:
                self.status["turbo"] = mode
                self.status["mute"] = ACStatic.ONOFF.OFF
                self.status["fanspeed"] = ACStatic.FAN.NONE
                return self._send_status_and_refresh()
            self.logger.debug("Not found turbo value %s", value)
            return False

    def set_fixation_v(self, fixation_text: str) -> dict[str, Any] | bool:
        """Set vertical fixation."""
        with self.operation_lock:
            self.get_ac_states()
            fixation = ACStatic.FIXATION.VERTICAL.__dict__.get(fixation_text.upper())
            if fixation is not None:
                self.status["fixation_v"] = fixation
                return self._send_status_and_refresh()
            self.logger.debug("Not found vertical fixation value %s", fixation_text)
            return False

    def set_fixation_h(self, fixation_text: str) -> dict[str, Any] | bool:
        """Set horizontal fixation."""
        with self.operation_lock:
            self.get_ac_states()
            fixation = ACStatic.FIXATION.HORIZONTAL.__dict__.get(fixation_text.upper())
            if fixation is not None:
                self.status["fixation_h"] = fixation
                return self._send_status_and_refresh()
            self.logger.debug("Not found horizontal fixation value %s", fixation_text)
            return False

    def set_display(self, value: str) -> dict[str, Any] | bool:
        """Set display board power."""
        with self.operation_lock:
            self.get_ac_states()
            mode = ACStatic.ONOFF.__dict__.get(value)
            if mode is not None:
                self.status["display"] = (
                    ACStatic.ONOFF.OFF if mode else ACStatic.ONOFF.ON
                )
                return self._send_status_and_refresh()
            self.logger.debug("Not found display value %s", value)
            return False

    def set_mildew(self, value: str) -> dict[str, Any] | bool:
        """Set mildew mode."""
        return self._set_onoff_status("mildew", value)

    def set_clean(self, value: str) -> dict[str, Any] | bool:
        """Set clean mode."""
        return self._set_onoff_status("clean", value)

    def set_health(self, value: str) -> dict[str, Any] | bool:
        """Set health mode."""
        return self._set_onoff_status("health", value)

    def set_sleep(self, value: str) -> dict[str, Any] | bool:
        """Set sleep mode."""
        return self._set_onoff_status("sleep", value)

    def _set_onoff_status(self, key: str, value: str) -> dict[str, Any] | bool:
        """Set a raw on/off status value."""
        with self.operation_lock:
            self.get_ac_states()
            mode = ACStatic.ONOFF.__dict__.get(value)
            if mode is not None:
                self.status[key] = mode
                return self._send_status_and_refresh()
            self.logger.debug("Not found %s value %s", key, value)
            return False

    def set_homekit_mode(self, status: str) -> dict[str, Any] | bool:
        """Set mode from a HomeKit-style mode string."""
        with self.operation_lock:
            status = str(status)

            if status.lower() == "coolon":
                mode = ACStatic.MODE.COOLING
            elif status.lower() == "heaton":
                mode = ACStatic.MODE.HEATING
            elif status.lower() == "auto":
                mode = ACStatic.MODE.AUTO
            elif status.lower() == "dry":
                mode = ACStatic.MODE.DRY
            elif status.lower() == "fan_only":
                mode = ACStatic.MODE.FAN
            elif status.lower() == "off":
                self.status["power"] = ACStatic.ONOFF.OFF
                return self._send_status_and_refresh()
            else:
                self.logger.debug("Invalid status for homekit %s", status)
                return False

            self.status["mode"] = mode
            self.status["power"] = ACStatic.ONOFF.ON
            return self._send_status_and_refresh()

    def set_homeassistant_mode(self, status: str) -> dict[str, Any] | bool:
        """Set mode from a Home Assistant HVAC mode string."""
        with self.operation_lock:
            status = str(status)

            if status.lower() == "cool":
                mode = ACStatic.MODE.COOLING
            elif status.lower() == "heat":
                mode = ACStatic.MODE.HEATING
            elif status.lower() == "auto":
                mode = ACStatic.MODE.AUTO
            elif status.lower() == "dry":
                mode = ACStatic.MODE.DRY
            elif status.lower() == "fan_only":
                mode = ACStatic.MODE.FAN
            elif status.lower() == "off":
                self.status["power"] = ACStatic.ONOFF.OFF
                return self._send_status_and_refresh()
            else:
                self.logger.debug("Invalid status for homeassistant %s", status)
                return False

            self.status["mode"] = mode
            self.status["power"] = ACStatic.ONOFF.ON
            return self._send_status_and_refresh()

    def _send_status_and_refresh(self) -> dict[str, Any] | int | bool:
        """Send the current raw status and read back the device state."""
        self.set_ac_status()
        self.status["lastupdate"] = 0
        status = self.get_ac_states(force_update=True)
        if not isinstance(status, dict):
            raise BroadlinkACConnectionError(
                "Set status succeeded but refreshing state failed"
            )
        return status

    def get_ac_info(self) -> dict[str, Any] | int:
        """Get AC device info and ambient temperature."""
        response = self.send_packet(COMMAND_AC, GET_AC_INFO)
        err = response[0x22] | (response[0x23] << 8)
        if err != 0:
            self.logger.debug("Invalid packet received Errorcode %s", err)
            self.logger.debug(
                "Failed Raw Response: %s",
                " ".join(format(x, "08b") for x in response),
            )
            return 0

        response_payload = bytearray(self.decrypt(bytes(response[0x38:])))
        self.logger.debug(
            "Acinfo Raw Response: %s",
            " ".join(format(x, "08b") for x in response_payload),
        )
        self.logger.debug(
            "Acinfo Raw Hex: %s",
            " ".join(format(x, "02x") for x in response_payload),
        )

        response_payload = response_payload[2:]
        self.logger.debug(
            "AcInfo: %s", " ".join(format(x, "08b") for x in response_payload[9:])
        )

        if len(response_payload) < 40:
            self.logger.debug("AcInfo: Invalid, seems too short")
            return 0

        ambient_temp = response_payload[15] & 0b00011111
        self.logger.debug(
            "Ambient Temp Decimal: %s", float(response_payload[31] & 0b00011111)
        )

        if ambient_temp:
            self.status["ambient_temp"] = ambient_temp

        return make_nice_status(self.status)

    def get_ac_states(self, force_update: bool = False) -> dict[str, Any] | int | bool:
        """Get current AC states and parse them into raw status."""
        self.logger.debug("Last update was: %s", self.status["lastupdate"])
        if (
            force_update is False
            and (self.status["lastupdate"] + self.update_interval) > time.time()
        ):
            return make_nice_status(self.status)

        response = self.send_packet(COMMAND_AC, GET_STATES)
        err = response[0x22] | (response[0x23] << 8)
        if err != 0:
            return 0

        response_payload = bytearray(self.decrypt(bytes(response[0x38:])))
        if response_payload[4] != PACKET_TYPE_RESULT:
            return False

        if response_payload[0] != STATE_PACKET_LENGTH:
            return False

        self.logger.debug(
            "Raw AC Status: %s",
            " ".join(format(x, "08b") for x in response_payload[9:]),
        )

        response_payload = response_payload[2:]
        self.logger.debug(
            "Raw AC Status: %s", " ".join(format(x, "02x") for x in response_payload)
        )

        self.status["temp"] = (
            8 + (response_payload[10] >> 3) + (0.5 * float(response_payload[12] >> 7))
        )
        self.status["power"] = response_payload[18] >> 5 & 0b00000001
        self.status["fixation_v"] = response_payload[10] & 0b00000111
        self.status["mode"] = response_payload[15] >> 5 & 0b00001111
        self.status["sleep"] = response_payload[15] >> 2 & 0b00000001
        self.status["display"] = response_payload[20] >> 4 & 0b00000001
        self.status["mildew"] = response_payload[20] >> 3 & 0b00000001
        self.status["health"] = response_payload[18] >> 1 & 0b00000001
        self.status["fixation_h"] = response_payload[11] >> 5 & 0b00000111
        self.status["fanspeed"] = response_payload[13] >> 5 & 0b00000111
        self.status["ifeel"] = response_payload[15] >> 3 & 0b00000001
        self.status["mute"] = response_payload[14] >> 7 & 0b00000001
        self.status["turbo"] = response_payload[14] >> 6 & 0b00000001
        self.status["clean"] = response_payload[18] >> 2 & 0b00000001
        self.status["lastupdate"] = time.time()

        return make_nice_status(self.status)

    def set_ac_status(self) -> dict[str, Any] | str | bool:
        """Send the complete AC status payload."""
        self.logger.debug("Start set_ac_status")

        temperature, temperature_05, clamped_temperature = encode_temperature(
            self.status["temp"]
        )
        self.status["temp"] = clamped_temperature

        payload = bytearray(23)
        payload[0] = 0xBB
        payload[1] = 0x00
        payload[2] = 0x06
        payload[3] = 0x80
        payload[4] = 0x00
        payload[5] = 0x00
        payload[6] = 0x0F
        payload[7] = 0x00
        payload[8] = 0x01
        payload[9] = 0x01
        payload[10] = 0b00000000 | temperature << 3 | self.status["fixation_v"]
        payload[11] = 0b00000000 | self.status["fixation_h"] << 5
        payload[12] = 0b00001111 | temperature_05 << 7
        payload[13] = 0b00000000 | self.status["fanspeed"] << 5
        payload[14] = 0b00000000 | self.status["turbo"] << 6 | self.status["mute"] << 7
        payload[15] = (
            0b00000000 | self.status["mode"] << 5 | self.status["sleep"] << 2
        )
        payload[16] = 0b00000000
        payload[17] = 0x00
        payload[18] = (
            0b00000000
            | self.status["power"] << 5
            | self.status["health"] << 1
            | self.status["clean"] << 2
        )
        payload[19] = 0x00
        payload[20] = (
            0b00000000 | self.status["display"] << 4 | self.status["mildew"] << 3
        )
        payload[21] = 0b00000000
        payload[22] = 0b00000000

        self.logger.debug("Payload:%s", "".join(format(x, "02x") for x in payload))

        request_payload = bytearray(32)
        request_payload[0] = len(payload) + 2
        request_payload[2 : len(payload) + 2] = payload

        crc = checksum(payload)
        self.logger.debug("Checksum:%s", format(crc, "02x"))
        request_payload[len(payload) + 2] = (crc >> 8) & 0xFF
        request_payload[len(payload) + 3] = crc & 0xFF

        self.logger.debug(
            "Packet:%s", "".join(format(x, "02x") for x in request_payload)
        )

        response = self.send_packet(COMMAND_AC, request_payload)
        self.logger.debug("Response:%s", "".join(format(x, "02x") for x in response))

        err = response[0x22] | (response[0x23] << 8)
        if err == 0:
            response_payload = bytearray(self.decrypt(bytes(response[0x38:])))
            self.logger.debug(
                "Set status response payload: %s",
                " ".join(format(x, "02x") for x in response_payload),
            )
            if response_payload[4] in (PACKET_TYPE_RESULT, PACKET_TYPE_SET_ACK):
                return self.status
            raise BroadlinkACConnectionError(
                f"Unexpected set status response packet type: {response_payload[4]:02x}"
            )

        raise BroadlinkACConnectionError(f"Set status failed with error code {err}")
