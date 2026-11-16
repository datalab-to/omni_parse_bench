"""Uncertainty for the scorer's summary: an interval on each score, and a paired comparison of two systems.

A document's tests pass or fail together, so a score's uncertainty is that of a sample of documents, not of
tests. Both functions resample documents (a cluster bootstrap): they draw the dataset's documents with
replacement, the same draw for every slice (and, in `paired`, for both systems), and read each statistic
off the draw. The percentiles of those statistics are the interval.

They take score lines, as `scores.jsonl` holds them and as the summary reads them, and use the standard
library only. The summary itself is unchanged."""

from __future__ import annotations

import collections
import itertools
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


def _effective(counts: Iterable[int]) -> float:
    """How many equal-sized documents the per-document test `counts` are worth: their sum squared over the
    sum of their squares. It is the number of documents when the counts are equal, and falls as they skew;
    0 for no tests."""
    xs = list(counts)
    sq = sum(x * x for x in xs)
    return sum(xs) ** 2 / sq if sq else 0.0


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

    Note: scores are pooled over tests, so a document with many tests weighs more, and the draws of
    documents already reflect that. `documents` is a raw count; `effective_documents` is what the tests are
    worth as equal-sized documents. Pages with the same `row.document` are one document; pages of one
    source under different document values are separate ones, and the interval says nothing of that
    dependence. A percentile interval on few documents is too narrow (about 0.88 coverage at 10 documents,
    0.93 at 30, for a 95% interval); read a slice of few documents as rough."""
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
            per_doc: dict[int, int] = collections.Counter()
            for k in fams:
                for i, t, _ in sparse[("families", k)]:
                    per_doc[i] += t
        else:
            per_doc = collections.Counter()
            for i, t, _ in sparse[sk]:
                per_doc[i] += t
        n, d = sum(per_doc.values()), len(per_doc)
        low, high = _bounds(draws[sk], resamples, d, level)
        return {"score": point[sk], "low": low, "high": high, "tests": n, "documents": d,
                "effective_documents": round(_effective(per_doc.values()), 1), "draws": len(draws[sk])}

    out: dict[str, Any] = {"headline": entry(HEADLINE) if HEADLINE in point else None}
    for s in SLICES:
        out[s] = {k: entry((s, k)) for k in _keys(s, table) if (s, k) in point}
    return out | {"interval": _method(resamples, seed, level)}


def paired(pages_a: Iterable[Mapping[str, Any]], pages_b: Iterable[Mapping[str, Any]], *,
           resamples: int = 1000, seed: int = 0, level: float = 0.95) -> dict[str, Any]:
    """Two systems' score lines compared over the documents both have: for the headline (`headline`), each
    family and each slice, `{"a", "b", "gap", "low", "high", "documents", "effective_documents", "draws",
    "excludes_zero"}`. `gap`
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

    def counts_of(sp: Mapping[tuple[str, str], Any], sk: tuple[str, str]) -> dict[int, int]:
        out: dict[int, int] = collections.Counter()
        for key in ([("families", k) for k in fams] if sk == HEADLINE else [sk]):
            for i, t, _ in sp.get(key, ()):
                out[i] += t
        return out

    def entry(sk: tuple[str, str]) -> dict[str, Any]:
        da_, db_ = docs_of(sa, sk), docs_of(sb, sk)
        low, high = _bounds(draws[sk], resamples, min(len(da_), len(db_)), level)
        cnt = [(counts_of(sa, sk).get(i, 0) + counts_of(sb, sk).get(i, 0)) / 2 for i in da_ | db_]
        return {"a": pa[sk], "b": pb[sk], "gap": pa[sk] - pb[sk], "low": low, "high": high,
                "documents": len(da_ | db_), "effective_documents": round(_effective(cnt), 1),
                "draws": len(draws[sk]),
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


def _ranks(xs: Sequence[float]) -> list[float]:
    """The ranks of `xs`, from 1, a tie getting the average of the ranks it spans."""
    order = sorted(range(len(xs)), key=xs.__getitem__)
    out = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return out


def _spearman(x: Sequence[float], y: Sequence[float]) -> float | None:
    """Spearman's rank correlation (ties by average rank), or None when either side has no variance."""
    rx, ry = _ranks(x), _ranks(y)
    n = len(rx)
    mx, my = sum(rx) / n, sum(ry) / n
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    if not sxx or not syy:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True)) / (sxx * syy) ** 0.5


def _brown(r: float | None) -> float | None:
    """Spearman-Brown: the correlation of the two halves, stepped up to that of the whole, `2r / (1 + r)`.
    `r` is clipped to [-1, 1], -1 maps to -1 (the step is undefined there), and the result is clipped to
    [-1, 1]."""
    if r is None:
        return None
    r = max(-1.0, min(1.0, r))
    return -1.0 if r == -1 else max(-1.0, min(1.0, 2 * r / (1 + r)))


def _residuals(y: Sequence[float], x: Sequence[float]) -> list[float] | None:
    """What is left of `y` after an ordinary least squares fit on `x` (across the systems), or None when
    `x` has no variance."""
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((a - mx) ** 2 for a in x)
    if not sxx:
        return None
    slope = sum((a - mx) * (b - my) for a, b in zip(x, y, strict=True)) / sxx
    return [b - my - slope * (a - mx) for a, b in zip(x, y, strict=True)]


MIN_SYSTEMS = 5      # Spearman over fewer systems takes too few values to say anything
MAX_SKIPPED = 0.2     # a number undefined in more than this share of the splits is left out


def _halves(sizes: Sequence[int], splits: int, rng: random.Random, balanced: bool) -> list[list[int]]:
    """`splits` splits of the documents (their numbers of tests `sizes`) into halves, each a list of 1 for
    a document in half A and 0 for one in B. Balanced: the documents, ordered by their number of tests
    (ties at random), are cut into consecutive pairs and each pair is split between the halves at random,
    an odd one out going to a random half, so the halves hold nearly equal numbers of tests. Otherwise
    half A is `len(sizes) // 2` documents drawn at random."""
    n = len(sizes)
    out = []
    for _ in range(splits):
        order = list(range(n))
        rng.shuffle(order)
        flags = [0] * n
        if balanced:
            order.sort(key=sizes.__getitem__)
            for k in range(0, n - 1, 2):
                flags[order[k + rng.randrange(2)]] = 1
            if n % 2:
                flags[order[-1]] = rng.randrange(2)
        else:
            for i in order[:n // 2]:
                flags[i] = 1
        out.append(flags)
    return out


def reliability(runs: Mapping[str, Iterable[Mapping[str, Any]]], *, splits: int = 100, seed: int = 0,
                threshold: float = 0.7, min_documents: int = 10, balanced: bool = True) -> dict[str, Any]:
    """Whether each slice ranks the systems in `runs` (name: score lines) reproducibly, and whether it does
    so beyond what the rest of the benchmark does, by split-half over documents. For each of `splits`
    random halves of the documents (the same for every slice and system), each system's pass rate on the
    slice is taken in half A and in half B. `agreement` is the median over splits of the Spearman
    correlation (ties by average rank) between the two halves' rankings of the systems, stepped up with
    Spearman-Brown (`_brown`). `beyond_headline` fits, in each half, the systems' slice pass rates on their
    pass rates on the other tests (all tests outside the slice, in that half) by least squares across the
    systems, and takes the Spearman-Brown corrected correlation between half A's residuals and half B's:
    whether the slice ranks the systems by something the other tests don't. A slice is `flag`ged when
    `beyond_headline` is below `threshold`, and then `kind` is "noisy" if `agreement` is below it too (the
    slice can't rank these systems reproducibly at all), else "redundant" (it ranks them, but only as the
    other tests do).

    The slices are those of `intervals`: `{kind: {key: {"documents", "effective_documents", "tests",
    "agreement", "beyond_headline", "flag", "splits_used": {"agreement", "beyond_headline"}}}}`, with
    `kind` when flagged. An entry without a number says why in `reason`, and is not flagged: fewer than
    `min_documents` effective documents (`effective_documents`: the documents' worth when they hold unequal
    numbers of tests, see `_effective`; `documents` is the raw count), a test count that differs between
    systems, no tests outside the slice, or the number undefined in more than 20% of the splits. A split
    is undefined for `agreement` when a half has no slice tests or the systems' pass rates in it have no
    variance, and for `beyond_headline` also when a half has no tests outside the slice or the systems'
    pass rates on them have no variance; each number counts its own splits (`splits_used`). Raises
    ValueError for fewer than 5 systems, or no document all of them have.

    The halves are balanced by test count unless `balanced` is False (see `_halves`). Only documents every
    system has, with the same number of tests in each, are used; the others are
    counted in `documents_dropped`. The tests outside a slice are the page lines' `tests` and `passed` less
    the slice's, so a test with several tags counts under each of them, and the other tests of a tag slice
    leave out only the tests that carry that tag: co-tagged tests stay in them for the other tags.

    Note: the numbers depend on which systems are in `runs`: a few near-identical systems rank by noise,
    and so does a half of few documents. They say a slice can't rank these systems reproducibly, or only
    as the other tests do, on this dataset, not that its tests are wrong, and nothing here corrects for
    looking at many slices at once."""
    if isinstance(splits, bool) or not isinstance(splits, int) or splits < 10:
        raise ValueError(f"splits must be an integer of at least 10, not {splits!r}")
    if isinstance(min_documents, bool) or not isinstance(min_documents, int) or min_documents < 2:
        raise ValueError(f"min_documents must be an integer of at least 2, not {min_documents!r}")
    if len(runs) < MIN_SYSTEMS:
        raise ValueError(f"reliability needs at least {MIN_SYSTEMS} systems, got {len(runs)}: a rank "
                         "correlation over fewer takes too few values to say anything")
    lines = {name: list(pages) for name, pages in runs.items()}
    tables = {name: _table(pages) for name, pages in lines.items()}
    totals: dict[str, dict[str, list[int]]] = {}
    for name, pages in lines.items():
        t = totals[name] = {}
        for x in pages:
            c = t.setdefault(x["row"]["document"], [0, 0])
            c[0] += x["tests"]
            c[1] += x["passed"]
    names = list(runs)
    common = set.intersection(*(set(t) for t in totals.values()))
    if not common:
        raise ValueError("the systems have no document in common, so there is nothing to split; check "
                         "the runs are of the same dataset and manifest")
    every = {d for t in totals.values() for d in t}
    docs = sorted(d for d in common if len({t[d][0] for t in totals.values()}) == 1)
    if len(docs) < 2:
        raise ValueError("fewer than 2 documents have the same number of tests in every system")
    index = {d: i for i, d in enumerate(docs)}
    n_docs = len(docs)
    total_n = [totals[names[0]][d][0] for d in docs]
    total_p = {s: [totals[s][d][1] for d in docs] for s in names}

    in_a = _halves(total_n, splits, random.Random(seed), balanced)
    in_b = [[1 - f for f in flags] for flags in in_a]
    # Note: a half's totals per system, once per split, for the tests outside each slice.
    whole = [[(sum(itertools.compress(total_n, h)), [sum(itertools.compress(total_p[s], h)) for s in names])
              for h in (fa, fb)] for fa, fb in zip(in_a, in_b, strict=True)]

    out: dict[str, Any] = {}
    for kind in SLICES:
        present = {k for s in names for k in tables[s][kind]}
        order = _ORDER.get(kind, ())
        keys = [*(k for k in order if k in present), *sorted(present - set(order))]
        out[kind] = {}
        for key in keys:
            per = {s: {d: c for d, c in tables[s][kind].get(key, {}).items() if d in index and c[0]}
                   for s in names}
            idx = sorted({index[d] for p in per.values() for d in p})
            n = [per[names[0]].get(docs[i], (0, 0))[0] for i in idx]
            eff = round(_effective(n), 1)
            entry: dict[str, Any] = {"documents": len(idx), "effective_documents": eff, "tests": sum(n),
                                     "agreement": None,
                                     "beyond_headline": None, "flag": False,
                                     "splits_used": {"agreement": 0, "beyond_headline": 0}}
            reason = None
            if any([per[s].get(docs[i], (0, 0))[0] for i in idx] != n for s in names):
                reason = "the systems do not have the same tests for this slice"
            elif _effective(n) < min_documents:
                reason = (f"fewer than {min_documents} effective documents (it has {len(idx)} documents "
                          f"worth {eff})")
            elif sum(n) >= sum(total_n):
                reason = "no tests outside the slice"
            if reason:
                out[kind][key] = entry | {"reason": reason}
                continue
            passed = {s: [per[s].get(docs[i], (0, 0))[1] for i in idx] for s in names}
            agree: list[float] = []
            beyond: list[float] = []
            for (a, b), fa, fb in zip(whole, in_a, in_b, strict=True):
                rates, resid = [], []
                for (tn, tp), flags in ((a, fa), (b, fb)):
                    keep = [flags[i] for i in idx]
                    sn = sum(itertools.compress(n, keep))
                    if not sn:
                        rates = None
                        break
                    sp = [sum(itertools.compress(passed[s], keep)) for s in names]
                    rates.append([x / sn for x in sp])
                    resid.append(_residuals(rates[-1], [(tp[j] - x) / (tn - sn) for j, x in enumerate(sp)])
                                 if tn > sn else None)
                if rates is None:
                    continue
                if (r := _brown(_spearman(rates[0], rates[1]))) is not None:
                    agree.append(r)
                if None not in resid and (r := _brown(_spearman(resid[0], resid[1]))) is not None:
                    beyond.append(r)
            entry["splits_used"] = {"agreement": len(agree), "beyond_headline": len(beyond)}
            need = (1 - MAX_SKIPPED) * splits
            if len(agree) >= need:
                entry["agreement"] = statistics.median(agree)
            if len(beyond) >= need:
                entry["beyond_headline"] = statistics.median(beyond)
            late = [m for m in ("agreement", "beyond_headline") if entry[m] is None]
            if late:
                entry["reason"] = (f"{' and '.join(late)} undefined in more than 20% of the splits (no "
                                   "variance between the systems in a half)")
            if entry["beyond_headline"] is not None:
                entry["flag"] = entry["beyond_headline"] < threshold
                if entry["flag"]:
                    entry["kind"] = ("noisy" if entry["agreement"] is None or entry["agreement"] < threshold
                                     else "redundant")
            out[kind][key] = entry
    kinds = [e for k in SLICES for e in out[k].values()]
    return out | {"systems": len(names), "documents_used": n_docs, "documents_dropped": len(every) - n_docs,
                  "slices_with_numbers": sum(e["beyond_headline"] is not None for e in kinds),
                  "slices_without_numbers": sum(e["beyond_headline"] is None for e in kinds),
                  "reliability": {"method": "split-half over documents, Spearman-Brown corrected, median "
                                  "over splits; beyond_headline on residuals from the other tests' "
                                  "pass rate", "splits": splits, "seed": seed, "threshold": threshold,
                                  "min_documents": min_documents, "balanced": balanced}}
