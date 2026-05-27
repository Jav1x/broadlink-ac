"""Exceptions for the Broadlink AC integration."""

from __future__ import annotations


class BroadlinkACError(Exception):
    """Base error for Broadlink AC communication."""


class BroadlinkACConnectionError(BroadlinkACError):
    """Broadlink AC connection error."""


class BroadlinkACTimeoutError(BroadlinkACConnectionError):
    """Broadlink AC connection timeout."""
