"""Scoring: `score` gives one page's verdicts, `summarize` a run's scores.

    verdicts = metric.score(outputs, page_tests)        # outputs: {"html": "...", "blocks": [...]}
    summary = metric.summarize(verdicts, tests, pages)  # every page of a run at once

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

With the pages (`gold.Page`, by page id), each score gets its `documents` count: how many source
documents its tests are from. A document's tests pass or fail together (one misread table fails all
its cells; a page's image copy is the same page), so a score over a few documents says less than its
test count suggests.
"""
from __future__ import annotations

import collections
import statistics
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from typing import Any, Literal, NamedTuple

from omni_parse_bench import gold, runners, views, vocab

Result = Literal["pass", "fail", "unsupported", "error"]
UNSCORED = ("unsupported", "error")

VIEWS: dict[str, Callable[[Any], Any]] = {
    "html": views.html,
    "blocks": views.blocks,
}


class Verdict(NamedTuple):
    id: str
    result: Result
    why: str


def score(outputs: Mapping[str, Any], tests: Sequence[gold.Test],
          unsupported: Collection[str] = ()) -> list[Verdict]:
    """One verdict per test. `outputs` maps an output type to its value, or to None when it
    errored; `unsupported` lists the output types the provider declares it can't produce."""
    built: dict[str, Any] = {}   # output type -> its view, or the Verdict its tests all get
    out = []
    for t in tests:
        if t.output_type in unsupported:
            out.append(Verdict(t.id, "unsupported", f"the provider can't produce {t.output_type}"))
            continue
        if outputs.get(t.output_type) is None:
            out.append(Verdict(t.id, "fail", f"no {t.output_type} output"))
            continue
        if t.output_type not in built:
            built[t.output_type] = _view(t.output_type, outputs[t.output_type])
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


def summarize(verdicts: Iterable[Verdict], tests: Iterable[gold.Test],
              pages: Iterable[gold.Page] | None = None) -> dict[str, Any]:
    """`headline` (see `headline`), then per output type: `score`, the test counts (`tests` scored,
    `unsupported`, `errors`), `per_test_type` and `per_tag` (each `{score, tests, pages}`), and, with
    `pages` (the tests' pages, as `gold.load` gives them), `documents` beside each score; then `per_suite`
    (with `pages`) and `per_derivation`. Scores are fractions from 0 to 1. An output type with no scored
    tests is left out."""
    tests = list(tests)
    pages = None if pages is None else {p.page_id: p for p in pages}
    by_id = {t.id: t for t in tests}
    vs = list(verdicts)
    scored = [(by_id[v.id], v.result == "pass") for v in vs if v.result not in UNSCORED]
    summary: dict[str, Any] = {"headline": headline(scored, [by_id[v.id] for v in vs], pages)}
    for output in vocab.OUTPUT_TYPES:
        xs = [(t, ok) for t, ok in scored if t.output_type == output]
        if not xs: continue
        groups: dict[str, list[tuple[gold.Test, bool]]] = {}
        for t, ok in xs:
            for g in t.tags: groups.setdefault(g, []).append((t, ok))
        per_tag = {g: {"score": _mean(ok for _, ok in ys), "tests": len(ys),
                       "pages": len({t.page_id for t, _ in ys}), **_documents(ys, pages)}
                   for g, ys in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))}
        count = collections.Counter(v.result for v in vs if by_id[v.id].output_type == output)
        summary[output] = {
            "score": _mean(ok for _, ok in xs),
            "tests": len(xs),
            "unsupported": count["unsupported"],
            "errors": count["error"],
            **_documents(xs, pages),
            "per_test_type": _means(xs, lambda t: t.test_type, order=list(runners.TYPES)),
            "per_tag": per_tag,
        }
    if pages is not None:
        summary["per_suite"] = _means(scored, lambda t: pages[t.page_id].suite)
    summary["per_derivation"] = _means(scored, lambda t: t.derivation, order=list(vocab.DERIVATIONS))
    return summary


def headline(scored: Sequence[tuple[gold.Test, bool]], graded: Sequence[gold.Test],
             pages: Mapping[str, gold.Page] | None = None) -> dict[str, Any]:
    """The mean of the families' scores, each family's flat over its scored tests, over the families
    the graded tests are in; with `pages`, the documents each family's tests are from. `score` is None
    when a family has no scored test (every one unsupported or an error), since a mean over fewer
    families isn't the same number; `families` says which."""
    sizes = collections.Counter(vocab.FAMILIES[t.test_type] for t in graded)
    by = collections.defaultdict(list)
    for t, ok in scored: by[vocab.FAMILIES[t.test_type]].append((t, ok))
    families = {f: {"score": _mean(ok for _, ok in by[f]) if by[f] else None, "tests": len(by[f]),
                    **_documents(by[f], pages)}
                for f, _ in sorted(sizes.items(), key=lambda kv: -kv[1])}
    complete = bool(families) and all(x["score"] is not None for x in families.values())
    out = {"score": _mean(x["score"] for x in families.values()) if complete else None,
           "families": families}
    return out | _documents(scored, pages)


def _documents(xs: Sequence[tuple[gold.Test, bool]], pages: Mapping[str, gold.Page] | None) -> dict[str, int]:
    """`{documents: n}`, the source documents the tests are from; {} without the pages."""
    return {} if pages is None else {"documents": len({pages[t.page_id].document for t, _ in xs})}


def _mean(xs: Iterable[bool | float]) -> float:
    """The mean as a float: `statistics.mean` of bools is an int when they all agree."""
    return float(statistics.mean(xs))


def _means(xs: Sequence[tuple[gold.Test, bool]], key: Callable[[gold.Test], str],
           order: Sequence[str] | None = None) -> dict[str, float]:
    """The pass rate per key, in `order` when given, else sorted."""
    groups: dict[str, list[bool]] = {}
    for t, ok in xs:
        groups.setdefault(key(t), []).append(ok)
    keys = [k for k in order if k in groups] if order else sorted(groups)
    return {k: _mean(groups[k]) for k in keys}
