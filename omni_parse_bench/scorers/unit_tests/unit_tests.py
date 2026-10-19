"""A dataset's unit tests: each page's tests read and checked (`gold`, `check`), each page's verdicts as test
lines (`lines`), every test line summarized (`summarize`), and `UnitTests`, the scorer as omni-bench-core
grades a run.
"""
from __future__ import annotations

import collections
import dataclasses
import statistics
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any, ClassVar

from omni_bench_core import scorer

from omni_parse_bench import data, errors, vocab

from . import compare, runners
from . import tests as _tests
from .compare import Verdict

Line = Mapping[str, Any]   # a test line (`lines`)


@dataclasses.dataclass(frozen=True)
class UnitTests(scorer.Scorer[data.Page, tuple[_tests.Test, ...], Mapping[str, Any]]):
    """Omni Parse Bench's scorer: each page's yes/no tests, run against its outputs.

    `outputs` chooses which outputs are graded: only the tests that read one of them are run. Grade a system
    that can't produce layout blocks with `UnitTests(outputs=("html",))`, and compare it with others graded
    the same way.

    Each page's line holds its counts (`tests`, `passed`) and its verdicts without their reasons
    (`verdicts`), so `summarize` can group the tests by family, type, tag and derivation. The reasons are the
    page's details. A page whose call failed counts as 0 by the core's rule: the headline is the families'
    score over the graded pages, times the share of pages graded."""

    name: ClassVar[str] = "unit_tests"
    outputs: tuple[str, ...] = vocab.OUTPUT_TYPES

    def gold(self, row: data.Page) -> tuple[_tests.Test, ...]:
        """The page's tests that read one of `outputs`."""
        return tuple(t for t in gold(row) if t.output_type in self.outputs)

    def prediction(self, output: Any) -> Mapping[str, Any]:
        if not isinstance(output, dict):
            raise ValueError(f"the prediction is a JSON {type(output).__name__}, not an object of outputs")
        return output

    def score(self, pred: Mapping[str, Any], tests: Sequence[_tests.Test]) -> scorer.Score:
        vs = compare.score(pred, tests)
        by_id = {t.id: t for t in tests}
        verdicts = [{"test_id": v.id, "test_type": (t := by_id[v.id]).test_type, "output_type": t.output_type,
                     "derivation": t.derivation, "tags": list(t.tags), "result": v.result} for v in vs]
        result = {"tests": len(vs), "passed": sum(v.result == "pass" for v in vs), "verdicts": verdicts}
        return scorer.Score(result, [{"test_id": v.id, "result": v.result, "why": v.why} for v in vs])

    def row_fields(self, row: data.Page) -> dict[str, Any]:
        return {"document": row.document}

    def summarize(self, lines: Sequence[Line]) -> dict[str, Any]:
        """`summarize` of the test lines of every scored page."""
        return summarize({"page_id": x["id"], "suite": x["suite"], "document": x["row"]["document"], **v}
                         for x in scorer.scored(lines) for v in x["verdicts"])

    def check_gold(self, rows: Sequence[data.Page]) -> None:
        """Every page's tests read and checked (`check`), before any call."""
        check(rows)


def gold(page: data.Page) -> tuple[_tests.Test, ...]:
    """The page's tests, from its gold file (`page.gt_path`) alone; refuses a page whose manifest `outputs`
    disagree with what its tests read."""
    ts = _tests.read(page.gt_path)
    if not ts:
        raise _tests.GoldError(f"page {page.page_id!r}: its gold {page.gt_path} has no tests; give it tests, "
                              "or drop the page from the manifest")
    if frozenset(page.outputs) != _tests.wants(ts):
        raise _tests.GoldError(f"page {page.page_id!r}: the manifest says it is asked for "
                              f"{list(page.outputs)}, but its tests read {sorted(_tests.wants(ts))}; the "
                              "manifest is out of step with the gold")
    return ts


def check(pages: Sequence[data.Page]) -> tuple[_tests.Test, ...]:
    """Every test of `pages` (a manifest's, `data.read_manifest`), each page's checked (`gold`), and what
    no single page can show: a test id used twice, and a page with no tests. What publishing a dataset
    checks, before any call of a benchmark; grading needs none of it.

    Note: a gold file no manifest names is not refused here: a dataset may hold several manifests (a
    sample beside the whole), each naming some of the gold files, so one manifest can't say a file is
    stray."""
    every = tuple(t for p in pages for t in gold(p))
    if twice := [i for i, n in collections.Counter(t.id for t in every).items() if n > 1]:
        raise _tests.GoldError(f"test ids used more than once, across the dataset: "
                               f"{errors.counted(len(twice), 'id')}, e.g. {twice[:3]}; each test's id is "
                               "unique in its dataset")
    if empty := sorted({p.page_id for p in pages} - {t.page_id for t in every}):
        raise _tests.GoldError(f"pages with no tests: {errors.counted(len(empty), 'page')}, e.g. "
                               f"{empty[:3]}; remove them or give them tests")
    return every


def lines(verdicts: Iterable[Verdict], tests: Iterable[_tests.Test], page: data.Page) -> list[dict[str, Any]]:
    """Each verdict of `page` as a score line: the page it's on, then what its test is (looked up by id in
    `tests`), then the verdict.

    A test line is one test's verdict beside what the page and the test are: `page_id`, `suite`, `document`,
    `test_id`, `test_type`, `output_type`, `derivation`, `tags`, `result` and `why`. `summarize` reads any
    number of them.
    """
    by_id = {t.id: t for t in tests}
    on = {"page_id": page.page_id, "suite": page.suite, "document": page.document}
    return [on | {"test_id": (t := by_id[v.id]).id, "test_type": t.test_type, "output_type": t.output_type,
                  "derivation": t.derivation, "tags": list(t.tags), "result": v.result, "why": v.why}
            for v in verdicts]


def summarize(lines: Iterable[Line]) -> dict[str, Any]:
    """The test lines (from `lines()`) summarized. It holds:

    - `headline`, the one number to compare runs by (see `_families`), beside `families` and `documents`;
    - per output type the lines have: `score`, `tests`, `documents`, `per_test_type` and `per_tag` (each
      `{score, tests, pages, documents}`); and
    - `per_suite`, each suite's `headline` and `score` (its pass rate), and `per_derivation`.

    Scores are fractions from 0 to 1.

    An output type's score is the mean over its tests. Beside it, `per_test_type` scores each structure a test
    checks (presence, order, a table cell), and `per_tag` each kind of content (a table, math, handwriting, a
    script, a language), with its test and page counts. A test counts toward every tag it has, so the tags
    overlap and their scores don't average to the score: a reader who wants a mix of tags (table and degraded)
    selects those tests and scores them, never combines rows.

    Each score gets its `documents` count: how many source documents its tests are from. A document's tests
    pass or fail together (one misread table fails all its cells; a page's image copy is the same page), so a
    score over a few documents says less than its test count suggests.
    """
    every = list(lines)
    scored = [(x, x["result"] == "pass") for x in every]
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
        summary[output] = {
            "score": _mean(ok for _, ok in ys),
            "tests": len(ys),
            "documents": _documents(ys),
            "per_test_type": _means(ys, lambda x: x["test_type"], order=list(runners.TYPES)),
            "per_tag": per_tag,
        }
    by_suite: dict[str, list[Line]] = collections.defaultdict(list)
    for x in every: by_suite[x["suite"]].append(x)
    summary["per_suite"] = {k: _suite(xs) for k, xs in sorted(by_suite.items())}
    summary["per_derivation"] = _means(scored, lambda x: x["derivation"], order=list(vocab.DERIVATIONS))
    return summary


def _families(scored: Sequence[tuple[Line, bool]], graded: Sequence[Line]) -> dict[str, Any]:
    """`headline`, the mean of the families' scores, each family's flat over its scored tests, over the
    families the graded tests are in; `families`, each one's score, tests and documents; and `documents`,
    the source documents the scored tests are from. `headline` is None when a family has no scored test,
    since a mean over fewer families isn't the same number."""
    sizes = collections.Counter(vocab.FAMILIES[x["test_type"]] for x in graded)
    by = collections.defaultdict(list)
    for x, ok in scored: by[vocab.FAMILIES[x["test_type"]]].append((x, ok))
    families = {f: {"score": _mean(ok for _, ok in by[f]) if by[f] else None, "tests": len(by[f]),
                    "documents": _documents(by[f])}
                for f, _ in sorted(sizes.items(), key=lambda kv: -kv[1])}
    complete = bool(families) and all(x["score"] is not None for x in families.values())
    return {"headline": _mean(x["score"] for x in families.values()) if complete else None,
            "families": families, "documents": _documents(scored)}


def _suite(graded: Sequence[Line]) -> dict[str, Any]:
    """One suite's `headline` (`_families` over its lines) and `score`, its pass rate."""
    scored = [(x, x["result"] == "pass") for x in graded]
    return {"headline": _families(scored, graded)["headline"],
            "score": _mean(ok for _, ok in scored) if scored else None}


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
