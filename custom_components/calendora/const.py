"""Constants for the Calendora integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Final

DOMAIN: Final = "calendora"

LOGGER: Final = logging.getLogger(__package__)

# `docs/API-SURFACE.md` §1: hardcoded on purpose. There is no issuer field on a
# key and no discovery endpoint, so a config field for this would be a form
# every user skips past in service of a deployment model that does not exist.
# If self-hosting becomes real it arrives as a documented field first.
API_BASE_URL: Final = "https://calendora.app"

CONF_API_KEY: Final = "api_key"

# The stream is the update path; this is only the safety net for a stream that
# died without telling us. Deliberately slow — a push integration that polls
# every minute is a polling integration with extra steps.
FALLBACK_POLL_INTERVAL: Final = timedelta(minutes=30)

# How much calendar to keep loaded. `docs/API-SURFACE.md` §4 rejects a range
# longer than 400 days outright rather than truncating it, so this must stay
# comfortably inside that — and the check in `api.py` enforces it rather than
# trusting whoever edits these next.
EVENT_WINDOW_PAST: Final = timedelta(days=30)
EVENT_WINDOW_FUTURE: Final = timedelta(days=365)
MAX_EVENT_RANGE_DAYS: Final = 400
