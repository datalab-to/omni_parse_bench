"""A dataset's unit tests:

- `UnitTests`: the scorer a run is graded with;
- `gold` and `check`: each page's tests, read and checked;
- `lines`: a page's verdicts as test lines; and
- `summarize`: test lines as one summary.
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
    """Omni Parse Bench's scorer: each page's yes/no tests, run against its outputs. A test on an output the
    system didn't produce fails as "no <output> output", so a system with html alone scores 0 on layout.

    - A page's line in scores.jsonl holds `tests`, `passed` and `per_family` (each family's `tests` and
      `passed`);
    - its details (`details/<page_id>.jsonl`) hold one test line per test (`lines`); and
    - the summary is `summarize` over every page, a failed one with all its tests failed (`score_failure`): the
      families in the order text, tables, layout, and their mean as the headline. Any other breakdown (by tag,
      test type, suite or derivation) is `summarize` of a slice of the details."""

    name: ClassVar[str] = "unit_tests"

    def gold(self, row: data.Page) -> tuple[_tests.Test, ...]:
        """The page's tests."""
        return gold(row)

    def prediction(self, output: Any) -> Mapping[str, Any]:
        """The page's outputs: the one page of the prediction's `pages`, as a row is one page. A prediction
        that isn't `{"pages": [an object of outputs]}` is the system's failure: the page counts 0. An output
        of the wrong shape inside it fails only its own tests (`views.MalformedOutput`)."""
        pages = output.get("pages") if isinstance(output, dict) else None
        if not (isinstance(pages, list) and len(pages) == 1 and isinstance(pages[0], dict)):
            got = f"{len(pages)} pages" if isinstance(pages, list) else f"a JSON {type(output).__name__}"
            raise errors.SystemFailed(f"the prediction is {got}, not {{\"pages\": [the page's outputs]}}: "
                                      "a row is one page")
        return pages[0]

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

    def score_failure(self, tests: Sequence[_tests.Test]) -> scorer.Score:
        """A failed page: the score of a prediction with no outputs, so every test fails and the page costs
        its tests, not a page's share of the headline."""
        return self.score({}, tests)

    def detail_fields(self, row: data.Page) -> dict[str, Any]:
        """Each detail line's page (`page_id`, `suite`, `document`), so a page's details are test lines that
        `summarize` reads."""
        return {"page_id": row.page_id, "suite": row.suite, "document": row.document}

    def row_fields(self, row: data.Page) -> dict[str, Any]:
        return {"document": row.document}

    def summarize(self, lines: Sequence[Line]) -> dict[str, Any]:
        """The headline and `families`, over every page's counts, a failed page's from `score_failure`."""
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
    """Every test of `pages`, each page's checked (`gold`), and what no single page can show: a test id used
    twice. It is what publishing a dataset checks; grading needs none of it.

    Note: a gold file no manifest names isn't refused, since a dataset may hold several manifests, each naming
    some of the gold files."""
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
    """Each verdict of `page` as a test line: `page_id`, `suite`, `document`, `test_id`, `test_type`,
    `output_type`, `derivation`, `tags`, `result` and `why`. `summarize` reads any set of them."""
    by_id = {t.id: t for t in tests}
    on = {"page_id": page.page_id, "suite": page.suite, "document": page.document}
    return [on | {"test_id": (t := by_id[v.id]).id, "test_type": t.test_type, "output_type": t.output_type,
                  "derivation": t.derivation, "tags": list(t.tags), "result": v.result, "why": v.why}
            for v in verdicts]


def summarize(lines: Iterable[Line]) -> dict[str, Any]:
    """Test lines (from `lines`) as one summary: `headline`, the mean of the families' scores, and `families`,
    each family's `score` (the share of its tests passed), `tests` and `documents`. The headline is None when
    there are no tests.

    Note: a mean over families, each flat over its tests, so how many tests a family has never sets its
    weight. A document's tests pass or fail together (one misread table fails all its cells), so
    `documents` says how much a score rests on."""
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
