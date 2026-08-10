"""The control for the failure nobody could have noticed.

Three releases shipped a blueprint that had never been imported into any
household. Not a missed test — a **missing installation**: a HACS integration
does not register its own blueprint, nothing in this repository said so, and
nothing checked. So the blueprint was neither read nor run, anywhere, and the
two bugs in it were unreachable by any process that existed.

These tests hold the control in place. The one that matters is the second: a
check that cannot tell present from absent is worse than no check, because it
reports a clean bill either way.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from custom_components.calendora.blueprint_check import (
    BLUEPRINT_PATH,
    ISSUE_ID,
    async_check_blueprint_is_imported,
)
from custom_components.calendora.const import DOMAIN

REPO_BLUEPRINT = Path(__file__).resolve().parents[1] / BLUEPRINT_PATH


def _install(hass: HomeAssistant) -> Path:
    """Put the blueprint where an import would have put it."""
    target = Path(hass.config.path(BLUEPRINT_PATH))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(REPO_BLUEPRINT.read_text(encoding="utf-8"), encoding="utf-8")
    return target


async def test_a_household_without_the_blueprint_is_told(hass: HomeAssistant) -> None:
    """The state Mike's house was in for three releases, with nothing saying so."""
    assert await async_check_blueprint_is_imported(hass) is False

    issue = ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_ID)
    assert issue is not None, (
        "the blueprint is absent and nothing was raised — this is the exact "
        "silence that let three releases ship an unloadable blueprint"
    )
    assert issue.severity is ir.IssueSeverity.WARNING
    assert not issue.is_fixable, (
        "an integration cannot import a blueprint on a user's behalf; offering "
        "a fix button that cannot fix it is worse than stating the absence"
    )
    assert "github.com" in (issue.translation_placeholders or {}).get("url", ""), (
        "the notice must carry the address a user pastes, or it names a problem "
        "and withholds the one thing needed to act on it"
    )


async def test_a_household_with_the_blueprint_is_left_alone(
    hass: HomeAssistant,
) -> None:
    """The half that stops this being a control that always fires.

    A check that reports the same thing in both states is not a check. This is
    the assertion that would fail if the file test were wrong — a bad path, a
    typo in the filename — which would otherwise present as a permanent warning
    that every user learns to dismiss.
    """
    _install(hass)
    assert await async_check_blueprint_is_imported(hass) is True
    assert ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_ID) is None


async def test_importing_it_later_clears_the_notice(hass: HomeAssistant) -> None:
    """Reloading after an import must take the warning away.

    Otherwise the fix leaves the complaint on screen, and the next person
    concludes the check is broken and stops believing it.
    """
    assert await async_check_blueprint_is_imported(hass) is False
    assert ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_ID) is not None

    _install(hass)
    assert await async_check_blueprint_is_imported(hass) is True
    assert ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_ID) is None


def test_the_path_it_checks_is_the_path_the_repo_ships() -> None:
    """The two ends of this only line up by agreement, so assert the agreement.

    `BLUEPRINT_PATH` is where Home Assistant puts an imported blueprint, derived
    from the blueprint's own location in this repository. Move the file and the
    check silently starts testing for something that was never there, and warns
    every household forever.
    """
    assert REPO_BLUEPRINT.is_file(), (
        f"{BLUEPRINT_PATH} is not in this repository — the check is looking for "
        f"a file this integration no longer ships"
    )


def test_the_import_url_points_at_the_blueprint_this_repo_ships() -> None:
    """A URL in a user-facing notice is a promise, and it is easy to get wrong."""
    from custom_components.calendora.blueprint_check import IMPORT_URL

    assert IMPORT_URL.endswith("blueprints/automation/calendora/shopping_list_on_arrival.yaml")
    assert "momoz/calendora-hass" in IMPORT_URL


async def test_the_notice_survives_a_household_that_has_never_opened_blueprints(
    hass: HomeAssistant,
) -> None:
    """No blueprints directory at all, which is the untouched-install case.

    The check must not depend on Home Assistant having created that folder,
    because the household this exists for is precisely the one that has never
    been to that page.
    """
    blueprints = Path(hass.config.path("blueprints"))
    assert not (blueprints / "automation" / "calendora").exists()
    assert await async_check_blueprint_is_imported(hass) is False
