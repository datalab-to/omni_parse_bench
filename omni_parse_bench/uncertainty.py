"""Uncertainty for the scorer's summary: an interval on each score, and a paired comparison of two systems.

A document's tests pass or fail together, so a score's uncertainty is that of a sample of documents, not of
tests. Both functions resample documents (a cluster bootstrap): they draw the dataset's documents with
replacement, the same draw for every slice (and, in `paired`, for both systems), and read each statistic
off the draw. The percentiles of those statistics are the interval.

They take score lines, as `scores.jsonl` holds them and as the summary reads them, and use the standard
library only. The summary itself is unchanged."""

from __future__ import annotations

import random
import statistics
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from omni_parse_bench import vocab
from omni_parse_bench.scorers.unit_tests import tests as _tests

SLICES = ("families", "per_tag", "per_suite", "per_test_type", "per_arg_kind", "per_derivation")
_ORDER = {"families": vocab.FAMILY_ORDER, "per_test_type": tuple(vocab.FAMILIES),
          "per_arg_kind": tuple(_tests.KINDS)}
_COUNTS = {"families": "per_family", "per_tag": "per_tag", "per_test_type": "per_test_type",
           "per_arg_kind": "per_arg_kind", "per_derivation": "per_derivation"}

# Note: a slice's counts, `{slice: {key: {document: [tests, passed]}}}`.
Table = dict[str, dict[str, dict[str, list[int]]]]


def _table(pages: Iterable[Mapping[str, Any]]) -> Table:
    """Each slice's tests and passed counts by key and document, from score lines. A line without a count,
    or without `row.suite`, adds nothing to that slice, as in the summary; a line with no `row.document`
    is refused, since a document is what is resampled."""
    out: Table = {s: {} for s in SLICES}

    def add(slice_: str, key: str, document: str, tests: int, passed: int) -> None:
        c = out[slice_].setdefault(key, {}).setdefault(document, [0, 0])
        c[0] += tests
        c[1] += passed

    for x in pages:
        row = x.get("row") or {}
        if "document" not in row:
            raise ValueError(f"a score line ({x.get('id', '?')!r}) has no row.document; intervals resample "
                             "documents, so each line needs the document its page came from")
        if "suite" in row:
            add("per_suite", row["suite"], row["document"], x["tests"], x["passed"])
        for slice_, name in _COUNTS.items():
            for key, c in x.get(name, {}).items():
                add(slice_, key, row["document"], c["tests"], c["passed"])
    return {s: {k: v for k, v in ks.items() if sum(c[0] for c in v.values())} for s, ks in out.items()}


def _documents(table: Table) -> list[str]:
    """Every document in the table, sorted."""
    return sorted({d for ks in table.values() for v in ks.values() for d in v})


def _keys(slice_: str, table: Table) -> list[str]:
    """The slice's keys: the vocabulary's order first, then the rest sorted, as the summary orders them."""
    have = table[slice_]
    order = _ORDER.get(slice_, ())
    return [*(k for k in order if k in have), *sorted(have.keys() - set(order))]


def _sparse(table: Table, index: Mapping[str, int]) -> dict[tuple[str, str], list[tuple[int, int, int]]]:
    """Each (slice, key)'s (document index, tests, passed) triples, over the documents in `index`."""
    return {(s, k): [(index[d], c[0], c[1]) for d, c in v.items() if d in index]
            for s, ks in table.items() for k, v in ks.items()}


def _weights(rng: random.Random, n: int) -> list[int]:
    """How many times each of `n` documents is drawn, in one draw of `n` with replacement."""
    m = [0] * n
    for i in rng.choices(range(n), k=n):
        m[i] += 1
    return m


def _scores(sparse: Mapping[tuple[str, str], Sequence[tuple[int, int, int]]], m: Sequence[int]
            ) -> dict[tuple[str, str], float]:
    """Each (slice, key)'s score under the weights `m`, left out when it has no tests there, plus the
    headline under `("score", "")`: the mean of the families' scores, as the summary takes it."""
    out: dict[tuple[str, str], float] = {}
    for sk, triples in sparse.items():
        n = k = 0
        for i, t, p in triples:
            if w := m[i]:
                n += w * t
                k += w * p
        if n:
            out[sk] = k / n
    fam = [v for (s, _), v in out.items() if s == "families"]
    if fam:
        out[("score", "")] = statistics.fmean(fam)
    return out


def _quantile(xs: Sequence[float], q: float) -> float:
    """The `q` quantile of sorted `xs`, by linear interpolation."""
    at = (len(xs) - 1) * q
    lo = int(at)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (at - lo)


def _bounds(draws: list[float], level: float) -> tuple[float | None, float | None]:
    """The central `level` of the draws, or None when there are none."""
    if not draws:
        return None, None
    draws.sort()
    tail = (1 - level) / 2
    return _quantile(draws, tail), _quantile(draws, 1 - tail)


def _check(resamples: int, level: float) -> None:
    if resamples < 1:
        raise ValueError(f"resamples must be at least 1, not {resamples}")
    if not 0 < level < 1:
        raise ValueError(f"level must be between 0 and 1, not {level}")


def _method(resamples: int, seed: int, level: float) -> dict[str, Any]:
    return {"method": "cluster bootstrap over documents, percentile interval", "level": level,
            "resamples": resamples, "seed": seed}


def _totals(sparse: Mapping[tuple[str, str], Sequence[tuple[int, int, int]]]) -> tuple[int, int]:
    """The tests and documents under the families, which hold every test once."""
    tests = sum(t for sk, ts in sparse.items() if sk[0] == "families" for _, t, _ in ts)
    docs = {i for sk, ts in sparse.items() if sk[0] == "families" for i, _, _ in ts}
    return tests, len(docs)


def intervals(pages: Iterable[Mapping[str, Any]], *, resamples: int = 1000, seed: int = 0,
              level: float = 0.95) -> dict[str, Any]:
    """The summary's `score`, `families` and slices (`per_tag`, `per_suite`, `per_test_type`,
    `per_arg_kind`, `per_derivation`), each entry now `{"score", "low", "high", "tests", "documents"}`:
    its score and the central `level` of its scores over `resamples` draws of the documents (a cluster
    bootstrap, the same draws for every entry, so the headline and the families agree). `score` holds the
    headline as one such entry; `interval` says how it was made. Deterministic for a `seed`. A slice with
    no tests is left out. A slice's `documents` is how many documents its tests come from, and a slice of
    few documents has a wide interval and a coarse one.

    Note: pages with the same `row.document` are one document; pages of one source under different
    document values are separate ones, and the interval says nothing of that dependence."""
    _check(resamples, level)
    table = _table(pages)
    docs = _documents(table)
    sparse = _sparse(table, {d: i for i, d in enumerate(docs)})
    point = _scores(sparse, [1] * len(docs))
    draws: dict[tuple[str, str], list[float]] = {sk: [] for sk in point}
    rng = random.Random(seed)
    for _ in range(resamples if docs else 0):
        for sk, v in _scores(sparse, _weights(rng, len(docs))).items():
            if sk in draws:
                draws[sk].append(v)

    def entry(sk: tuple[str, str]) -> dict[str, Any]:
        low, high = _bounds(draws[sk], level)
        n, d = _totals(sparse) if sk[0] == "score" else (
            sum(t for _, t, _ in sparse[sk]), len({i for i, _, _ in sparse[sk]}))
        return {"score": point[sk], "low": low, "high": high, "tests": n, "documents": d}

    out: dict[str, Any] = {"score": entry(("score", "")) if ("score", "") in point else None}
    for s in SLICES:
        out[s] = {k: entry((s, k)) for k in _keys(s, table) if (s, k) in point}
    return out | {"interval": _method(resamples, seed, level)}


def paired(pages_a: Iterable[Mapping[str, Any]], pages_b: Iterable[Mapping[str, Any]], *,
           resamples: int = 1000, seed: int = 0, level: float = 0.95) -> dict[str, Any]:
    """Two systems' score lines compared over the documents both have: for the headline (`score`), each
    family and each slice, `{"a", "b", "gap", "low", "high", "documents", "separable"}`. `gap` is a's score
    minus b's; `low` and `high` are the central `level` of the gap over `resamples` draws of the paired
    documents, one draw for both systems; `separable` is whether that interval leaves out 0. An entry
    both systems have tests for, on the paired documents, is kept.

    `documents_paired` counts the documents in both; `documents_unpaired` how many each system has that the
    other lacks, and they are left out. Raises ValueError when no document is in both.

    Note: separable is a statement about this dataset's documents, not a significance test across several
    slices; with many slices some will separate by chance."""
    _check(resamples, level)
    ta, tb = _table(pages_a), _table(pages_b)
    da, db = set(_documents(ta)), set(_documents(tb))
    both = sorted(da & db)
    if not both:
        raise ValueError(f"the two systems have no document in common ({len(da)} in the first, {len(db)} "
                         "in the second), so there is nothing to pair; check both runs are of the same "
                         "dataset and manifest")
    index = {d: i for i, d in enumerate(both)}
    sa, sb = _sparse(ta, index), _sparse(tb, index)
    pa, pb = _scores(sa, [1] * len(both)), _scores(sb, [1] * len(both))
    keys = [sk for sk in pa if sk in pb]
    draws: dict[tuple[str, str], list[float]] = {sk: [] for sk in keys}
    rng = random.Random(seed)
    for _ in range(resamples):
        m = _weights(rng, len(both))
        va, vb = _scores(sa, m), _scores(sb, m)
        for sk in keys:
            if sk in va and sk in vb:
                draws[sk].append(va[sk] - vb[sk])

    def entry(sk: tuple[str, str]) -> dict[str, Any]:
        low, high = _bounds(draws[sk], level)
        gap = pa[sk] - pb[sk]
        docs = len({i for sp in (sa, sb) for i, _, _ in sp.get(sk, ())} if sk[0] != "score" else both)
        return {"a": pa[sk], "b": pb[sk], "gap": gap, "low": low, "high": high, "documents": docs,
                "separable": low is not None and high is not None and (low > 0 or high < 0)}

    out: dict[str, Any] = {"score": entry(("score", "")) if ("score", "") in keys else None}
    for s in SLICES:
        out[s] = {k: entry((s, k)) for k in _keys(s, ta) if (s, k) in draws}
    return out | {"documents_paired": len(both),
                  "documents_unpaired": {"a": len(da - db), "b": len(db - da)},
                  "interval": _method(resamples, seed, level)}
