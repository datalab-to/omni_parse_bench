"""Scoring: `gold` reads a page's tests, `score` gives its verdicts, `summarize` a run's scores.

    page_tests = scorer.gold(page)                      # a page of `data.read_manifest`
    verdicts = scorer.score(outputs, page_tests)        # outputs: {"html": "...", "blocks": [...]}
    xs = scorer.lines(verdicts, page_tests)             # each verdict beside what its test is
    summary = scorer.summarize(xs, pages)               # every page of a run at once

A score line is one test's verdict beside what the test is: `page_id`, `test_id`, `test_type`,
`output_type`, `derivation`, `tags`, `result` and `why`. It is what a run's scores.jsonl holds, so
`summarize` reads a scores.jsonl, or any part of one (one tag, one suite), as it is.

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

With the pages (`data.Page`, by page id), each score gets its `documents` count: how many source
documents its tests are from. A document's tests pass or fail together (one misread table fails all
its cells; a page's image copy is the same page), so a score over a few documents says less than its
test count suggests.
"""
from __future__ import annotations

import collections
import statistics
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, NamedTuple

# Note: imported as `_gold`, since `gold` here is the function that reads a page's gold.
from omni_parse_bench import gold as _gold
from omni_parse_bench import runners, views, vocab

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


def gold(page: data.Page) -> tuple[_gold.Test, ...]:
    """The page's tests, from its gold file (`page.gt_path`) alone; refuses a page whose manifest `outputs`
    disagree with what its tests read."""
    ts = _gold.read(page.gt_path)
    if frozenset(page.outputs) != _gold.wants(ts):
        raise _gold.GoldError(f"page {page.page_id!r}: the manifest says it is asked for "
                              f"{list(page.outputs)}, but its tests read {sorted(_gold.wants(ts))}; the "
                              "manifest is out of step with the gold")
    return ts


def check(pages: Sequence[data.Page]) -> tuple[_gold.Test, ...]:
    """Every test of `pages` (a dataset's, `data.read_manifest`), each page's checked (`gold`), and the
    dataset as a whole: a gold file with no page, a test id used twice, and a page with no tests are
    refused. What publishing a dataset checks, and `opb tests` writes; grading needs none of it."""
    named = {Path(p.gt_path).name for p in pages}
    folders = {Path(p.gt_path).parent for p in pages}
    if stray := sorted(f.name for d in folders for f in d.glob("*.json") if f.name not in named):
        raise _gold.GoldError(f"{len(stray)} gold files have no manifest row, e.g. {stray[:3]}")
    every = tuple(t for p in pages for t in gold(p))
    if twice := [i for i, n in collections.Counter(t.id for t in every).items() if n > 1]:
        raise _gold.GoldError(f"{len(twice)} test ids are used more than once, e.g. {twice[:3]}")
    if empty := sorted({p.page_id for p in pages} - {t.page_id for t in every}):
        raise _gold.GoldError(f"{len(empty)} pages have no tests, e.g. {empty[:3]}; remove them or give "
                              "them tests")
    return every


def score(outputs: Mapping[str, Any], tests: Sequence[_gold.Test],
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


def lines(verdicts: Iterable[Verdict], tests: Iterable[_gold.Test]) -> list[dict[str, Any]]:
    """Each verdict as a score line: beside what its test is, the test looked up by id in `tests`."""
    by_id = {t.id: t for t in tests}
    return [{"page_id": (t := by_id[v.id]).page_id, "test_id": t.id, "test_type": t.test_type,
             "output_type": t.output_type, "derivation": t.derivation, "tags": list(t.tags),
             "result": v.result, "why": v.why}
            for v in verdicts]


def summarize(xs: Iterable[Line], pages: Iterable[data.Page] | None = None) -> dict[str, Any]:
    """The score lines `xs` (from `lines`, or a scores.jsonl's) summarized: `headline` (see `headline`),
    then per output type: `score`, the test counts (`tests` scored, `unsupported`, `errors`),
    `per_test_type` and `per_tag` (each `{score, tests, pages}`), and, with `pages` (the tests' pages, as
    `data.read_manifest` gives them), `documents` beside each score; then `per_suite` (with `pages`) and
    `per_derivation`. Scores are fractions from 0 to 1. An output type with no scored
    tests is left out."""
    pages = None if pages is None else {p.page_id: p for p in pages}
    every = list(xs)
    scored = [(x, x["result"] == "pass") for x in every if x["result"] not in UNSCORED]
    summary: dict[str, Any] = {"headline": headline(scored, every, pages)}
    for output in vocab.OUTPUT_TYPES:
        ys = [(x, ok) for x, ok in scored if x["output_type"] == output]
        if not ys: continue
        groups: dict[str, list[tuple[Line, bool]]] = {}
        for x, ok in ys:
            for g in x["tags"]: groups.setdefault(g, []).append((x, ok))
        per_tag = {g: {"score": _mean(ok for _, ok in zs), "tests": len(zs),
                       "pages": len({x["page_id"] for x, _ in zs}), **_documents(zs, pages)}
                   for g, zs in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))}
        count = collections.Counter(x["result"] for x in every if x["output_type"] == output)
        summary[output] = {
            "score": _mean(ok for _, ok in ys),
            "tests": len(ys),
            "unsupported": count["unsupported"],
            "errors": count["error"],
            **_documents(ys, pages),
            "per_test_type": _means(ys, lambda x: x["test_type"], order=list(runners.TYPES)),
            "per_tag": per_tag,
        }
    if pages is not None:
        summary["per_suite"] = _means(scored, lambda x: pages[x["page_id"]].suite)
    summary["per_derivation"] = _means(scored, lambda x: x["derivation"], order=list(vocab.DERIVATIONS))
    return summary


def headline(scored: Sequence[tuple[Line, bool]], graded: Sequence[Line],
             pages: Mapping[str, data.Page] | None = None) -> dict[str, Any]:
    """The mean of the families' scores, each family's flat over its scored tests, over the families
    the graded tests are in; with `pages`, the documents each family's tests are from. `score` is None
    when a family has no scored test (every one unsupported or an error), since a mean over fewer
    families isn't the same number; `families` says which."""
    sizes = collections.Counter(vocab.FAMILIES[x["test_type"]] for x in graded)
    by = collections.defaultdict(list)
    for x, ok in scored: by[vocab.FAMILIES[x["test_type"]]].append((x, ok))
    families = {f: {"score": _mean(ok for _, ok in by[f]) if by[f] else None, "tests": len(by[f]),
                    **_documents(by[f], pages)}
                for f, _ in sorted(sizes.items(), key=lambda kv: -kv[1])}
    complete = bool(families) and all(x["score"] is not None for x in families.values())
    out = {"score": _mean(x["score"] for x in families.values()) if complete else None,
           "families": families}
    return out | _documents(scored, pages)


def _documents(xs: Sequence[tuple[Line, bool]], pages: Mapping[str, data.Page] | None) -> dict[str, int]:
    """`{documents: n}`, the source documents the tests are from; {} without the pages."""
    return {} if pages is None else {"documents": len({pages[x["page_id"]].document for x, _ in xs})}


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
