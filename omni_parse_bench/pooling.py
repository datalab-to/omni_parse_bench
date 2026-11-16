"""How much a set of documents is worth, when they hold different numbers of tests."""

from __future__ import annotations

from collections.abc import Iterable


def effective_documents(counts: Iterable[int]) -> float:
    """How many equal-sized documents the per-document test `counts` are worth: their sum squared over the
    sum of their squares. It is the number of documents when the counts are equal, and falls as they skew;
    0 for no tests. Scores are pooled over tests, so a document with many tests weighs more, and this says
    how much that costs in information."""
    xs = list(counts)
    sq = sum(x * x for x in xs)
    return sum(xs) ** 2 / sq if sq else 0.0
