"""Catch a vendored contract that has come apart from itself.

`CONTRACT.md` §10's guarantee is that Calendora cannot change the interface
without breaking this build. That holds only while the vendored copies are
current. If `docs/API-SURFACE.md` is re-vendored and `fixtures/` is not — or the
reverse — every test in `test_contract_fixtures.py` keeps passing against the
older half, and the guarantee has quietly inverted into its opposite: a green
build asserting a contract nobody is offering any more.

**Nothing here can prove the pair is up to date.** Proving that needs the
current upstream fingerprint, and this repository is public while Calendora is
private, so CI cannot read it. What these tests do is cheaper and still worth
having: they fail when the two vendored halves disagree with *each other*, which
is what a half-finished re-vendor actually looks like. The remaining half is
tracked as a gap — see the module note at the bottom.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SURFACE = ROOT / "docs" / "API-SURFACE.md"
FIXTURES = ROOT / "fixtures"


@pytest.fixture(scope="module")
def surface_text() -> str:
    return SURFACE.read_text(encoding="utf-8")


def test_the_vendored_surface_records_where_it_came_from(surface_text: str) -> None:
    """`CONTRACT.md` §3: the copy carries the commit it was taken from.

    A re-vendor that pastes the body and drops the header leaves a document that
    looks authoritative and cannot be dated. Failing here is the only moment
    anybody would notice.
    """
    assert re.search(
        # Trailing prose allowed: the 2026-10-28 extract reads "@ `4a7fb28`
        # (this change is the commit after it)". The sha is what must be there.
        r"^\*\*Source:\*\* `momoz/calendora` @ `[0-9a-f]{7,40}`",
        surface_text,
        re.MULTILINE,
    ), "no `**Source:** … @ `<sha>`` line — see CONTRACT.md §3"

    assert re.search(
        r"^\*\*Contract fingerprint:\*\* `[0-9a-f]{8,}`", surface_text, re.MULTILINE
    ), "no contract fingerprint recorded"

    assert re.search(
        r"^\*\*Regenerated:\*\* \d{4}-\d{2}-\d{2}$", surface_text, re.MULTILINE
    ), "no regeneration date"


def test_the_stated_fixture_count_matches_the_directory(surface_text: str) -> None:
    """The cheapest possible signal that the two halves have come apart.

    Calendora runs this same check on its own side (`CONTRACT.md` §10a) against
    the directory it generates. Running it here against the directory actually
    vendored is what makes it catch a *half*-finished vendoring, which is the
    failure that only ever shows up downstream.
    """
    stated = re.search(r"\*\*(\d+) request/response pairs\*\*", surface_text)
    assert stated, "§10 no longer states a fixture count in prose"

    expected = int(stated.group(1))
    actual = len(list(FIXTURES.glob("*.json")))

    assert actual == expected, (
        f"docs/API-SURFACE.md §10 says {expected} request/response pairs, "
        f"fixtures/ holds {actual}. One half was re-vendored and the other was "
        f"not — re-copy both from the same Calendora commit rather than editing "
        f"the number to match."
    )


def test_every_fixture_named_in_the_prose_was_actually_vendored(
    surface_text: str,
) -> None:
    """§10 names the pairs a release added. A named-but-absent file is a
    truncated copy, and it is invisible to a count that happens to still add up
    because something else arrived in the same vendoring.
    """
    section = surface_text.split("## 10. Fixtures", 1)[-1]
    named = set(re.findall(r"`([a-z0-9]+(?:-[a-z0-9]+)+)`", section))
    # Only names that look like fixture stems, not prose in backticks.
    named = {n for n in named if not n.startswith("api")}

    missing = sorted(n for n in named if not (FIXTURES / f"{n}.json").is_file())
    assert not missing, (
        f"§10 names {missing} but no such fixture is vendored — the copy is "
        f"incomplete"
    )


def test_the_fingerprint_covers_the_fixtures_we_actually_hold(
    surface_text: str,
) -> None:
    """The recorded fingerprint, recomputed from the vendored directory.

    Until 2026-10-28 this was deliberately not checked: the algorithm was not
    written down, and guessing one that happened to match once would have made
    a check that passes forever (card #105). Calendora's agent then supplied
    it — sha256 over each `*.json` name followed by its bytes, in name order,
    first sixteen hex digits — and it reproduces both the old and the new
    fingerprint exactly. Still not in the extract's §10 prose; asked for.

    What this catches is the half-finished re-vendor: the doc from one commit
    and the fixtures from another, which the count test misses whenever the
    count happens to be unchanged.
    """
    import hashlib

    recorded = re.search(
        r"^\*\*Contract fingerprint:\*\* `([0-9a-f]{16})`", surface_text, re.MULTILINE
    )
    assert recorded, "no 16-digit contract fingerprint recorded"

    digest = hashlib.sha256()
    for path in sorted(FIXTURES.glob("*.json"), key=lambda p: p.name):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())

    assert digest.hexdigest()[:16] == recorded.group(1), (
        "fixtures/ does not hash to the fingerprint docs/API-SURFACE.md records "
        "— re-copy both from the same Calendora commit"
    )


# Whether these two halves, agreeing with each other, agree with Calendora
# *today* is still not checked here: that needs the upstream fingerprint, and
# this repository is public while Calendora is private. `contract-drift.yml`
# asks the live server instead.
