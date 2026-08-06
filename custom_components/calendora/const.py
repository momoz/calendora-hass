"""Constants for the Calendora integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Final

DOMAIN: Final = "calendora"

LOGGER: Final = logging.getLogger(__package__)

# Config-entry data. The feed URL contains a capability token — possession is
# authorisation — so it is a secret: never log it, never surface it in
# diagnostics, never put it in an issue template.
CONF_FEED_URL: Final = "feed_url"

# Options.
CONF_SCAN_INTERVAL_MINUTES: Final = "scan_interval_minutes"

# Polling is correct here and nowhere else: /api/feeds/{token} is a static ICS
# document with nothing to push with. From Phase 2 the coordinator moves to the
# SSE stream and this constant goes away with the feed path.
DEFAULT_SCAN_INTERVAL: Final = timedelta(minutes=15)
MIN_SCAN_INTERVAL_MINUTES: Final = 5
MAX_SCAN_INTERVAL_MINUTES: Final = 240
