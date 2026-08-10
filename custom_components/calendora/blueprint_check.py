"""Notice when the shopping blueprint was never imported.

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

**Why this asks Home Assistant instead of looking for a file.** The first
version tested for
`blueprints/automation/calendora/shopping_list_on_arrival.yaml`, reasoning from
this repository's own folder layout. That path is wrong, and it was wrong in the
worst available direction: **Home Assistant files an imported blueprint under
the GitHub OWNER**, so the real path is
`blueprints/automation/momoz/shopping_list_on_arrival.yaml`. The check could
therefore never pass — a household that had done exactly what the notice asked
was told to do it again, forever.

It shipped in 0.4.3 and 0.4.4 and was caught by reading a live instance rather
than by any test, because the test that covered the "already imported" case
installed the file **at the path the check was looking in**. The author supplied
the location as well as the value.

So identity now comes from the blueprint's own `source_url`, which points at
this repository and is written by whoever published it — not from a path, which
is Home Assistant's to choose and is not this integration's business to predict.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN, LOGGER

ISSUE_ID = "shopping_blueprint_not_imported"

#: Any blueprint whose `source_url` contains this came from this repository,
#: whatever folder Home Assistant chose to file it under.
SOURCE_MARKER = "momoz/calendora-hass"
BLUEPRINT_FILENAME = "shopping_list_on_arrival.yaml"

IMPORT_URL = (
    "https://github.com/momoz/calendora-hass/blob/main/"
    "blueprints/automation/calendora/shopping_list_on_arrival.yaml"
)


def _is_ours(path: str, blueprint: Any) -> bool:
    """Whether this is our shopping blueprint, however it was filed.

    `source_url` first, because it is what the blueprint says about itself. The
    filename is a fallback for a copy somebody saved by hand from a file rather
    than imported from a URL, which carries no source.
    """
    metadata = getattr(blueprint, "metadata", None) or {}
    source_url = metadata.get("source_url") or ""
    if SOURCE_MARKER in source_url:
        return True
    return path.endswith(BLUEPRINT_FILENAME)


async def async_check_blueprint_is_imported(hass: HomeAssistant) -> bool:
    """Raise a repair when the shopping blueprint is not installed.

    Returns whether it is present, so a caller — and a test — can tell the two
    outcomes apart rather than inferring them from the issue registry.
    """
    present = False
    try:
        from homeassistant.components.automation.helpers import async_get_blueprints

        blueprints = await async_get_blueprints(hass).async_get_blueprints()
        present = any(
            blueprint is not None and _is_ours(path, blueprint)
            for path, blueprint in blueprints.items()
        )
    except Exception:  # noqa: BLE001
        # Never let a missing notice become a broken integration. If the
        # blueprint machinery is unavailable — the `automation` integration not
        # loaded yet, an internal API moved — say nothing rather than claim an
        # absence that has not been established. A wrong notice is worse than no
        # notice: this check already shipped once telling households to import
        # something they had.
        LOGGER.debug("Could not check for the shopping blueprint", exc_info=True)
        return True

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
