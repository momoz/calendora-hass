"""Tests for the Calendora config, reconfigure and options flows."""

from __future__ import annotations

import aiohttp
import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.calendora.api import feed_identity
from custom_components.calendora.const import CONF_FEED_URL, DOMAIN

from .const import (
    FEED_TOKEN,
    FEED_URL,
    ICS,
    ICS_HEADERS,
    OTHER_FEED_TOKEN,
    OTHER_FEED_URL,
)


def _entry(url: str = FEED_URL) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="example.invalid",
        data={CONF_FEED_URL: url},
        unique_id=feed_identity(url),
    )


async def test_user_flow(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The happy path: paste a feed URL, get a loaded entry."""
    aioclient_mock.get(FEED_URL, text=ICS, headers=ICS_HEADERS)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_FEED_URL: FEED_URL}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "example.invalid"
    assert result["data"] == {CONF_FEED_URL: FEED_URL}

    entry = result["result"]
    assert entry.unique_id == feed_identity(FEED_URL)
    assert FEED_TOKEN not in entry.unique_id
    assert FEED_TOKEN not in entry.title

    await hass.async_block_till_done()
    assert entry.state is config_entries.ConfigEntryState.LOADED


async def test_user_flow_strips_whitespace(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A URL pasted out of a browser often arrives with a trailing space."""
    aioclient_mock.get(FEED_URL, text=ICS, headers=ICS_HEADERS)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_FEED_URL: f"  {FEED_URL}  "}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_FEED_URL] == FEED_URL


async def test_user_flow_aborts_on_duplicate(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """One entry per household."""
    aioclient_mock.get(FEED_URL, text=ICS, headers=ICS_HEADERS)
    _entry().add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_FEED_URL: FEED_URL}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"status": 404}, "invalid_feed"),
        ({"text": "<html/>", "headers": {"Content-Type": "text/html"}}, "invalid_feed"),
        ({"exc": aiohttp.ClientConnectionError("boom")}, "cannot_connect"),
        ({"status": 500}, "server_error"),
    ],
    ids=["rejected", "not-a-calendar", "unreachable", "server-error"],
)
async def test_user_flow_errors_recover(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    kwargs: dict,
    expected: str,
) -> None:
    """Every failure shows a form error, and the form still works afterwards."""
    aioclient_mock.get(FEED_URL, **kwargs)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_FEED_URL: FEED_URL}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected}

    aioclient_mock.clear_requests()
    aioclient_mock.get(FEED_URL, text=ICS, headers=ICS_HEADERS)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_FEED_URL: FEED_URL}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_unexpected_error_does_not_log_the_token(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The catch-all branch logs a traceback — it must not carry the secret."""
    aioclient_mock.get(FEED_URL, exc=ValueError("something odd"))

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_FEED_URL: FEED_URL}
    )

    assert result["errors"] == {"base": "unknown"}
    assert FEED_TOKEN not in caplog.text


async def test_reconfigure_accepts_a_rotated_token(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Rotating the feed token must not cost the user their entities.

    This is the whole reason the step exists: the unique id is derived from the
    token, so a rotation changes it. The existing entry has to follow the new
    URL — the alternative is a dead entry plus a duplicate.
    """
    aioclient_mock.get(FEED_URL, text=ICS, headers=ICS_HEADERS)
    aioclient_mock.get(OTHER_FEED_URL, text=ICS, headers=ICS_HEADERS)

    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert result["description_placeholders"] == {"host": "example.invalid"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_FEED_URL: OTHER_FEED_URL}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"

    assert entry.data[CONF_FEED_URL] == OTHER_FEED_URL
    assert entry.unique_id == feed_identity(OTHER_FEED_URL)
    assert OTHER_FEED_TOKEN not in entry.unique_id
    # The point of the whole exercise: still exactly one entry.
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    assert entry.state is config_entries.ConfigEntryState.LOADED


async def test_reconfigure_rejects_a_feed_already_configured(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Two entries must never end up pointing at the same household."""
    aioclient_mock.get(FEED_URL, text=ICS, headers=ICS_HEADERS)
    aioclient_mock.get(OTHER_FEED_URL, text=ICS, headers=ICS_HEADERS)

    entry = _entry()
    entry.add_to_hass(hass)
    other = _entry(OTHER_FEED_URL)
    other.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_FEED_URL: OTHER_FEED_URL}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_FEED_URL] == FEED_URL


async def test_reconfigure_keeps_the_old_url_on_a_bad_one(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A typo in the new URL must not strand a working entry."""
    aioclient_mock.get(FEED_URL, text=ICS, headers=ICS_HEADERS)
    aioclient_mock.get(OTHER_FEED_URL, status=404)

    entry = _entry()
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_FEED_URL: OTHER_FEED_URL}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_feed"}
    assert entry.data[CONF_FEED_URL] == FEED_URL
    assert entry.unique_id == feed_identity(FEED_URL)


async def test_options_flow_changes_the_poll_interval(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """OptionsFlowWithReload must actually reload, or the option does nothing."""
    aioclient_mock.get(FEED_URL, text=ICS, headers=ICS_HEADERS)

    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.update_interval.total_seconds() == 15 * 60

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"scan_interval_minutes": 30}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {"scan_interval_minutes": 30}
    assert entry.runtime_data.update_interval.total_seconds() == 30 * 60
