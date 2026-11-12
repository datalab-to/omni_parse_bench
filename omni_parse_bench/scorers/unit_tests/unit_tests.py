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


@dataclasses.dataclass(frozen=True)
class UnitTests(scorer.Scorer[data.Page, tuple[_tests.Test, ...], Mapping[str, Any]]):
    """Omni Parse Bench's scorer: each page's yes/no tests, run against its outputs. A test on an output the
    system didn't produce fails as "no <output> output", so a system with html alone scores 0 on layout.

    - A page's line in scores.jsonl holds `tests`, `passed` and `per_family` (each family's `tests` and
      `passed`), and the same counts by `per_tag`, `per_test_type`, `per_arg_kind` and `per_derivation`;
      its `row` holds
      the page's `document` and `suite`;
    - its details (`details/<page_id>.jsonl`) hold one test line per test (`lines`); and
    - the summary is `summarize` over every page, a failed one with all its tests failed (`score_failure`):
      the families in the order text, tables, layout, and their mean as the headline, then the same scores
      by tag, suite, test type, arg kind and derivation."""

    name: ClassVar[str] = "unit_tests"
    headline: ClassVar[str] = "score"

    def gold(self, row: data.Page) -> tuple[_tests.Test, ...]:
        """The page's tests."""
        return gold(row)

    def prediction(self, output: Any) -> Mapping[str, Any]:
        """The page's outputs: the one page of the prediction's `pages`, as a row is one page. A prediction
        that isn't `{"pages": [an object of outputs]}` is the system's failure: the page fails. An output
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
        result = {"tests": len(vs), "passed": sum(v.result == "pass" for v in vs)} | _count(
            (v.result == "pass", (t := by_id[v.id]).test_type, t.derivation, t.tags,
             _tests.arg_kinds(t.test_type, t.args)) for v in vs)
        return scorer.Score(result, [{"test_id": v.id, "test_type": (t := by_id[v.id]).test_type,
                                      "output_type": t.output_type, "derivation": t.derivation,
                                      "tags": list(t.tags), "args": t.args, "settings": t.settings,
                                      "result": v.result, "why": v.why} for v in vs])

    def score_failure(self, tests: Sequence[_tests.Test]) -> scorer.Score:
        """A failed page: the score of a prediction with no outputs, so every test fails and the page costs
        its tests, not a page's share of the headline."""
        return self.score({}, tests)

    def detail_fields(self, row: data.Page) -> dict[str, Any]:
        """Each detail line's page (`page_id`, `suite`, `document`), so a page's details are test lines that
        `summarize` reads."""
        return {"page_id": row.page_id, "suite": row.suite, "document": row.document}

    def row_fields(self, row: data.Page) -> dict[str, Any]:
        return {"document": row.document, "suite": row.suite}

    def summarize(self, lines: Sequence[Line]) -> dict[str, Any]:
        """`score`, `families` and the slices (`per_tag`, `per_suite`, `per_test_type`, `per_arg_kind`,
        `per_derivation`), over every page's counts, a failed page's from `score_failure`. A line kept
        before the slices were
        (no `per_tag`, ..., no `row.suite`) adds nothing to them."""
        return _summary(lines)

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
    `output_type`, `derivation`, `tags`, `args` and `settings` (the test's own, as its gold file states them),
    `result` and `why`. `summarize` reads any set of them."""
    by_id = {t.id: t for t in tests}
    on = {"page_id": page.page_id, "suite": page.suite, "document": page.document}
    return [on | {"test_id": (t := by_id[v.id]).id, "test_type": t.test_type, "output_type": t.output_type,
                  "derivation": t.derivation, "tags": list(t.tags), "args": t.args, "settings": t.settings,
                  "result": v.result, "why": v.why}
            for v in verdicts]


def summarize(lines: Iterable[Line]) -> dict[str, Any]:
    """Test lines (from `lines`) as one summary: `score`, the mean of the families' scores, and `families`,
    each family's `score` (the share of its tests passed), `tests` and `documents`; then `per_tag`,
    `per_suite`, `per_test_type`, `per_arg_kind` and `per_derivation`, each a slice's entries shaped as a
    family's. `score`
    is None when there are no tests, and a slice with no tests is left out.

    Note: a test with several tags counts under each, so the tag slices' `tests` add up to at least the
    total; the suite, test type and derivation slices each add up to it exactly. The arg kind slice (text,
    number, latex: how the test's content is compared) counts a test under each kind its args use, and a
    `layout_kind` test under none, since its text only labels a place. A slice's score is its
    share of tests passed, not part of the headline.

    Note: a page's lines are those sharing a `page_id` (unique in a dataset); a line without `suite`,
    `tags` or `derivation` adds nothing to that slice.

    Note: a mean over families, each flat over its tests, so how many tests a family has never sets its
    weight. A document's tests pass or fail together (one misread table fails all its cells), so
    `documents` says how much a score rests on."""
    by_page: dict[str, list[Line]] = collections.defaultdict(list)
    for x in lines:
        by_page[x.get("page_id", x["document"])].append(x)
    return _summary(
        {"row": {"document": xs[0]["document"], **({"suite": xs[0]["suite"]} if "suite" in xs[0] else {})},
         "tests": len(xs), "passed": sum(x["result"] == "pass" for x in xs)}
        | _count((x["result"] == "pass", x["test_type"], x.get("derivation", ""), x.get("tags", ()),
                  _tests.arg_kinds(x["test_type"], x.get("args", {})))
                 for x in xs)
        for xs in by_page.values())


def _count(marks: Iterable[tuple[bool, str, str, Iterable[str], Iterable[str]]]
           ) -> dict[str, dict[str, dict[str, int]]]:
    """One page's counts, each as `{key: {"tests", "passed"}}`: `per_family`, `per_tag`, `per_test_type`,
    `per_arg_kind` and `per_derivation`, from its tests' (passed, test type, derivation, tags, arg kinds). A
    test counts once under each of its tags and of its arg kinds; a blank derivation counts under none."""
    out: dict[str, dict[str, dict[str, int]]] = {"per_family": {}, "per_tag": {}, "per_test_type": {},
                                                 "per_arg_kind": {}, "per_derivation": {}}
    for ok, test_type, derivation, tags, arg_kinds in marks:
        keys = {"per_family": [vocab.FAMILIES[test_type]], "per_tag": dict.fromkeys(tags),
                "per_test_type": [test_type], "per_arg_kind": dict.fromkeys(arg_kinds),
                "per_derivation": [derivation] if derivation else []}
        for slice_, ks in keys.items():
            for k in ks:
                c = out[slice_].setdefault(k, {"tests": 0, "passed": 0})
                c["tests"] += 1
                c["passed"] += ok
    return out


def _entries(counts: Iterable[tuple[str, str, int, int]], order: Sequence[str] = ()) -> dict[str, Any]:
    """From (key, document, passed, tests) counts, each key's `score`, `tests` and `documents`: the keys of
    `order` first, then the rest sorted; a key with no tests is left out."""
    tests: collections.Counter[str] = collections.Counter()
    passed: collections.Counter[str] = collections.Counter()
    documents: dict[str, set[str]] = collections.defaultdict(set)
    for key, document, k, n in counts:
        tests[key] += n
        passed[key] += k
        documents[key].add(document)
    keys = [*order, *sorted(tests.keys() - set(order))]
    return {k: {"score": passed[k] / n, "tests": n, "documents": len(documents[k])}
            for k in keys if (n := tests[k])}


def _summary(pages: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """`score`, `families` and the slices, from score lines (a page's `row`, `tests`, `passed` and `_count`s);
    the families in `vocab.FAMILY_ORDER`, the test types in `vocab.FAMILIES` order, the arg kinds in
    `tests.KINDS` order, the other slices' keys sorted. A line without a count, or without `row.suite`, adds
    nothing to that slice."""
    pages = list(pages)

    def counted(name: str) -> Iterable[tuple[str, str, int, int]]:
        return ((k, x["row"]["document"], c["passed"], c["tests"])
                for x in pages for k, c in x.get(name, {}).items())

    families = _entries(counted("per_family"), vocab.FAMILY_ORDER)
    return {"score": float(statistics.fmean(x["score"] for x in families.values())) if families else None,
            "families": families,
            "per_tag": _entries(counted("per_tag")),
            "per_suite": _entries((x["row"]["suite"], x["row"]["document"], x["passed"], x["tests"])
                                 for x in pages if "suite" in x["row"]),
            "per_test_type": _entries(counted("per_test_type"), tuple(vocab.FAMILIES)),
            "per_arg_kind": _entries(counted("per_arg_kind"), tuple(_tests.KINDS)),
            "per_derivation": _entries(counted("per_derivation"))}
