"""A dataset's unit tests: each page's tests read and checked (`gold`, `check`), each page's verdicts as test
lines (`lines`), test lines summarized (`summarize`), and `UnitTests`, the scorer as omni-bench-core grades a
run.
"""
from __future__ import annotations

import collections
import dataclasses
import statistics
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, ClassVar

from omni_bench_core import scorer

from omni_parse_bench import data, errors, vocab

from . import compare
from . import tests as _tests
from .compare import Verdict

Line = Mapping[str, Any]   # a test line (`lines`)
HEADLINE = "the mean of the families' scores"


@dataclasses.dataclass(frozen=True)
class UnitTests(scorer.Scorer[data.Page, tuple[_tests.Test, ...], Mapping[str, Any]]):
    """Omni Parse Bench's scorer: each page's yes/no tests, run against its outputs.

    Every test of a page is graded. A test on an output the system didn't produce (one it can't, or one it
    failed to give) fails as "no <output> output", so a system that produces html alone scores 0 on the layout
    family, and its text and tables families say how it reads.

    The summary holds the headline and `families`: each family's score (its tests' pass rate), tests and
    source documents (`summarize`), in the order text, tables, layout. The headline is the mean of the
    families' scores over the scored pages; the core then multiplies it by coverage, so a page whose call
    failed counts as 0, and a run where every page failed has headline 0.

    Each page's line in scores.jsonl holds its counts: `tests`, `passed`, and `per_family`, each family's
    `tests` and `passed`. Each test's verdict is in the page's details (`details/<page_id>.jsonl`), as a test
    line (`lines`): `page_id`, `suite`, `document`, `test_id`, `test_type`, `output_type`, `derivation`,
    `tags`, `result` and `why`. So `summarize` reads details lines, and any other breakdown (by tag, test
    type, suite or derivation) is `summarize` of a slice of them."""

    name: ClassVar[str] = "unit_tests"

    def gold(self, row: data.Page) -> tuple[_tests.Test, ...]:
        """The page's tests."""
        return gold(row)

    def prediction(self, output: Any) -> Mapping[str, Any]:
        """The page's outputs. A prediction that isn't an object of outputs is the system's failure: the
        page counts 0. An output of the wrong shape inside it fails only its own tests
        (`views.MalformedOutput`)."""
        if not isinstance(output, dict):
            raise errors.SystemFailed(f"the prediction is a JSON {type(output).__name__}, not an object "
                                           "of outputs")
        return output

    def score(self, pred: Mapping[str, Any], tests: Sequence[_tests.Test]) -> scorer.Score:
        vs = compare.score(pred, tests)
        by_id = {t.id: t for t in tests}
        per_family: dict[str, dict[str, int]] = {}
        for v in vs:
            c = per_family.setdefault(vocab.FAMILIES[by_id[v.id].test_type], {"tests": 0, "passed": 0})
            c["tests"] += 1
            c["passed"] += v.result == "pass"
        result = {"tests": len(vs), "passed": sum(v.result == "pass" for v in vs), "per_family": per_family}
        return scorer.Score(result, [{"test_id": v.id, "test_type": (t := by_id[v.id]).test_type,
                                      "output_type": t.output_type, "derivation": t.derivation,
                                      "tags": list(t.tags), "result": v.result, "why": v.why} for v in vs])

    def score_all(self, rows: Sequence[data.Page], preds: Sequence[Mapping[str, Any]],
                  golds: Sequence[Sequence[_tests.Test]]) -> list[scorer.Score]:
        """The core's, with each detail line on its page (`page_id`, `suite`, `document`), so a page's details
        are test lines that `summarize` reads."""
        out = []
        for r, x in zip(rows, super().score_all(rows, preds, golds), strict=True):
            on = {"page_id": r.page_id, "suite": r.suite, "document": r.document}
            out.append(x if x.details is None else x._replace(details=[on | d for d in x.details]))
        return out

    def row_fields(self, row: data.Page) -> dict[str, Any]:
        return {"document": row.document}

    def summarize(self, lines: Sequence[Line]) -> dict[str, Any]:
        """The headline and `families`, over the scored pages' counts (the core gives only those)."""
        s = _summary((f, x["row"]["document"], c["passed"], c["tests"])
                     for x in lines for f, c in x["per_family"].items())
        return {"headline": s["headline"], "headline_is": HEADLINE, "families": s["families"]}

    def check_gold(self, rows: Sequence[data.Page]) -> None:
        """Every page's tests read and checked (`check`), before any call."""
        check(rows)


def gold(page: data.Page) -> tuple[_tests.Test, ...]:
    """The page's tests, from its gold file (`page.gt_path`) alone; refuses a page whose manifest `outputs`
    disagree with what its tests read."""
    ts = _tests.read(page.gt_path)
    if not ts:
        raise ValueError(f"page {page.page_id!r}: its gold {page.gt_path} has no tests; give it tests, "
                        "or drop the page from the manifest")
    if frozenset(page.outputs) != _tests.wants(ts):
        raise ValueError(f"page {page.page_id!r}: the manifest says it is asked for "
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
        raise ValueError(f"test ids used more than once, across the dataset: "
                         f"{errors.counted(len(twice), 'id')}, e.g. {twice[:3]}; each test's id is "
                         "unique in its dataset")
    if empty := sorted({p.page_id for p in pages} - {t.page_id for t in every}):
        raise ValueError(f"pages with no tests: {errors.counted(len(empty), 'page')}, e.g. "
                         f"{empty[:3]}; remove them or give them tests")
    return every


def lines(verdicts: Iterable[Verdict], tests: Iterable[_tests.Test], page: data.Page) -> list[dict[str, Any]]:
    """Each verdict of `page` as a test line: the page it's on, then what its test is (looked up by id in
    `tests`), then the verdict.

    A test line is one test's verdict beside what the page and the test are: `page_id`, `suite`, `document`,
    `test_id`, `test_type`, `output_type`, `derivation`, `tags`, `result` and `why`. `summarize` reads any
    number of them, and a slice of them (one tag, one suite) is summarized the same way.
    """
    by_id = {t.id: t for t in tests}
    on = {"page_id": page.page_id, "suite": page.suite, "document": page.document}
    return [on | {"test_id": (t := by_id[v.id]).id, "test_type": t.test_type, "output_type": t.output_type,
                  "derivation": t.derivation, "tags": list(t.tags), "result": v.result, "why": v.why}
            for v in verdicts]


def summarize(lines: Iterable[Line]) -> dict[str, Any]:
    """The test lines (from `lines()`) summarized: the benchmark's summary of a run, on any set of tests.

    It holds `headline`, the mean of the families' scores, and `families`: each family's `score` (the share
    of its tests passed), `tests` and `documents` (how many source documents its tests are from). Scores are
    fractions from 0 to 1, and the headline is None when there are no tests.

    The headline is a mean over families, each family's score flat over its tests, so how many tests a family
    has never sets its weight. A document's tests pass or fail together (one misread table fails all its
    cells), so a score over a few documents says less than its test count suggests: `documents` says how
    many.
    """
    return _summary((vocab.FAMILIES[x["test_type"]], x["document"], int(x["result"] == "pass"), 1)
                    for x in lines)


def _summary(counts: Iterable[tuple[str, str, int, int]]) -> dict[str, Any]:
    """`headline` and `families` from (family, document, passed, tests) counts, the families in
    `vocab.FAMILY_ORDER`."""
    tests: collections.Counter[str] = collections.Counter()
    passed: collections.Counter[str] = collections.Counter()
    documents: dict[str, set[str]] = collections.defaultdict(set)
    for f, d, k, n in counts:
        tests[f] += n
        passed[f] += k
        documents[f].add(d)
    families = {f: {"score": passed[f] / n, "tests": n, "documents": len(documents[f])}
                for f in vocab.FAMILY_ORDER if (n := tests[f])}
    return {"headline": float(statistics.fmean(x["score"] for x in families.values())) if families else None,
            "families": families}
