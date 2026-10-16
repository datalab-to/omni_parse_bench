"""The unit-test scorer: yes/no tests on single pages. `gold` reads a page's tests, `score` gives its
verdicts, `lines` makes them score lines, and `summarize` gives many lines one summary.

    tests = unit_tests.gold(page)                      # a page of `data.read_manifest`
    verdicts = unit_tests.score(pred, tests)           # pred: {"html": "...", "blocks": [...]}
    xs = unit_tests.lines(verdicts, tests, page)       # each verdict beside its page and its test
    summary = unit_tests.summarize(xs)                 # any number of pages at once

The gold is unit tests: what one is, and how a gold file of them is read and checked, is `tests.py`;
how each test type is run is `runners.py`. A score line is one test's verdict beside what the page
and the test are: `page_id`, `suite`, `document`, `test_id`, `test_type`, `output_type`,
`derivation`, `tags`, `result` and `why`. It is what a run's scores.jsonl holds, so `summarize` reads
a scores.jsonl, or any part of one (one tag, one suite), as it is.

A verdict's result is one of four:

    pass          the test passed
    fail          it failed, or its output is missing or malformed (`views.MalformedOutput`)
    unsupported   the provider can't produce the test's output type
    error         grading raised on a well-formed output: a scorer bug, never the provider's fault

`unsupported` and `error` are left out of a score, so failing on a hard page can never raise one,
and a scorer bug never lowers one; `summarize` counts each per output type.

An output type's score is the mean over its tests. Beside it, `per_test_type` scores each structure
a test checks (presence, order, a table cell), and `per_tag` each kind of content (a table, math,
handwriting, a script, a language), with its test and page counts. A test counts toward every tag it
has, so the tags overlap and their scores don't average to the score: a reader who wants a mix of
tags (table and degraded) selects those tests and scores them, never combines rows.

Each score gets its `documents` count: how many source documents its tests are from. A document's
tests pass or fail together (one misread table fails all its cells; a page's image copy is the same
page), so a score over a few documents says less than its test count suggests.
"""
from __future__ import annotations

import collections
import statistics
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, Literal, NamedTuple

from omni_parse_bench import views, vocab

from . import runners
from . import tests as _tests
from .tests import GoldError, Test

__all__ = ["GoldError", "Test", "Verdict", "check", "gold", "lines", "runners", "score", "summarize", "tests"]

if TYPE_CHECKING:
    from omni_parse_bench import data

Result = Literal["pass", "fail", "unsupported", "error"]
Line = Mapping[str, Any]   # a score line (`lines`)
UNSCORED = ("unsupported", "error")

VIEWS: dict[str, Callable[[Any], Any]] = {
    "html": views.html,
    "blocks": views.blocks,
}


class Verdict(NamedTuple):
    id: str
    result: Result
    why: str


def gold(page: data.Page) -> tuple[_tests.Test, ...]:
    """The page's tests, from its gold file (`page.gt_path`) alone; refuses a page whose manifest `outputs`
    disagree with what its tests read."""
    ts = _tests.read(page.gt_path)
    if frozenset(page.outputs) != _tests.wants(ts):
        raise _tests.GoldError(f"page {page.page_id!r}: the manifest says it is asked for "
                              f"{list(page.outputs)}, but its tests read {sorted(_tests.wants(ts))}; the "
                              "manifest is out of step with the gold")
    return ts


def check(pages: Sequence[data.Page]) -> tuple[_tests.Test, ...]:
    """Every test of `pages` (a manifest's, `data.read_manifest`), each page's checked (`gold`), and what
    no single page can show: a test id used twice, and a page with no tests. What publishing a dataset
    checks, and `opb tests` writes; grading needs none of it.

    Note: a gold file no manifest names is not refused here: a dataset may hold several manifests (a
    sample beside the whole), each naming some of the gold files, so one manifest can't say a file is
    stray."""
    every = tuple(t for p in pages for t in gold(p))
    if twice := [i for i, n in collections.Counter(t.id for t in every).items() if n > 1]:
        raise _tests.GoldError(f"{len(twice)} test ids are used more than once, e.g. {twice[:3]}")
    if empty := sorted({p.page_id for p in pages} - {t.page_id for t in every}):
        raise _tests.GoldError(f"{len(empty)} pages have no tests, e.g. {empty[:3]}; remove them or give "
                               "them tests")
    return every


def score(pred: Mapping[str, Any], gold: Sequence[_tests.Test],
          unsupported: Collection[str] = ()) -> list[Verdict]:
    """One verdict per test of `gold`, the page's tests. `pred` maps an output type to its value, or to
    None when it errored; `unsupported` lists the output types the provider declares it can't produce."""
    if isinstance(unsupported, str) or (bad := sorted(set(unsupported) - set(vocab.OUTPUT_TYPES))):
        raise ValueError(f"unsupported is a collection of output types from {list(vocab.OUTPUT_TYPES)}, not "
                         f"{unsupported!r}" + ("" if isinstance(unsupported, str) else f" ({bad} aren't)"))
    built: dict[str, Any] = {}   # output type -> its view, or the Verdict its tests all get
    out = []
    for t in gold:
        if t.output_type in unsupported:
            out.append(Verdict(t.id, "unsupported", f"the provider can't produce {t.output_type}"))
            continue
        if pred.get(t.output_type) is None:
            out.append(Verdict(t.id, "fail", f"no {t.output_type} output"))
            continue
        if t.output_type not in built:
            built[t.output_type] = _view(t.output_type, pred[t.output_type])
        if isinstance(v := built[t.output_type], Verdict):
            out.append(v._replace(id=t.id))
            continue
        try:
            passed, why = runners.TYPES[t.test_type][1](t.params, v)
        except Exception as e:
            out.append(Verdict(t.id, "error", f"{type(e).__name__}: {e}"))
            continue
        out.append(Verdict(t.id, "pass" if passed else "fail", why))
    return out


def _view(output_type: str, value: Any) -> Any:
    """The output's view; or, when it can't be built, the verdict each of its tests gets: `fail` for
    an output of the wrong shape (the provider's fault), `error` when building it raised otherwise."""
    try:
        return VIEWS[output_type](value)
    except views.MalformedOutput as e:
        return Verdict("", "fail", f"malformed {output_type} output: {e}")
    except Exception as e:
        return Verdict("", "error", f"{type(e).__name__}: {e}")


def lines(verdicts: Iterable[Verdict], tests: Iterable[_tests.Test], page: data.Page) -> list[dict[str, Any]]:
    """Each verdict of `page` as a score line: the page it's on, then what its test is (looked up by id in
    `tests`), then the verdict."""
    by_id = {t.id: t for t in tests}
    on = {"page_id": page.page_id, "suite": page.suite, "document": page.document}
    return [on | {"test_id": (t := by_id[v.id]).id, "test_type": t.test_type, "output_type": t.output_type,
                  "derivation": t.derivation, "tags": list(t.tags), "result": v.result, "why": v.why}
            for v in verdicts]


def summarize(xs: Iterable[Line]) -> dict[str, Any]:
    """The score lines `xs` (from `lines`, or a scores.jsonl's) summarized: `headline`, the one number to
    compare runs by (see `_families`), beside `families` and `documents`; then per output type: `score`,
    the test counts (`tests` scored, `unsupported`, `errors`), `documents`, `per_test_type` and `per_tag`
    (each `{score, tests, pages, documents}`); then `per_suite` and `per_derivation`. Scores are
    fractions from 0 to 1. An output type with no scored tests is left out."""
    every = list(xs)
    scored = [(x, x["result"] == "pass") for x in every if x["result"] not in UNSCORED]
    summary: dict[str, Any] = _families(scored, every)
    for output in vocab.OUTPUT_TYPES:
        ys = [(x, ok) for x, ok in scored if x["output_type"] == output]
        if not ys: continue
        groups: dict[str, list[tuple[Line, bool]]] = {}
        for x, ok in ys:
            for g in x["tags"]: groups.setdefault(g, []).append((x, ok))
        per_tag = {g: {"score": _mean(ok for _, ok in zs), "tests": len(zs),
                       "pages": len({x["page_id"] for x, _ in zs}), "documents": _documents(zs)}
                   for g, zs in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))}
        count = collections.Counter(x["result"] for x in every if x["output_type"] == output)
        summary[output] = {
            "score": _mean(ok for _, ok in ys),
            "tests": len(ys),
            "unsupported": count["unsupported"],
            "errors": count["error"],
            "documents": _documents(ys),
            "per_test_type": _means(ys, lambda x: x["test_type"], order=list(runners.TYPES)),
            "per_tag": per_tag,
        }
    summary["per_suite"] = _means(scored, lambda x: x["suite"])
    summary["per_derivation"] = _means(scored, lambda x: x["derivation"], order=list(vocab.DERIVATIONS))
    return summary


def _families(scored: Sequence[tuple[Line, bool]], graded: Sequence[Line]) -> dict[str, Any]:
    """`headline`, the mean of the families' scores, each family's flat over its scored tests, over the
    families the graded tests are in; `families`, each one's score, tests and documents; and `documents`,
    the source documents the scored tests are from. `headline` is None when a family has no scored test
    (every one unsupported or an error), since a mean over fewer families isn't the same number."""
    sizes = collections.Counter(vocab.FAMILIES[x["test_type"]] for x in graded)
    by = collections.defaultdict(list)
    for x, ok in scored: by[vocab.FAMILIES[x["test_type"]]].append((x, ok))
    families = {f: {"score": _mean(ok for _, ok in by[f]) if by[f] else None, "tests": len(by[f]),
                    "documents": _documents(by[f])}
                for f, _ in sorted(sizes.items(), key=lambda kv: -kv[1])}
    complete = bool(families) and all(x["score"] is not None for x in families.values())
    return {"headline": _mean(x["score"] for x in families.values()) if complete else None,
            "families": families, "documents": _documents(scored)}


def _documents(xs: Sequence[tuple[Line, bool]]) -> int:
    """The source documents the lines are from."""
    return len({x["document"] for x, _ in xs})


def _mean(xs: Iterable[bool | float]) -> float:
    """The mean as a float: `statistics.mean` of bools is an int when they all agree."""
    return float(statistics.mean(xs))


def _means(xs: Sequence[tuple[Line, bool]], key: Callable[[Line], str],
           order: Sequence[str] | None = None) -> dict[str, float]:
    """The pass rate per key, in `order` when given, else sorted."""
    groups: dict[str, list[bool]] = {}
    for x, ok in xs:
        groups.setdefault(key(x), []).append(ok)
    keys = [k for k in order if k in groups] if order else sorted(groups)
    return {k: _mean(groups[k]) for k in keys}
