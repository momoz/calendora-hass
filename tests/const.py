"""Shared test constants.

No real household data and no real credential reaches this repository — it is
public. The key below is a fake with the right shape, and `example.invalid` is
reserved by RFC 2606 so no test can accidentally contact a real host.
"""

from __future__ import annotations

# Shaped like a real key (`cal_` prefix) so that any code path which parses or
# truncates one behaves the same in tests, and obviously fake so that nobody
# mistakes a leak for a real one.
API_KEY = "cal_test_not_a_real_key_0000000000000000000"


def load_fixture(name: str) -> dict:
    """Return a synthetic API response.

    Synthetic on purpose: these tests must fail because of the code, not because
    a live household changed overnight — and this repository is public, so no
    real family's calendar can be committed to it. Shapes come from
    `docs/API-SURFACE.md` §4a.
    """
    import json
    from pathlib import Path

    return json.loads(
        (Path(__file__).parent / "fixtures" / name).read_text(encoding="utf-8")
    )
