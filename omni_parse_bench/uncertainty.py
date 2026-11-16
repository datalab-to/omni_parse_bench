"""Uncertainty for the scorer's summary: an interval on each score, and a paired comparison of two systems.

A document's tests pass or fail together, so a score's uncertainty is that of a sample of documents, not of
tests. Both functions resample documents (a cluster bootstrap): they draw the dataset's documents with
replacement, the same draw for every slice (and, in `paired`, for both systems), and read each statistic
off the draw. The percentiles of those statistics are the interval.

They take score lines, as `scores.jsonl` holds them and as the summary reads them, and use the standard
library only. The summary itself is unchanged."""

from __future__ import annotations

import collections
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
    return {(s, k): [(index[d], c[0], c[1]) for d, c in v.items() if d in index and c[0]]
            for s, ks in table.items() for k, v in ks.items()}


def _weights(rng: random.Random, n: int) -> list[int]:
    """How many times each of `n` documents is drawn, in one draw of `n` with replacement."""
    m = [0] * n
    for i in rng.choices(range(n), k=n):
        m[i] += 1
    return m


HEADLINE = ("headline", "")


def _scores(sparse: Mapping[tuple[str, str], Sequence[tuple[int, int, int]]], m: Sequence[int],
            families: Sequence[str]) -> dict[tuple[str, str], float]:
    """Each (slice, key)'s score under the weights `m`, left out when it has no tests there. The headline,
    under `HEADLINE`, is the mean of the scores of `families`, and is left out when any of them has no
    tests in the draw, so it is always a mean over the same families."""
    out: dict[tuple[str, str], float] = {}
    for sk, triples in sparse.items():
        n = k = 0
        for i, t, p in triples:
            if w := m[i]:
                n += w * t
                k += w * p
        if n:
            out[sk] = k / n
    fam = [out.get(("families", f)) for f in families]
    if fam and None not in fam:
        out[HEADLINE] = statistics.fmean(fam)   # type: ignore[arg-type]
    return out


def _quantile(xs: Sequence[float], q: float) -> float:
    """The `q` quantile of sorted `xs`, by linear interpolation."""
    at = (len(xs) - 1) * q
    lo = int(at)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (at - lo)


MIN_DOCUMENTS = 5     # below this many documents an entry has no interval
MAX_ABSENT = 0.05     # an entry absent from more than this share of the draws has no interval
MIN_RESAMPLES = 100


def _bounds(draws: list[float], resamples: int, documents: int, level: float
            ) -> tuple[float | None, float | None]:
    """The central `level` of the draws, or None for both when the entry has fewer than `MIN_DOCUMENTS`
    documents, or was absent (no tests, or for a gap, none in one system) from more than `MAX_ABSENT` of
    the `resamples` draws: the draws that are left are then those where it was present, and say too little."""
    if documents < MIN_DOCUMENTS or len(draws) < (1 - MAX_ABSENT) * resamples:
        return None, None
    draws.sort()
    tail = (1 - level) / 2
    return _quantile(draws, tail), _quantile(draws, 1 - tail)


def _check(resamples: int, level: float) -> None:
    if isinstance(resamples, bool) or not isinstance(resamples, int):
        raise ValueError(f"resamples must be an integer, not {resamples!r}")
    if resamples < MIN_RESAMPLES:
        raise ValueError(f"resamples must be at least {MIN_RESAMPLES}, not {resamples}; fewer draws give "
                         "bounds too rough to read")
    if not 0 < level < 1:
        raise ValueError(f"level must be between 0 and 1, not {level}")


def _method(resamples: int, seed: int, level: float) -> dict[str, Any]:
    return {"method": "cluster bootstrap over documents, percentile interval", "level": level,
            "resamples": resamples, "seed": seed, "min_documents": MIN_DOCUMENTS,
            "max_absent": MAX_ABSENT}


def intervals(pages: Iterable[Mapping[str, Any]], *, resamples: int = 1000, seed: int = 0,
              level: float = 0.95) -> dict[str, Any]:
    """The summary's headline (here `headline`), `families` and slices (`per_tag`, `per_suite`,
    `per_test_type`, `per_arg_kind`, `per_derivation`), each entry now `{"score", "low", "high", "tests",
    "documents", "draws"}`: its score and the central `level` of its scores over `resamples` draws of the
    documents (a cluster bootstrap, the same draws for every entry, so the headline and the families
    agree). `draws` is how many draws the entry was present in. `low` and `high` are None for an entry of
    fewer than 5 documents, or absent from more than 5% of the draws: with so few documents the draws say
    little, and a bound made from the draws that are left would look sure of a score it is not.
    `interval` says how it was made. Deterministic for a `seed`. A slice with no tests is left out. The
    headline is a mean over every family, so a draw missing a family is not one of its draws.

    Note: pages with the same `row.document` are one document; pages of one source under different
    document values are separate ones, and the interval says nothing of that dependence. A percentile
    interval on few documents is too narrow (about 0.88 coverage at 10 documents, 0.93 at 30, for a 95%
    interval); read a slice of few documents as rough."""
    _check(resamples, level)
    table = _table(pages)
    docs = _documents(table)
    sparse = _sparse(table, {d: i for i, d in enumerate(docs)})
    fams = _keys("families", table)
    point = _scores(sparse, [1] * len(docs), fams)
    draws: dict[tuple[str, str], list[float]] = {sk: [] for sk in point}
    rng = random.Random(seed)
    for _ in range(resamples if docs else 0):
        for sk, v in _scores(sparse, _weights(rng, len(docs)), fams).items():
            draws[sk].append(v)

    def entry(sk: tuple[str, str]) -> dict[str, Any]:
        if sk == HEADLINE:
            ts = [t for k in fams for _, t, _ in sparse[("families", k)]]
            n, d = sum(ts), len({i for k in fams for i, _, _ in sparse[("families", k)]})
        else:
            n, d = sum(t for _, t, _ in sparse[sk]), len({i for i, _, _ in sparse[sk]})
        low, high = _bounds(draws[sk], resamples, d, level)
        return {"score": point[sk], "low": low, "high": high, "tests": n, "documents": d,
                "draws": len(draws[sk])}

    out: dict[str, Any] = {"headline": entry(HEADLINE) if HEADLINE in point else None}
    for s in SLICES:
        out[s] = {k: entry((s, k)) for k in _keys(s, table) if (s, k) in point}
    return out | {"interval": _method(resamples, seed, level)}


def paired(pages_a: Iterable[Mapping[str, Any]], pages_b: Iterable[Mapping[str, Any]], *,
           resamples: int = 1000, seed: int = 0, level: float = 0.95) -> dict[str, Any]:
    """Two systems' score lines compared over the documents both have: for the headline (`headline`), each
    family and each slice, `{"a", "b", "gap", "low", "high", "documents", "draws", "excludes_zero"}`. `gap`
    is a's score minus b's; `low` and `high` are the central `level` of the gap over `resamples` draws of
    the paired documents, one draw for both systems; `excludes_zero` is whether that interval leaves out 0.
    An interval is None (and `excludes_zero` False) as in `intervals`: for an entry of fewer than 5
    documents in either system, or one absent from either system in more than 5% of the draws. `draws`
    counts the draws the gap was present in; `documents` is the union of the two systems' documents for the
    entry, within the paired set.

    The headline is the mean over `headline_families`, those both systems have tests for on the paired
    documents, and a draw missing one of them is not one of its draws. `a` and `b` are scores over the
    paired documents only, so they need not equal each run's own summary.

    `documents_paired` counts the documents in both; `documents_unpaired` how many each system has that the
    other lacks, and they are left out. `entries_unpaired` counts, per side, the entries only that system
    has tests for on the paired documents, which get no gap. `documents_mismatched` counts paired documents
    whose number of tests differs between the systems (usually two different datasets or manifests). Raises
    ValueError when no document is in both.

    Note: `excludes_zero` is a statement about this dataset's documents, not a significance test across
    several slices; with many slices some will exclude 0 by chance, and the interval is optimistic on
    few documents."""
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
    ones = [1] * len(both)
    present = lambda sp: {k for (s, k), v in sp.items() if s == "families" and v}
    fams = [k for k in _keys("families", ta) if k in present(sa) and k in present(sb)]
    pa, pb = _scores(sa, ones, fams), _scores(sb, ones, fams)
    keys = [sk for sk in pa if sk in pb]
    draws: dict[tuple[str, str], list[float]] = {sk: [] for sk in keys}
    rng = random.Random(seed)
    for _ in range(resamples):
        m = _weights(rng, len(both))
        va, vb = _scores(sa, m, fams), _scores(sb, m, fams)
        for sk in keys:
            if sk in va and sk in vb:
                draws[sk].append(va[sk] - vb[sk])

    def docs_of(sp: Mapping[tuple[str, str], Any], sk: tuple[str, str]) -> set[int]:
        if sk == HEADLINE:
            return {i for k in fams for i, _, _ in sp.get(("families", k), ())}
        return {i for i, _, _ in sp.get(sk, ())}

    def entry(sk: tuple[str, str]) -> dict[str, Any]:
        da_, db_ = docs_of(sa, sk), docs_of(sb, sk)
        low, high = _bounds(draws[sk], resamples, min(len(da_), len(db_)), level)
        return {"a": pa[sk], "b": pb[sk], "gap": pa[sk] - pb[sk], "low": low, "high": high,
                "documents": len(da_ | db_), "draws": len(draws[sk]),
                "excludes_zero": low is not None and high is not None and (low > 0 or high < 0)}

    def total(sp: Mapping[tuple[str, str], Any]) -> dict[int, int]:
        out: dict[int, int] = collections.Counter()
        for (s, _), ts in sp.items():
            if s == "families":
                for i, t, _ in ts:
                    out[i] += t
        return out

    ca, cb = total(sa), total(sb)
    out: dict[str, Any] = {"headline": entry(HEADLINE) if HEADLINE in keys else None,
                           "headline_families": fams}
    for s in SLICES:
        out[s] = {k: entry((s, k)) for k in _keys(s, ta) if (s, k) in draws}
    return out | {"documents_paired": len(both),
                  "documents_unpaired": {"a": len(da - db), "b": len(db - da)},
                  "documents_mismatched": sum(ca[i] != cb[i] for i in range(len(both))),
                  "entries_unpaired": {"a": sum(sk not in pb for sk in pa if sk != HEADLINE),
                                       "b": sum(sk not in pa for sk in pb if sk != HEADLINE)},
                  "interval": _method(resamples, seed, level)}
