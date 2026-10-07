#!/usr/bin/env python3
"""Check the thing HACS hands a household, rather than the commit it came from.

**Why this exists.** `validate.yml` proves a *commit* is sound: it checks out the
tree, runs hassfest, the test suite and the HACS action against it, and goes
green. Nothing in this repository has ever opened the artifact a user actually
receives — the release archive HACS downloads, and the URL the Repairs notice
tells them to paste.

That gap is not hypothetical here. Three releases shipped a blueprint that had
never executed anywhere (`docs/SHOP-ARRIVAL-BUILD-LOG.md`), and the process
answer written down at the time had three parts. Two shipped — the README
carries the import step, and a Repairs notice fires when the blueprint is
absent. This is the third: *verify the artifact, not the commit.*

Apply the silent-success test to the state before this script. If a tag were
published with the blueprint missing, or with `manifest.json` naming a different
version than the tag, or with the import URL pointing at a file that had been
renamed — **what would look different?** Nothing. Every check this repository
owns would still be green, because none of them fetches anything.

**What it checks**, in the order a household meets them:

1. The tag has a **published release**. A tag that was never created, or created
   and never released, offers HACS nothing — and reads as shipped from here.
2. The archive downloads and unpacks.
3. `custom_components/calendora/manifest.json` declares **exactly** the tag's
   version. A mismatch is the failure where HACS's record says one number and
   the `update` entity a person actually looks at says another.
4. `hacs.json` still describes the layout the archive really has.
5. The blueprint is **in the archive** and parses.
6. The `IMPORT_URL` compiled into *the downloaded copy* of `blueprint_check.py`
   resolves, and what it serves parses as the same blueprint. This is the only
   part of the product that is a promise made to a user in a notice, and it is
   the one nothing could have caught: `HANDOFF.md` once told Mike to re-import
   from a path that could not exist, and it took a person trying it to find out.

**What it deliberately does not do.** It does not fail when the blueprint served
by the import URL differs from the one in the archive. The URL points at `main`
by design, so between releases those two legitimately differ — but a household
importing from `main` while running an older release is a real hazard (a
blueprint calling a service its installed integration does not have yet), so the
divergence is **reported loudly** rather than swallowed or treated as a fault.

Loading the blueprint inside Home Assistant is not done here either. That gate
already exists as `tests/test_blueprint_configures.py`, and the archive carries
the tests — so the workflow runs pytest *from inside the unpacked archive*,
which is the same gate aimed at the artifact instead of the working tree.

Usage:

    python scripts/verify_release_artifact.py                  # latest release
    python scripts/verify_release_artifact.py --tag 0.5.0
    python scripts/verify_release_artifact.py --unpack-to /tmp/artifact

Exits non-zero if any check fails. Warnings alone do not fail it.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

REPO = "momoz/calendora-hass"

#: Where the blueprint lives inside the archive, and inside this repository.
BLUEPRINT_IN_ARCHIVE = "blueprints/automation/calendora/shopping_list_on_arrival.yaml"

#: HACS installs an integration by copying this folder into the household's
#: config directory. If it is not in the archive, nothing is.
INTEGRATION_IN_ARCHIVE = "custom_components/calendora"

Fetch = Callable[[str], bytes]


class CheckFailed(Exception):
    """A check could not even be run — a missing release, a download that 404s."""


# --------------------------------------------------------------------------
# Fetching. Isolated behind these two functions so every check below can be
# tested offline, which is the difference between a control that is exercised
# and one that is only ever watched.
# --------------------------------------------------------------------------


def _request(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "calendora-hass"})
    # Anonymous requests are rate-limited to 60/hour per IP, which on a busy
    # runner fails as a 403 that reads exactly like a missing release. Use the
    # workflow's token when there is one.
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def latest_release_tag(repo: str = REPO, fetch: Fetch = _request) -> str:
    try:
        body = fetch(f"https://api.github.com/repos/{repo}/releases/latest")
    except urllib.error.HTTPError as err:
        raise CheckFailed(
            f"{repo} has no published release at all ({err.code}) — HACS has "
            f"nothing to offer any household"
        ) from err
    return json.loads(body)["tag_name"]


def release_for_tag(tag: str, repo: str = REPO, fetch: Fetch = _request) -> dict:
    """The published release, or a failure naming which half is missing.

    A tag with no release is the specific shape worth catching: the commit is
    pushed, the version is bumped, the changelog says it shipped — and HACS,
    which reads releases rather than tags, is still offering the previous one.
    """
    try:
        body = fetch(f"https://api.github.com/repos/{repo}/releases/tags/{tag}")
    except urllib.error.HTTPError as err:
        if err.code == 404:
            raise CheckFailed(
                f"no published release for tag {tag!r}. Either the tag was "
                f"never created, or it exists and was never released — HACS "
                f"reads releases, so both look identical to a household: "
                f"nothing on offer."
            ) from err
        raise
    return json.loads(body)


def download_archive(tag: str, dest: Path, repo: str = REPO, fetch: Fetch = _request) -> Path:
    """Fetch the archive HACS fetches for an integration at this tag."""
    url = f"https://github.com/{repo}/archive/refs/tags/{tag}.zip"
    try:
        payload = fetch(url)
    except urllib.error.HTTPError as err:
        raise CheckFailed(f"the release archive did not download: {url} ({err.code})") from err
    dest.write_bytes(payload)
    return dest


def unpack(archive: Path, into: Path) -> Path:
    """Unpack and return the single top-level directory GitHub wraps it in."""
    with zipfile.ZipFile(archive) as zipped:
        zipped.extractall(into)
    roots = [child for child in into.iterdir() if child.is_dir()]
    if len(roots) != 1:
        raise CheckFailed(
            f"expected one directory inside the archive, found {len(roots)}: "
            f"{[str(root.name) for root in roots]}"
        )
    return roots[0]


# --------------------------------------------------------------------------
# The checks. Each takes a tree on disk and returns problems — no printing, no
# exits — so `tests/test_release_artifact.py` can hand each one a broken tree
# and assert it complains. A check nobody has watched fail is a claim.
# --------------------------------------------------------------------------


def check_integration_is_present(tree: Path) -> list[str]:
    integration = tree / INTEGRATION_IN_ARCHIVE
    if not (integration / "manifest.json").is_file():
        return [
            f"{INTEGRATION_IN_ARCHIVE}/manifest.json is not in the archive — "
            f"this release installs nothing"
        ]
    return []


def check_manifest_version_matches_tag(tree: Path, tag: str) -> list[str]:
    """The number HACS records and the number the `update` entity shows.

    They come from different places — the tag and `manifest.json` — and when
    they disagree, the disagreement is invisible from either side alone.
    """
    manifest_path = tree / INTEGRATION_IN_ARCHIVE / "manifest.json"
    if not manifest_path.is_file():
        return []  # already reported by check_integration_is_present
    version = json.loads(manifest_path.read_text(encoding="utf-8")).get("version")
    if version != tag:
        return [
            f"manifest.json says version {version!r} but the release is tagged "
            f"{tag!r} — HACS would record one number and the update entity in "
            f"the household would show the other"
        ]
    return []


def check_hacs_layout(tree: Path) -> list[str]:
    """`hacs.json` describes the archive; check it still does."""
    hacs_path = tree / "hacs.json"
    if not hacs_path.is_file():
        return ["hacs.json is not in the archive"]
    hacs = json.loads(hacs_path.read_text(encoding="utf-8"))
    problems: list[str] = []
    if hacs.get("content_in_root"):
        problems.append(
            "hacs.json sets content_in_root, but this archive keeps the "
            "integration under custom_components/ — HACS would copy the wrong "
            "thing into the household"
        )
    return problems


def check_blueprint_is_in_the_archive(tree: Path) -> list[str]:
    """The file the import URL is supposed to serve, at the released version."""
    blueprint = tree / BLUEPRINT_IN_ARCHIVE
    if not blueprint.is_file():
        return [
            f"{BLUEPRINT_IN_ARCHIVE} is not in the archive — the release ships "
            f"an integration whose Repairs notice points at a file it does not "
            f"contain"
        ]
    return _blueprint_parses(blueprint.read_text(encoding="utf-8"), BLUEPRINT_IN_ARCHIVE)


def _blueprint_parses(text: str, where: str) -> list[str]:
    """A structural read, not a load.

    Loading it properly is Home Assistant's job and is covered by running the
    archive's own tests. This catches the cruder failure: a redirect page, an
    error document, an empty file — anything that is not a blueprint at all.
    """
    import yaml

    class _InputTolerant(yaml.SafeLoader):
        """`!input` is a Home Assistant tag; SafeLoader refuses unknown tags."""

    _InputTolerant.add_constructor("!input", lambda loader, node: None)

    try:
        parsed = yaml.load(text, Loader=_InputTolerant)
    except yaml.YAMLError as err:
        return [f"{where} is not parseable YAML: {err}"]
    if not isinstance(parsed, dict) or "blueprint" not in parsed:
        return [f"{where} parsed, but has no `blueprint:` block — it is not a blueprint"]
    metadata = parsed["blueprint"]
    missing = [key for key in ("name", "domain", "source_url") if key not in metadata]
    if missing:
        return [f"{where} is missing blueprint {', '.join(missing)}"]
    return []


def import_url_from(tree: Path) -> str:
    """Read `IMPORT_URL` out of the archive's own copy, without importing it.

    Read from the artifact rather than from this checkout on purpose: the
    question is what the *released* integration tells a household to paste, and
    taking it from the working tree would check the URL against itself.
    """
    source = (tree / INTEGRATION_IN_ARCHIVE / "blueprint_check.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "IMPORT_URL"
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise CheckFailed(
        "the archive's blueprint_check.py declares no IMPORT_URL — the Repairs "
        "notice has no address to hand anybody"
    )


def raw_url_for(blob_url: str) -> str:
    """`github.com/o/r/blob/ref/path` → the raw file Home Assistant fetches."""
    return blob_url.replace(
        "https://github.com/", "https://raw.githubusercontent.com/", 1
    ).replace("/blob/", "/", 1)


def check_import_url_serves_a_blueprint(
    blob_url: str, fetch: Fetch = _request
) -> tuple[list[str], bytes | None]:
    """Fetch what a user's Home Assistant would fetch, and check it is one."""
    raw = raw_url_for(blob_url)
    try:
        served = fetch(raw)
    except urllib.error.HTTPError as err:
        return (
            [
                f"the Repairs notice points at {blob_url}, and the file it "
                f"resolves to does not exist ({err.code} on {raw}) — every "
                f"household that follows the notice hits a dead end"
            ],
            None,
        )
    return _blueprint_parses(served.decode("utf-8"), raw), served


def compare_served_against_archive(served: bytes, tree: Path) -> list[str]:
    """Not a failure. A difference people should be told about out loud.

    The import URL points at `main`, so between releases it legitimately serves
    something newer than the release. That is the design — and it is also how a
    household ends up running a blueprint that calls a service the integration
    it has installed does not provide yet. Silence here would be the comfortable
    reading of a real hazard.
    """
    archived = (tree / BLUEPRINT_IN_ARCHIVE).read_bytes()
    if served == archived:
        return []
    return [
        "the blueprint served by the import URL is NOT the one in this "
        "release — the URL points at `main`, so anybody importing it now gets "
        "main's version against this release's integration. Check that main's "
        "blueprint does not require anything this release does not ship."
    ]


def verify(tag: str, unpack_to: Path, fetch: Fetch = _request) -> tuple[list[str], list[str]]:
    """Run everything. Returns (problems, warnings)."""
    release = release_for_tag(tag, fetch=fetch)
    print(f"  release   {release.get('name') or tag}  published {release.get('published_at')}")

    archive = download_archive(tag, unpack_to / f"{tag}.zip", fetch=fetch)
    tree = unpack(archive, unpack_to)
    print(f"  archive   {archive.name} → {tree.name}")

    problems: list[str] = []
    problems += check_integration_is_present(tree)
    problems += check_manifest_version_matches_tag(tree, tag)
    problems += check_hacs_layout(tree)
    problems += check_blueprint_is_in_the_archive(tree)

    warnings: list[str] = []
    url = import_url_from(tree)
    print(f"  notice    {url}")
    url_problems, served = check_import_url_serves_a_blueprint(url, fetch=fetch)
    problems += url_problems
    if served is not None and not url_problems:
        warnings += compare_served_against_archive(served, tree)

    return problems, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tag", help="release tag to check (default: the latest release)")
    parser.add_argument(
        "--unpack-to",
        type=Path,
        help="keep the unpacked archive here, for a later step to run tests inside",
    )
    parser.add_argument("--repo", default=REPO)
    args = parser.parse_args()

    keep = args.unpack_to is not None
    workdir = Path(args.unpack_to) if keep else Path(tempfile.mkdtemp(prefix="calendora-artifact-"))
    if keep:
        shutil.rmtree(workdir, ignore_errors=True)
    workdir.mkdir(parents=True, exist_ok=True)

    try:
        tag = args.tag or latest_release_tag(args.repo)
        print(f"Checking the artifact for {args.repo} {tag}")
        problems, warnings = verify(tag, workdir)
    except CheckFailed as err:
        print(f"\nFAIL  {err}")
        return 1
    finally:
        if not keep:
            shutil.rmtree(workdir, ignore_errors=True)

    for warning in warnings:
        print(f"\nWARN  {warning}")
    if problems:
        for problem in problems:
            print(f"\nFAIL  {problem}")
        return 1

    print(f"\nOK    the artifact for {tag} is the one this repository meant to ship")
    if keep:
        print(f"      unpacked at {workdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
