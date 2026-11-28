"""The quantifiers of the contract (`schema.py`): how a test's raw candidates become a verdict.

Candidates are windows, regions or cells with the positions they occupy, `lo` to `hi` (hi excluded; the cell
offsets of `chain.Window`, spaces and breaks they cover included). exists, not_exists, all and the locator
form read only whether a candidate set is empty; `count` and `unique` read a selection: scan left to right,
keep the leftmost candidate, and among those starting there the longest (of equal length, the cheaper,
then the one listed first); drop every candidate that overlaps one kept, by position: two candidates that
share only a space or a break overlap.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import Protocol, TypeVar


class Span(Protocol):
    lo: int
    hi: int


W = TypeVar("W", bound=Span)


def select[W: Span](candidates: Iterable[W]) -> list[W]:
    """Leftmost, then longest, non-overlapping: the candidates a count reads."""
    kept: list[W] = []
    end = -1
    for c in sorted(candidates, key=lambda c: (c.lo, -c.hi, getattr(c, "cost", 0))):
        if c.lo >= end:
            kept.append(c)
            end = c.hi
    return kept


def exists(candidates: Sequence) -> bool:
    return bool(candidates)


def not_exists(candidates: Sequence) -> bool:
    return not candidates


def unique[W: Span](candidates: Iterable[W]) -> bool:
    return len(select(candidates)) == 1


def count[W: Span](candidates: Iterable[W], low: int, high: int | None = None) -> bool:
    n = len(select(candidates))
    return low <= n <= (low if high is None else high)


def every[W: Span](anchors: Sequence[W], witness: Callable[[W], bool]) -> bool:
    """For all: there is at least one anchor, and every anchor has a witness."""
    return bool(anchors) and all(witness(a) for a in anchors)


def locator_and_not(locator: Sequence, claim: Sequence) -> bool:
    """The locator has a witness and the claim has none: a negative test needs its target found first."""
    return bool(locator) and not claim
