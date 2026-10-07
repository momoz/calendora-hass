"""The control that checks the artifact, exercised in both directions.

`scripts/verify_release_artifact.py` only ever runs against a real release, on a
runner, once a tag is published — which is precisely the situation where nobody
watches it fail. So every check in it is a pure function over a tree on disk,
and this file hands each one a **broken** tree and asserts it complains.

That is the same rule the blueprint check earned the hard way: a check that
cannot tell present from absent reports a clean bill either way, and the release
it waves through is the one nobody looks at afterwards.

The fixtures are built from this repository's real files rather than from
invented ones, so a rename here fails these tests instead of quietly making them
test nothing.
"""

from __future__ import annotations

import importlib.util
import json
import urllib.error
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_script():
    """Load the script by path — `scripts/` is not an importable package."""
    path = REPO_ROOT / "scripts" / "verify_release_artifact.py"
    spec = importlib.util.spec_from_file_location("verify_release_artifact", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


verify_release_artifact = _load_script()
CheckFailed = verify_release_artifact.CheckFailed


@pytest.fixture
def artifact(tmp_path: Path) -> Path:
    """A tree shaped like an unpacked release archive, from the real files.

    Only the parts the checks read are copied. Everything copied is the genuine
    article: a fabricated manifest or a fabricated blueprint would let a rename
    in the real ones pass unnoticed, which is the failure mode this whole file
    exists to prevent.
    """
    tree = tmp_path / "calendora-hass-0.5.0"
    integration = tree / verify_release_artifact.INTEGRATION_IN_ARCHIVE
    integration.mkdir(parents=True)

    real_integration = REPO_ROOT / verify_release_artifact.INTEGRATION_IN_ARCHIVE
    manifest = json.loads((real_integration / "manifest.json").read_text(encoding="utf-8"))
    manifest["version"] = "0.5.0"
    (integration / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (integration / "blueprint_check.py").write_text(
        (real_integration / "blueprint_check.py").read_text(encoding="utf-8"), encoding="utf-8"
    )

    (tree / "hacs.json").write_text(
        (REPO_ROOT / "hacs.json").read_text(encoding="utf-8"), encoding="utf-8"
    )

    blueprint = tree / verify_release_artifact.BLUEPRINT_IN_ARCHIVE
    blueprint.parent.mkdir(parents=True)
    blueprint.write_text(
        (REPO_ROOT / verify_release_artifact.BLUEPRINT_IN_ARCHIVE).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return tree


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://example.invalid", code, "nope", {}, None)


# --------------------------------------------------------------------------
# The paths the script hard-codes — guards against the whole file passing
# vacuously after a move.
# --------------------------------------------------------------------------


def test_the_paths_the_script_looks_for_are_the_paths_this_repo_has() -> None:
    assert (REPO_ROOT / verify_release_artifact.BLUEPRINT_IN_ARCHIVE).is_file()
    assert (
        REPO_ROOT / verify_release_artifact.INTEGRATION_IN_ARCHIVE / "manifest.json"
    ).is_file()


# --------------------------------------------------------------------------
# A whole artifact, and each way it can be wrong.
# --------------------------------------------------------------------------


def test_a_sound_artifact_raises_nothing(artifact: Path) -> None:
    assert verify_release_artifact.check_integration_is_present(artifact) == []
    assert verify_release_artifact.check_manifest_version_matches_tag(artifact, "0.5.0") == []
    assert verify_release_artifact.check_hacs_layout(artifact) == []
    assert verify_release_artifact.check_blueprint_is_in_the_archive(artifact) == []


def test_an_archive_with_no_integration_in_it_is_caught(artifact: Path) -> None:
    (artifact / verify_release_artifact.INTEGRATION_IN_ARCHIVE / "manifest.json").unlink()
    problems = verify_release_artifact.check_integration_is_present(artifact)
    assert problems and "installs nothing" in problems[0]


def test_a_manifest_that_disagrees_with_the_tag_is_caught(artifact: Path) -> None:
    """HACS records the tag; the update entity shows the manifest.

    When they differ, each side looks right on its own — which is exactly how a
    household ends up being told it is up to date on a version it does not have.
    """
    problems = verify_release_artifact.check_manifest_version_matches_tag(artifact, "0.5.1")
    assert problems and "0.5.1" in problems[0] and "0.5.0" in problems[0]


def test_hacs_json_claiming_the_wrong_layout_is_caught(artifact: Path) -> None:
    hacs = json.loads((artifact / "hacs.json").read_text(encoding="utf-8"))
    hacs["content_in_root"] = True
    (artifact / "hacs.json").write_text(json.dumps(hacs), encoding="utf-8")

    problems = verify_release_artifact.check_hacs_layout(artifact)
    assert problems and "content_in_root" in problems[0]


def test_a_release_that_ships_no_blueprint_is_caught(artifact: Path) -> None:
    """The three-release failure, in the form it would take today.

    The integration would install, the Repairs notice would fire, and the URL in
    it would point into an archive with nothing at the other end.
    """
    (artifact / verify_release_artifact.BLUEPRINT_IN_ARCHIVE).unlink()
    problems = verify_release_artifact.check_blueprint_is_in_the_archive(artifact)
    assert problems and "not in the archive" in problems[0]


def test_a_blueprint_that_is_not_a_blueprint_is_caught(artifact: Path) -> None:
    """What a fetched error page or a truncated file looks like on disk."""
    (artifact / verify_release_artifact.BLUEPRINT_IN_ARCHIVE).write_text(
        "<!doctype html><title>404</title>", encoding="utf-8"
    )
    problems = verify_release_artifact.check_blueprint_is_in_the_archive(artifact)
    assert problems and "not a blueprint" in problems[0]


# --------------------------------------------------------------------------
# The import URL — the one promise this integration makes to a person.
# --------------------------------------------------------------------------


def test_the_import_url_is_read_from_the_archive_not_from_this_checkout(
    artifact: Path,
) -> None:
    url = verify_release_artifact.import_url_from(artifact)
    assert url.startswith("https://github.com/momoz/calendora-hass/blob/")
    assert url.endswith("blueprints/automation/calendora/shopping_list_on_arrival.yaml")

    # And it genuinely comes from the archive's file, rather than from this
    # checkout or from a constant here — change the file, get the new value.
    check = artifact / verify_release_artifact.INTEGRATION_IN_ARCHIVE / "blueprint_check.py"
    check.write_text('IMPORT_URL = "https://example.invalid/x.yaml"\n', encoding="utf-8")
    assert verify_release_artifact.import_url_from(artifact) == "https://example.invalid/x.yaml"


def test_an_integration_with_no_import_url_at_all_is_caught(artifact: Path) -> None:
    check = artifact / verify_release_artifact.INTEGRATION_IN_ARCHIVE / "blueprint_check.py"
    check.write_text("IMPORT_ELSEWHERE = 'nothing'\n", encoding="utf-8")
    with pytest.raises(CheckFailed, match="no IMPORT_URL"):
        verify_release_artifact.import_url_from(artifact)


def test_the_blob_url_is_turned_into_the_file_home_assistant_actually_fetches() -> None:
    assert verify_release_artifact.raw_url_for(
        "https://github.com/momoz/calendora-hass/blob/main/blueprints/a.yaml"
    ) == "https://raw.githubusercontent.com/momoz/calendora-hass/main/blueprints/a.yaml"


def test_an_import_url_that_404s_is_caught(artifact: Path) -> None:
    """`HANDOFF.md` once told Mike to re-import from a path that could not exist.

    It took a person trying it to find out. This is that, before the release.
    """

    def fetch(url: str) -> bytes:
        raise _http_error(404)

    problems, served = verify_release_artifact.check_import_url_serves_a_blueprint(
        "https://github.com/momoz/calendora-hass/blob/main/gone.yaml", fetch=fetch
    )
    assert served is None
    assert problems and "dead end" in problems[0]


def test_an_import_url_serving_a_login_page_is_caught() -> None:
    """A private repository serves HTML with a 200, not the file."""

    def fetch(url: str) -> bytes:
        return b"<!doctype html><title>Sign in</title>"

    problems, served = verify_release_artifact.check_import_url_serves_a_blueprint(
        "https://github.com/momoz/calendora-hass/blob/main/x.yaml", fetch=fetch
    )
    assert served is not None
    assert problems and "not a blueprint" in problems[0]


def test_an_import_url_serving_the_real_blueprint_is_clean(artifact: Path) -> None:
    body = (artifact / verify_release_artifact.BLUEPRINT_IN_ARCHIVE).read_bytes()
    problems, served = verify_release_artifact.check_import_url_serves_a_blueprint(
        "https://github.com/momoz/calendora-hass/blob/main/x.yaml", fetch=lambda url: body
    )
    assert problems == []
    assert served == body


# --------------------------------------------------------------------------
# Divergence between `main` and the release — reported, never fatal.
# --------------------------------------------------------------------------


def test_the_served_blueprint_matching_the_release_says_nothing(artifact: Path) -> None:
    served = (artifact / verify_release_artifact.BLUEPRINT_IN_ARCHIVE).read_bytes()
    assert verify_release_artifact.compare_served_against_archive(served, artifact) == []


def test_a_main_ahead_of_the_release_is_reported_rather_than_swallowed(
    artifact: Path,
) -> None:
    """The hazard: importing main's blueprint against an older integration.

    It is a warning and not a failure on purpose — between releases the two
    legitimately differ — but a household that imports a blueprint calling a
    service its installed version does not have gets an automation that errors
    at the shop, so the difference is said out loud.
    """
    served = (artifact / verify_release_artifact.BLUEPRINT_IN_ARCHIVE).read_bytes() + b"\n# newer\n"
    notes = verify_release_artifact.compare_served_against_archive(served, artifact)
    assert notes and "points at `main`" in notes[0]


# --------------------------------------------------------------------------
# The release itself.
# --------------------------------------------------------------------------


def test_a_tag_with_no_published_release_is_a_failure_not_a_pass() -> None:
    """A tag that was never released offers HACS nothing, and looks shipped.

    This has happened here once already, in the other direction: a release was
    reported that had no tag behind it. Both states are invisible from a repo
    checkout, because a checkout is the one thing that does not need the release.
    """

    def fetch(url: str) -> bytes:
        raise _http_error(404)

    with pytest.raises(CheckFailed, match="never created"):
        verify_release_artifact.release_for_tag("9.9.9", fetch=fetch)


def test_an_unpack_that_finds_more_than_one_root_is_a_failure(tmp_path: Path) -> None:
    """GitHub wraps an archive in exactly one directory.

    More than one means the archive is not what this script assumes, and the
    rest of the checks would look inside the wrong tree — passing while reading
    nothing.
    """
    import zipfile

    archive = tmp_path / "two-roots.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("one/file.txt", "a")
        zipped.writestr("two/file.txt", "b")

    with pytest.raises(CheckFailed, match="found 2"):
        verify_release_artifact.unpack(archive, tmp_path / "out")
