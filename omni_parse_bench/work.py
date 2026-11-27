"""Deterministic work counters for the reader and the chain search.

Verdicts never depend on time or on these counts. The counters record how much work a read or a search did,
in units that do not change between machines, so a test can assert that the worst inputs stay linear and a
page that goes over `BOUNDS` is logged (a warning, never a changed verdict).
"""

from __future__ import annotations

import logging
from collections import Counter

log = logging.getLogger("omni_parse_bench.work")

COUNTS: Counter[str] = Counter()

# fixed per-call bounds: the reader may do this much per input character, the search this much per cell pair
BOUNDS = {
    "diff_cells_per_char": 100,  # difflib cells (len x len of each aligned piece) per character read
    "diff_cells_floor": 4_000_000,
    "emit_runs_per_char": 50,  # markup runs visited per character read
    "states_per_cell_pair": 16,  # search states per (gold cells + 1) x (output cells + 1)
}


def add(name: str, n: int = 1) -> None:
    COUNTS[name] += n


def reset() -> None:
    COUNTS.clear()


def snapshot() -> dict[str, int]:
    return dict(COUNTS)


def check_read(chars: int, before: dict[str, int]) -> list[str]:
    """Warn about a read that went over the reader bounds; returns the names that did."""
    d = {k: COUNTS[k] - before.get(k, 0) for k in ("diff_cells", "emit_runs")}
    over = []
    if d["diff_cells"] > BOUNDS["diff_cells_floor"] + BOUNDS["diff_cells_per_char"] * chars:
        over.append("diff_cells")
    if d["emit_runs"] > BOUNDS["emit_runs_per_char"] * chars + 1000:
        over.append("emit_runs")
    for k in over:
        log.warning("reader work over its bound: %s=%d for %d characters", k, d[k], chars)
    return over


def check_search(m: int, n: int, states: int) -> bool:
    """Warn about a search that went over its bound."""
    bound = BOUNDS["states_per_cell_pair"] * (m + 1) * (n + 1)
    if states > bound:
        log.warning("search work over its bound: %d states for %d x %d cells", states, m, n)
        return True
    return False
