"""Shared test fixtures.

**Why the symlink below exists.** Home Assistant loads custom integrations by
mounting `hass.config.config_dir` at `sys.path[0]` and importing
`custom_components` from *there* (`homeassistant/loader.py`,
`_async_mount_config_dir`). Under pytest that config dir belongs to
pytest-homeassistant-custom-component, not to this repo, and the plugin's own
`custom_components` package is a regular package — so it wins the import no
matter where this repo sits on `sys.path`. Adding `__init__.py` here or
reordering `sys.path` does not help; only putting the integration inside the test
config dir does.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import pytest_homeassistant_custom_component

pytest_plugins = "pytest_homeassistant_custom_component"

_REPO_ROOT = Path(__file__).resolve().parents[1]
_INTEGRATION = _REPO_ROOT / "custom_components" / "calendora"
_TEST_CONFIG_CUSTOM_COMPONENTS = (
    Path(pytest_homeassistant_custom_component.__file__).parent
    / "testing_config"
    / "custom_components"
)


def _link_integration_into_test_config() -> None:
    """Make `custom_components.calendora` importable the way HA imports it."""
    link = _TEST_CONFIG_CUSTOM_COMPONENTS / "calendora"
    if link.is_symlink():
        if link.resolve() == _INTEGRATION:
            return
        link.unlink()
    elif link.exists():
        # A real directory here means someone copied a build in. Leave it alone
        # and fail loudly rather than testing a stale copy of the integration.
        raise RuntimeError(f"{link} exists and is not a symlink to {_INTEGRATION}")
    link.symlink_to(_INTEGRATION, target_is_directory=True)


_link_integration_into_test_config()


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let Home Assistant see this integration in every test."""
    return


_TEST_CONFIG_AUTOMATION_BLUEPRINTS = (
    Path(pytest_homeassistant_custom_component.__file__).parent
    / "testing_config"
    / "blueprints"
    / "automation"
)

#: Every folder this repository's tests write a blueprint into. `momoz` is where
#: Home Assistant actually files an imported blueprint — under the GitHub owner —
#: and the others are paths used to prove the check does not depend on that.
#: Listed rather than wildcarded so the plugin's own fixture blueprints are never
#: deleted by a test in this repository.
_BLUEPRINT_DIRS_WE_WRITE = ("calendora", "momoz", "somebody_elses_folder")


@pytest.fixture(autouse=True)
def clean_blueprint_directory():
    """Leave no blueprint behind, and start from none.

    `hass.config.path()` under pytest points into
    pytest-homeassistant-custom-component's own `testing_config`, which is a
    **real directory inside site-packages that survives the test run.** A test
    that installs the blueprint there to exercise it leaves it installed — for
    every later test in the session, and for every future session on the same
    machine.

    That matters more than ordinary tidiness here, because the control this
    repository just gained is *"is the blueprint absent?"*. Litter from one test
    makes that check answer "present" in a test written to prove it can say
    "absent" — a false pass on the exact assertion that would have caught the
    three-release failure. It showed up immediately, which is the only reason
    this is a fixture rather than a bug.
    """
    for name in _BLUEPRINT_DIRS_WE_WRITE:
        shutil.rmtree(_TEST_CONFIG_AUTOMATION_BLUEPRINTS / name, ignore_errors=True)
    yield
    for name in _BLUEPRINT_DIRS_WE_WRITE:
        shutil.rmtree(_TEST_CONFIG_AUTOMATION_BLUEPRINTS / name, ignore_errors=True)
