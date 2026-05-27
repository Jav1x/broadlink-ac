"""Fixtures for Broadlink AC tests."""

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.broadlink_ac.const import DOMAIN


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom integrations in tests."""
    yield


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Mock setting up a config entry."""
    with patch(
        "custom_components.broadlink_ac.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        yield mock_setup_entry
