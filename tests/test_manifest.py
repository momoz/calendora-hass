"""Static checks on the shipped metadata.

hassfest catches most of this in CI, but it runs in a container that is not
always available locally — and the strings/translations drift below is the kind
of mistake that is invisible in review and obvious to a user.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

INTEGRATION = Path(__file__).resolve().parents[1] / "custom_components" / "calendora"


def _load(name: str) -> dict:
    return json.loads((INTEGRATION / name).read_text(encoding="utf-8"))


def test_english_translations_match_strings() -> None:
    """`translations/en.json` is a copy of `strings.json`, and drifts silently."""
    assert _load("strings.json") == _load("translations/en.json")


def test_manifest_declares_what_hacs_and_ha_require() -> None:
    """HACS errors without `version`; the rest is the architecture in AGENTS.md."""
    manifest = _load("manifest.json")

    assert manifest["domain"] == "calendora"
    assert manifest["version"]
    assert manifest["config_flow"] is True
    assert manifest["iot_class"] == "cloud_push"
    assert manifest["integration_type"] == "service"
    assert manifest["documentation"].startswith("https://")
    assert manifest["issue_tracker"].startswith("https://")


def test_changelog_covers_the_manifest_version() -> None:
    """A release tag equals the manifest version, so the changelog must know it."""
    version = _load("manifest.json")["version"]
    changelog = (INTEGRATION.parents[1] / "CHANGELOG.md").read_text(encoding="utf-8")

    assert f"## {version}" in changelog


def test_brand_icon_is_shipped() -> None:
    """HA 2026.3 ships brand assets here, not in the brands repo."""
    icon = INTEGRATION / "brand" / "icon.png"

    assert icon.is_file()
    assert icon.stat().st_size > 0


def test_no_translation_string_contains_a_url() -> None:
    """hassfest rejects URLs in translation strings, and it cannot run locally.

    The rule is right: a URL in a translated string goes stale, and translators
    break them. A user copying their own feed URL out of their own settings
    screen does not need an example of what a URL looks like — they need to know
    they grabbed the right field, which a path fragment does without tripping
    this.

    Both files are checked. For a custom integration `translations/en.json` is
    maintained by hand alongside `strings.json`, so they drift.
    """
    pattern = re.compile(r"https?://")

    def walk(node: object, path: str) -> list[str]:
        if isinstance(node, dict):
            return [
                hit for key, value in node.items() for hit in walk(value, f"{path}.{key}")
            ]
        if isinstance(node, list):
            return [
                hit for i, value in enumerate(node) for hit in walk(value, f"{path}[{i}]")
            ]
        if isinstance(node, str) and pattern.search(node):
            return [f"{path}: {node}"]
        return []

    offenders = walk(_load("strings.json"), "strings") + walk(
        _load("translations/en.json"), "en"
    )
    assert not offenders, "URLs in translation strings: " + "; ".join(offenders)
