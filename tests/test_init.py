"""Tests for setting up and tearing down a Calendora config entry."""

from __future__ import annotations

import aiohttp
import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.calendora.api import feed_identity
from custom_components.calendora.const import CONF_FEED_URL, DOMAIN

from .const import FEED_TOKEN, FEED_URL, ICS, ICS_HEADERS


def _entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="example.invalid",
        data={CONF_FEED_URL: FEED_URL},
        unique_id=feed_identity(FEED_URL),
    )


async def test_setup_and_unload(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """An entry loads, exposes its coordinator, and unloads cleanly."""
    aioclient_mock.get(FEED_URL, text=ICS, headers=ICS_HEADERS)

    entry = _entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.data.raw_ics.startswith("BEGIN:VCALENDAR")

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


@pytest.mark.parametrize(
    ("kwargs", "expected_message"),
    [
        ({"status": 404}, "Reconfigure"),
        ({"status": 500}, "keep trying"),
        ({"exc": aiohttp.ClientConnectionError("boom")}, "keep trying"),
    ],
    ids=["rejected-token", "server-error", "unreachable"],
)
async def test_setup_failure_says_which_failure_it_is(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    kwargs: dict,
    expected_message: str,
) -> None:
    """"Unavailable" alone is a support thread; naming the cause is a fix.

    A rejected token is the one a user can act on, and the message has to say so
    — that is the difference between "open Reconfigure" and "open an issue".
    """
    aioclient_mock.get(FEED_URL, **kwargs)

    entry = _entry()
    entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert expected_message in (entry.reason or "")


async def test_setup_failure_never_logs_the_token(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The failure path a user is most likely to screenshot must be clean."""
    aioclient_mock.get(FEED_URL, status=404)

    entry = _entry()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert FEED_TOKEN not in caplog.text
    assert FEED_TOKEN not in (entry.reason or "")


async def test_calendar_platform_loads_with_no_entities(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Phase 0 ships the platform wired up and empty.

    Asserting the emptiness keeps the scaffold honest: when Phase 1 adds real
    calendars this test fails and has to be rewritten deliberately, rather than
    an accidental entity appearing unnoticed.
    """
    aioclient_mock.get(FEED_URL, text=ICS, headers=ICS_HEADERS)

    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.async_entity_ids("calendar") == []
