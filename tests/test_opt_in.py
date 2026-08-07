"""Per-member opt-in must be readable by the thing that sends.

An opt-in the sender cannot check is not an opt-in — it is a switch that lies,
on the most location-sensitive feature in the integration. These tests assert
the consent is visible on the entities a blueprint can actually reach.
"""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.calendora.const import (
    API_BASE_URL,
    CONF_API_KEY,
    CONF_SHOP_MEMBERS,
    DOMAIN,
)

from .const import API_KEY, load_fixture

ALEX_CALENDAR = "calendar.test_household_alex"
ALEX_SENSOR = "sensor.test_household_alex_next_event"
ALEX_CLASH = "binary_sensor.test_household_alex_has_a_clash_today"
ROBIN_CALENDAR = "calendar.test_household_robin"


async def _setup(hass, aioclient_mock, opted_in: list[str] | None = None):
    aioclient_mock.get(f"{API_BASE_URL}/api/v1/household", json=load_fixture("household.json"))
    aioclient_mock.get(f"{API_BASE_URL}/api/v1/members", json=load_fixture("members.json"))
    aioclient_mock.get(f"{API_BASE_URL}/api/v1/events", json=load_fixture("events.json"))
    aioclient_mock.get(f"{API_BASE_URL}/api/v1/lists", json={"lists": []})
    aioclient_mock.get(f"{API_BASE_URL}/api/v1/stream", text="",
                       headers={"Content-Type": "text/event-stream"})
    entry = MockConfigEntry(
        domain=DOMAIN, title="Calendora", data={CONF_API_KEY: API_KEY}, version=2,
        options={CONF_SHOP_MEMBERS: opted_in} if opted_in is not None else {},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.mark.parametrize("entity_id", [ALEX_CALENDAR, ALEX_SENSOR, ALEX_CLASH])
async def test_every_member_entity_carries_the_opt_in(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, entity_id: str
) -> None:
    """A blueprint may point at any of them, so all three must answer."""
    await _setup(hass, aioclient_mock, opted_in=["mem-1"])

    attributes = hass.states.get(entity_id).attributes
    assert attributes["member_id"] == "mem-1"
    assert attributes["shop_notifications"] is True


async def test_nobody_is_opted_in_by_default(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Silence is not consent. An unconfigured integration sends to nobody."""
    await _setup(hass, aioclient_mock)

    assert hass.states.get(ALEX_CALENDAR).attributes["shop_notifications"] is False


async def test_opting_one_person_in_does_not_opt_in_the_others(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Per member, not per household — the whole reason it is in the options flow."""
    await _setup(hass, aioclient_mock, opted_in=["mem-1"])

    assert hass.states.get(ALEX_CALENDAR).attributes["shop_notifications"] is True
    assert hass.states.get(ROBIN_CALENDAR).attributes["shop_notifications"] is False


async def test_the_member_id_is_readable_without_anyone_typing_it(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The blueprint picks an entity; the id comes from the entity.

    A pasted uuid is a typo that fails silently, and the failure here would be
    sending somebody's location-triggered shopping list to a person who never
    agreed to it.
    """
    await _setup(hass, aioclient_mock, opted_in=["mem-2"])

    assert hass.states.get(ROBIN_CALENDAR).attributes["member_id"] == "mem-2"
    assert hass.states.get(ROBIN_CALENDAR).attributes["shop_notifications"] is True
    assert hass.states.get(ALEX_CALENDAR).attributes["shop_notifications"] is False


async def test_a_clash_sensor_keeps_its_own_attributes_too(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Adding the opt-in must not displace what the entity already reported."""
    await _setup(hass, aioclient_mock, opted_in=["mem-1"])

    attributes = hass.states.get(ALEX_SENSOR).attributes
    assert "shop_notifications" in attributes
    assert "summary" in attributes or attributes.get("member_id") == "mem-1"
