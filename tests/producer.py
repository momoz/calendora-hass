"""Calendora's own fixtures, as the tests for new entities consume them.

`tests/fixtures/` is hand-built and predates the vendored contract; the shop
blueprint's three-release failure came from a hand-built shape that the real
producer never emitted. So every test written for the entities added with the
2026-10-28 re-vendor reads **`fixtures/`** — the pairs Calendora generates by
replaying real requests through its real handlers — and nothing here edits a
value on the way through. A case the producer has not generated is a gap to
file, not a fixture to write: see `require`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def pair(name: str) -> dict[str, Any]:
    """One request/response pair, exactly as vendored."""
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def body(name: str) -> Any:
    """The response body of one pair."""
    return pair(name)["response"]["body"]


def require(found: Any, gap: str) -> Any:
    """Skip, naming the gap, when the producer has not generated a case yet.

    A skip rather than a hand-made value: the test starts running by itself on
    the re-vendor that brings the case, and until then the suite says plainly
    what it is not covering instead of passing on something invented.
    """
    if not found:
        pytest.skip(f"no producer fixture for this case yet — {gap}")
    return found
