"""Tests for Broadlink AC protocol helpers."""

from __future__ import annotations

from custom_components.broadlink_ac.models import (
    ACStatic,
    checksum,
    default_status,
    encode_temperature,
    make_nice_status,
)


def test_encode_temperature_clamps_low_value() -> None:
    """Test low temperature values are clamped to protocol minimum."""
    encoded, half_degree, clamped = encode_temperature(12)

    assert encoded == 8
    assert half_degree == 0
    assert clamped == 16.0


def test_encode_temperature_clamps_high_value() -> None:
    """Test high temperature values are clamped to protocol maximum."""
    encoded, half_degree, clamped = encode_temperature(40)

    assert encoded == 24
    assert half_degree == 0
    assert clamped == 32.0


def test_encode_temperature_half_degree() -> None:
    """Test half-degree temperatures set the protocol half-degree flag."""
    encoded, half_degree, clamped = encode_temperature(22.5)

    assert encoded == 14
    assert half_degree == 1
    assert clamped == 22.5


def test_checksum_matches_known_status_payload() -> None:
    """Test checksum calculation for a representative AC status payload."""
    payload = bytearray(
        [
            0xBB,
            0x00,
            0x06,
            0x80,
            0x00,
            0x00,
            0x0F,
            0x00,
            0x01,
            0x01,
            0x47,
            0xE0,
            0x0F,
            0xA0,
            0x00,
            0x00,
            0x00,
            0x00,
            0x20,
            0x00,
            0x10,
            0x00,
            0x00,
        ]
    )

    assert checksum(payload) == 0xA6FD


def test_set_status_request_places_crc_after_payload() -> None:
    """Test set-status request framing keeps the full payload before CRC."""
    payload = bytearray(
        [
            0xBB,
            0x00,
            0x06,
            0x80,
            0x00,
            0x00,
            0x0F,
            0x00,
            0x01,
            0x01,
            0x47,
            0xE0,
            0x0F,
            0xA0,
            0x00,
            0x00,
            0x00,
            0x00,
            0x20,
            0x00,
            0x10,
            0x00,
            0x00,
        ]
    )
    request_payload = bytearray(32)
    request_payload[0] = len(payload) + 2
    request_payload[2 : len(payload) + 2] = payload
    crc = checksum(payload)
    request_payload[len(payload) + 2] = (crc >> 8) & 0xFF
    request_payload[len(payload) + 3] = crc & 0xFF

    assert request_payload[2 : len(payload) + 2] == payload
    assert request_payload[len(payload) + 2 : len(payload) + 4] == bytearray(
        [0xA6, 0xFD]
    )


def test_make_nice_status_inverts_display_protocol_bit() -> None:
    """Test the display board protocol bit is exposed as normal on/off."""
    status = default_status()
    status["display"] = ACStatic.ONOFF.OFF

    assert make_nice_status(status)["display"] == "ON"

    status["display"] = ACStatic.ONOFF.ON

    assert make_nice_status(status)["display"] == "OFF"


def test_make_nice_status_preserves_homeassistant_mode_keys() -> None:
    """Test the Home Assistant-facing status keys remain available."""
    status = default_status()
    nice_status = make_nice_status(status)

    assert nice_status["mode_homeassistant"] == "auto"
    assert nice_status["fanspeed_homeassistant"] == "Auto"
    assert nice_status["fixation_v"] == "AUTO"
