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
    ISSUE_ID,
    async_check_blueprint_is_imported,
)
from custom_components.calendora.const import DOMAIN

REPO_BLUEPRINT = (
    Path(__file__).resolve().parents[1]
    / "blueprints/automation/calendora/shopping_list_on_arrival.yaml"
)

#: Where Home Assistant ACTUALLY files it — under the GitHub owner, not under
#: this repository's own folder name. Verified against a live instance on
#: 2026-08-10, where the imported blueprint sits at
#: `momoz/shopping_list_on_arrival.yaml`. The first version of this check looked
#: under `calendora/` and so could never pass; the test that was meant to cover
#: the "already imported" case installed the file at the wrong path too, because
#: the same person wrote both.
IMPORTED_PATH = "blueprints/automation/momoz/shopping_list_on_arrival.yaml"


async def _install(hass: HomeAssistant, path: str = IMPORTED_PATH) -> Path:
    """Import the blueprint the way Home Assistant does."""
    target = Path(hass.config.path(path))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(REPO_BLUEPRINT.read_text(encoding="utf-8"), encoding="utf-8")
    await _reset_blueprint_cache(hass)
    return target


async def _reset_blueprint_cache(hass: HomeAssistant) -> None:
    """Home Assistant caches the blueprint listing; a test writing files must clear it."""
    from homeassistant.components.automation.helpers import async_get_blueprints

    await async_get_blueprints(hass).async_reset_cache()


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
    await _install(hass)
    assert await async_check_blueprint_is_imported(hass) is True
    assert ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_ID) is None


async def test_importing_it_later_clears_the_notice(hass: HomeAssistant) -> None:
    """Reloading after an import must take the warning away.

    Otherwise the fix leaves the complaint on screen, and the next person
    concludes the check is broken and stops believing it.
    """
    assert await async_check_blueprint_is_imported(hass) is False
    assert ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_ID) is not None

    await _install(hass)
    assert await async_check_blueprint_is_imported(hass) is True
    assert ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_ID) is None


def test_the_blueprint_this_repo_ships_still_exists() -> None:
    """Guard against the whole file passing vacuously."""
    assert REPO_BLUEPRINT.is_file(), (
        "the shopping blueprint is not in this repository — the check is looking "
        "for something this integration no longer ships"
    )


async def test_it_finds_the_blueprint_wherever_home_assistant_filed_it(
    hass: HomeAssistant,
) -> None:
    """The bug that shipped in 0.4.3 and 0.4.4, named.

    Home Assistant files an imported blueprint under the **GitHub owner** —
    `momoz/` — not under this repository's own folder name. A check that looked
    for `calendora/` could never pass, so a household that had imported the
    blueprint was told to import it, forever.

    This asserts the real path *and* an unrelated one, because identity comes
    from the blueprint's `source_url` rather than from where it happens to sit,
    and neither the owner's name nor Home Assistant's filing rule is this
    integration's to predict.
    """
    for path in (
        IMPORTED_PATH,
        "blueprints/automation/somebody_elses_folder/whatever.yaml",
    ):
        await _install(hass, path)
        assert await async_check_blueprint_is_imported(hass) is True, (
            f"the blueprint at {path} was not recognised — identity must come "
            f"from source_url, not from the folder Home Assistant chose"
        )
        Path(hass.config.path(path)).unlink()
        await _reset_blueprint_cache(hass)


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
    assert not (blueprints / "automation" / "momoz").exists()
    assert await async_check_blueprint_is_imported(hass) is False
