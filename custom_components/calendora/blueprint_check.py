"""Notice when the shopping blueprint was never installed.

**This is the finding that cost three releases, turned into a control.**

A HACS integration that ships a blueprint does not register it. The files land
in `custom_components/`, and the blueprint sits in the repository where nothing
reads it — Home Assistant only knows about a blueprint once a person pastes its
URL into Settings → Automations → Blueprints → Import blueprint. Nothing in this
repository said so, and nothing anywhere checked.

The consequence, confirmed on a real household on 2026-08-10: the blueprint had
never been imported, so the automation it builds had never existed, so the two
bugs that made it unloadable could not have been noticed by anybody. **There was
no step at which somebody would have found out.** Not a missed test — a missing
installation.

`30` §6b: a labelled absence beats a control that appears to work. So this does
not try to install anything, and it cannot — an integration may not write a
blueprint into a user's config directory on their behalf, and pretending
otherwise would replace one silent failure with a louder one. It states the
absence, once, with the URL to paste.
"""

from __future__ import annotations

from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN

BLUEPRINT_PATH = "blueprints/automation/calendora/shopping_list_on_arrival.yaml"
ISSUE_ID = "shopping_blueprint_not_imported"

IMPORT_URL = (
    "https://github.com/momoz/calendora-hass/blob/main/"
    "blueprints/automation/calendora/shopping_list_on_arrival.yaml"
)


async def async_check_blueprint_is_imported(hass: HomeAssistant) -> bool:
    """Raise a repair when the shopping blueprint is not installed.

    Returns whether it is present, so a caller — and a test — can tell the two
    outcomes apart rather than inferring them from the issue registry.

    The check is a file test rather than a read of the blueprint registry
    because it must be true of a household that has never opened the blueprints
    page, which is exactly the household this exists for.
    """
    path = Path(hass.config.path(BLUEPRINT_PATH))
    present = await hass.async_add_executor_job(path.is_file)

    if present:
        ir.async_delete_issue(hass, DOMAIN, ISSUE_ID)
        return True

    ir.async_create_issue(
        hass,
        DOMAIN,
        ISSUE_ID,
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_ID,
        translation_placeholders={"url": IMPORT_URL},
        learn_more_url=IMPORT_URL,
    )
    return False
