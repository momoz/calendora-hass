"""Config flow for Calendora."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    CalendoraConnectionError,
    CalendoraFeedClient,
    CalendoraInvalidFeedError,
    CalendoraResponseError,
    feed_host,
    feed_identity,
)
from .const import (
    CONF_FEED_URL,
    CONF_SCAN_INTERVAL_MINUTES,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LOGGER,
    MAX_SCAN_INTERVAL_MINUTES,
    MIN_SCAN_INTERVAL_MINUTES,
)

FEED_URL_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_FEED_URL): TextSelector(
            TextSelectorConfig(type=TextSelectorType.URL, autocomplete="url")
        )
    }
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SCAN_INTERVAL_MINUTES): NumberSelector(
            NumberSelectorConfig(
                min=MIN_SCAN_INTERVAL_MINUTES,
                max=MAX_SCAN_INTERVAL_MINUTES,
                step=5,
                unit_of_measurement="min",
                mode=NumberSelectorMode.BOX,
            )
        )
    }
)


class CalendoraConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Calendora."""

    VERSION = 1

    async def _async_feed_works(self, feed_url: str, errors: dict[str, str]) -> bool:
        """Fetch the feed once, translating any failure into a form error."""
        client = CalendoraFeedClient(async_get_clientsession(self.hass), feed_url)
        try:
            await client.async_fetch_ics()
        except CalendoraInvalidFeedError:
            errors["base"] = "invalid_feed"
        except CalendoraConnectionError:
            errors["base"] = "cannot_connect"
        except CalendoraResponseError:
            errors["base"] = "server_error"
        except Exception:  # noqa: BLE001 - the flow must never leak a traceback
            # Logged without the URL: the token is in it, and this line reaches
            # every log — and every bug report pasted out of one.
            LOGGER.exception("Unexpected error validating the Calendora feed")
            errors["base"] = "unknown"
        else:
            return True
        return False

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Take the calendar feed URL and prove it works before saving it."""
        errors: dict[str, str] = {}

        if user_input is not None:
            feed_url = user_input[CONF_FEED_URL].strip()

            # One entry per household. The unique id is a hash of the feed token,
            # never the token itself — see api.feed_identity for why, and for what
            # replaces it in Phase 2.
            await self.async_set_unique_id(feed_identity(feed_url))
            self._abort_if_unique_id_configured()

            if await self._async_feed_works(feed_url, errors):
                return self.async_create_entry(
                    title=feed_host(feed_url), data={CONF_FEED_URL: feed_url}
                )

        return self.async_show_form(
            step_id="user", data_schema=FEED_URL_SCHEMA, errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Point an existing entry at a new feed URL.

        This exists because the unique id is derived from the feed token, and
        rotating that token is the *security-conscious* thing for a user to do.
        Without this step the sequence is: regenerate the feed, watch every
        calendar go unavailable, add the integration again, and end up with a
        duplicate entry — because the hash changed, so nothing recognises the new
        URL as the same household. Punishing the careful user is not acceptable,
        and a reconfigure step is much smaller than the support thread it avoids.

        `_abort_if_unique_id_mismatch()` is deliberately *not* used: a changed
        unique id is the expected outcome here, not an error.
        """
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            feed_url = user_input[CONF_FEED_URL].strip()
            new_identity = feed_identity(feed_url)

            if any(
                other.entry_id != entry.entry_id and other.unique_id == new_identity
                for other in self.hass.config_entries.async_entries(DOMAIN)
            ):
                # The URL belongs to a household that is already set up. Silently
                # moving this entry onto it would leave two entries fighting over
                # the same feed.
                return self.async_abort(reason="already_configured")

            if await self._async_feed_works(feed_url, errors):
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=new_identity,
                    title=feed_host(feed_url),
                    data_updates={CONF_FEED_URL: feed_url},
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=FEED_URL_SCHEMA,
            errors=errors,
            description_placeholders={"host": feed_host(entry.data[CONF_FEED_URL])},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> CalendoraOptionsFlow:
        """Return the options flow."""
        return CalendoraOptionsFlow()


class CalendoraOptionsFlow(OptionsFlowWithReload):
    """Handle Calendora options.

    OptionsFlowWithReload reloads the entry on save, which is what makes a
    changed poll interval take effect without the user restarting anything.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_SCAN_INTERVAL_MINUTES: int(
                        user_input[CONF_SCAN_INTERVAL_MINUTES]
                    )
                }
            )

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA,
                {
                    CONF_SCAN_INTERVAL_MINUTES: self.config_entry.options.get(
                        CONF_SCAN_INTERVAL_MINUTES,
                        int(DEFAULT_SCAN_INTERVAL.total_seconds() // 60),
                    )
                },
            ),
        )
