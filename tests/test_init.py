"""Tests for setting up, streaming and tearing down a Calendora config entry."""

from __future__ import annotations

import aiohttp
import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.calendora.const import API_BASE_URL, CONF_API_KEY, DOMAIN

from .const import API_KEY

HOUSEHOLD_URL = f"{API_BASE_URL}/api/v1/household"
MEMBERS_URL = f"{API_BASE_URL}/api/v1/members"
EVENTS_URL = f"{API_BASE_URL}/api/v1/events"
LISTS_URL = f"{API_BASE_URL}/api/v1/lists"
STREAM_URL = f"{API_BASE_URL}/api/v1/stream"

SSE_HEADERS = {"Content-Type": "text/event-stream"}


def _entry(**kwargs) -> MockConfigEntry:
    kwargs.setdefault("data", {CONF_API_KEY: API_KEY})
    kwargs.setdefault("version", 2)
    return MockConfigEntry(domain=DOMAIN, title="Calendora", **kwargs)


def _mock_ok(aioclient_mock: AiohttpClientMocker, stream: str = "") -> None:
    aioclient_mock.get(
        HOUSEHOLD_URL,
        json={
            "household": {"id": "hh-test-0001", "name": "Test Household"},
            "timezone": {"value": "UTC", "source": "key-owner"},
        },
    )
    aioclient_mock.get(MEMBERS_URL, json={"members": []})
    aioclient_mock.get(LISTS_URL, json={"lists": []})
    aioclient_mock.get(
        EVENTS_URL, json={"occurrences": [{"id": "e1:o1", "eventId": "e1"}]}
    )
    aioclient_mock.get(LISTS_URL, json={"lists": []})
    aioclient_mock.get(STREAM_URL, text=stream, headers=SSE_HEADERS)


async def test_setup_and_unload(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """An entry loads, exposes its coordinator, and unloads cleanly."""
    _mock_ok(aioclient_mock)
    entry = _entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.data.household_id == "hh-test-0001"
    assert entry.runtime_data.data.key_owner_timezone == "UTC"
    assert entry.runtime_data.data.occurrences == [{"id": "e1:o1", "eventId": "e1"}]

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_events_are_requested_as_days_within_the_documented_range(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """§4: `from`/`to` are YYYY-MM-DD, and over 400 days is rejected outright."""
    _mock_ok(aioclient_mock)
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    events_call = next(
        call for call in aioclient_mock.mock_calls if "events" in str(call[1])
    )
    query = events_call[1].query
    assert "T" not in query["from"] and "T" not in query["to"]

    from datetime import date

    span = (date.fromisoformat(query["to"]) - date.fromisoformat(query["from"])).days
    assert 0 < span <= 400


async def test_revoked_key_starts_reauth_and_does_not_retry(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """§3: a 401 raises ConfigEntryAuthFailed. Never retry, never fail silently."""
    aioclient_mock.get(
        HOUSEHOLD_URL, status=401, json={"error": "no", "code": "unauthenticated"}
    )
    aioclient_mock.get(MEMBERS_URL, status=401, json={"error": "no", "code": "unauthenticated"})
    aioclient_mock.get(LISTS_URL, status=401, json={"error": "no", "code": "unauthenticated"})
    aioclient_mock.get(EVENTS_URL, status=401, json={"error": "no", "code": "unauthenticated"})
    aioclient_mock.get(STREAM_URL, status=401, json={"error": "no", "code": "unauthenticated"})

    entry = _entry()
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # SETUP_ERROR, not SETUP_RETRY: retrying a 401 is prohibited.
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert any(
        flow["context"]["source"] == "reauth"
        for flow in hass.config_entries.flow.async_progress()
    )
    aioclient_mock.get(LISTS_URL, json={"lists": []})


async def test_missing_scope_retries_rather_than_asking_for_a_new_key(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """403 is not an auth failure — the key is fine and reauth would loop."""
    aioclient_mock.get(
        HOUSEHOLD_URL,
        status=403,
        json={"error": "missing scope: calendar:read", "code": "forbidden"},
    )
    aioclient_mock.get(MEMBERS_URL, status=403, json={"error": "missing scope: calendar:read", "code": "forbidden"})
    aioclient_mock.get(LISTS_URL, status=403, json={"error": "missing scope: calendar:read", "code": "forbidden"})
    aioclient_mock.get(EVENTS_URL, status=403, json={"error": "missing scope: calendar:read", "code": "forbidden"})
    aioclient_mock.get(STREAM_URL, status=403, json={"error": "nope", "code": "forbidden"})

    entry = _entry()
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert "calendar:read" in (entry.reason or "")
    assert not [
        flow
        for flow in hass.config_entries.flow.async_progress()
        if flow["context"]["source"] == "reauth"
    ]


async def test_stream_changed_event_triggers_a_refresh(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The whole point of push: `changed` means re-read."""
    _mock_ok(aioclient_mock, stream="event: ready\ndata: {}\n\nevent: changed\ndata: {}\n\n")

    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # One refresh from setup, at least one more provoked by `changed`.
    household_calls = [c for c in aioclient_mock.mock_calls if "household" in str(c[1])]
    assert len(household_calls) >= 2


async def test_stream_task_is_cancelled_on_unload(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A background task that outlives its entry is the classic leak."""
    _mock_ok(aioclient_mock)
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry._background_tasks, "the stream task should be owned by the entry"

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    # Home Assistant cancels and awaits tasks it owns. An empty set here is the
    # difference between a clean unload and a task still talking to a
    # torn-down coordinator.
    assert not entry._background_tasks


async def test_migration_from_the_feed_entry_drops_the_url(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A 0.0.1 entry held a feed URL, which is now a prohibited surface.

    There is nothing to migrate *to* — a feed token is not an API key — so the
    URL is discarded and the user is asked for a key. Leaving it in storage
    would keep a live credential for a surface we may not touch.
    """
    entry = _entry(
        version=1, data={"feed_url": "https://calendora.app/api/feeds/old-token"}
    )
    aioclient_mock.get(LISTS_URL, json={"lists": []})
    entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.version == 2
    assert "feed_url" not in entry.data
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert any(
        flow["context"]["source"] == "reauth"
        for flow in hass.config_entries.flow.async_progress()
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"status": 401, "json": {"error": "no", "code": "unauthenticated"}},
        {"status": 403, "json": {"error": "no", "code": "forbidden"}},
        {"status": 500, "json": {"error": "no", "code": "server_error"}},
        {"exc": aiohttp.ClientConnectionError("boom")},
    ],
    ids=["revoked", "wrong-scope", "server-error", "unreachable"],
)
async def test_setup_failure_never_logs_the_key(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    caplog: pytest.LogCaptureFixture,
    kwargs: dict,
) -> None:
    """The failure paths a user is most likely to screenshot must be clean."""
    aioclient_mock.get(HOUSEHOLD_URL, **kwargs)
    aioclient_mock.get(MEMBERS_URL, **kwargs)
    aioclient_mock.get(LISTS_URL, **kwargs)
    aioclient_mock.get(EVENTS_URL, **kwargs)
    aioclient_mock.get(STREAM_URL, **kwargs)

    entry = _entry()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert API_KEY not in caplog.text
    assert API_KEY not in (entry.reason or "")
