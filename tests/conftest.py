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
