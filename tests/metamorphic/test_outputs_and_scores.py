# ruff: noqa: E501
"""Relations of missing, empty and malformed outputs (M138 to M141) and of how verdicts add up to family scores
and the headline (M142 to M144)."""
from __future__ import annotations

import statistics
import types

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from test_invariants import answer
from test_properties import TESTS

from metamorphic.common import HOLDS, relation
from omni_bench_core.errors import SystemFailed
from omni_parse_bench import views
from omni_parse_bench.scorers import unit_tests as scorer
from omni_parse_bench.scorers.unit_tests import compare, runners

OUTPUTS = ("html", "blocks")
BAD_HTML = [0, 1.5, True, [], {}, b"<p>x</p>", ["<p>x</p>"], {"html": "<p>x</p>"}]
GOOD_BOX = [0.1, 0.1, 0.5, 0.2]
BAD_BLOCKS = [
    {}, "text", 5, (1, 2), [1], ["text"], [{"label": "text"}], [{"bbox": GOOD_BOX}],
    [{"label": "text", "bbox": GOOD_BOX, "extra": 1}], [{"label": "paragraph", "bbox": GOOD_BOX}],
    [{"label": 5, "bbox": GOOD_BOX}], [{"label": "text", "bbox": GOOD_BOX[:3]}],
    [{"label": "text", "bbox": [*GOOD_BOX, 0.9]}], [{"label": "text", "bbox": [0.1, 0.1, 1.5, 0.2]}],
    [{"label": "text", "bbox": [-0.1, 0.1, 0.5, 0.2]}], [{"label": "text", "bbox": ["0.1", 0.1, 0.5, 0.2]}],
    [{"label": "text", "bbox": [True, 0.1, 0.5, 0.2]}], [{"label": "text", "bbox": "0.1 0.1 0.5 0.2"}],
    [{"label": "text", "bbox": GOOD_BOX, "text": 5}], [{"label": "text", "bbox": GOOD_BOX}, "x"],
]


# Note: noise runs on a sample of the html tests (every kind of them), so the real dataset stays quick
HTML = [t for t in TESTS if t.output_type == "html"]
NOISY = HTML[::max(1, len(HTML) // 60)]


# Note: pages are scored whole in M141 and M144; every 20th page of the real dataset keeps those quick
PAGES: dict[str, list] = {}
for _t in TESTS:
    PAGES.setdefault(_t.page_id, []).append(_t)
SAMPLE = {p: ts for i, (p, ts) in enumerate(PAGES.items()) if i % (20 if len(PAGES) > 200 else 1) == 0}


def verdict(pred, t):
    [v] = compare.score(pred, [t])
    return v


def read_by(t) -> str:
    """The output a test reads."""
    return t.output_type


@relation(HOLDS, domain="every loaded test, each with its own answer, with no output, with the output None, and "
                        "with only the other output")
def test_a_test_whose_output_is_missing_fails_as_no_output_and_the_others_are_unaffected():
    """A test fails with the reason `no <output> output` when its output is absent from the prediction or
    None, whatever else the prediction holds: the other output, written right, never stands in for it. A test
    whose output is there is not affected by the other output's absence. [M138]
    Why it matters for a score: a system with html alone scores 0 on layout, and one with blocks alone 0 on
    text and tables; each family is graded only on what the system gave (docs/scoring/README.md, case
    score-missing-output)."""
    for t in TESTS:
        right = answer(t)
        other = next(o for o in OUTPUTS if o != t.output_type)
        stand_in = {other: [] if other == "blocks" else "<p>x</p>"}
        # Given a test and its own answer; Then the answer alone passes (the baseline)
        assert verdict(right, t).result == "pass", t.id
        # When its output is absent, None, or the other output stands alone; Then it fails as no output
        for pred in [{}, {t.output_type: None}, stand_in, {**stand_in, t.output_type: None}]:
            got = verdict(pred, t)
            assert (got.result, got.why) == ("fail", f"no {t.output_type} output"), (t.id, pred)
        # And the other output being absent or broken changes nothing for the test
        for pred in [right, {**right, other: None}, {**right, other: BAD_HTML[0] if other == "html" else {}}]:
            assert verdict(pred, t).result == "pass", (t.id, pred)


@relation(HOLDS, domain="every loaded test, 8 values that are not a string for html, 20 malformed blocks, the "
                        "other output right or wrong")
def test_an_output_of_the_wrong_shape_fails_only_the_tests_that_read_it():
    """A test whose `html` is not a string, or whose `blocks` are not a list of `{label, bbox[, text]}` objects
    with a label of the eleven, a box of four numbers from 0 to 1 and a text that is a string or null, fails
    with a reason starting `malformed html output` or `malformed blocks output`; the tests that read the
    other output are not affected, and a scorer never raises on it. [M139]
    Why it matters for a score: a system's malformed output is its failure, counted as failed tests, never as
    a crash that loses the run (docs/scoring/README.md, case score-malformed; docs/design.md)."""
    for t in TESTS:
        right = answer(t)
        bad = BAD_HTML if t.output_type == "html" else BAD_BLOCKS
        for value in bad:
            # Given a malformed output for the test's own output type; Then the test fails as malformed
            got = verdict({**right, t.output_type: value}, t)
            assert got.result == "fail" and got.why.startswith(f"malformed {t.output_type} output"), \
                (t.id, value, got)
            # And a malformed output of the other type does not affect it
        other = "blocks" if t.output_type == "html" else "html"
        for value in BAD_BLOCKS[:3] if other == "blocks" else BAD_HTML[:3]:
            assert verdict({**right, other: value}, t).result == "pass", (t.id, other, value)


@relation(HOLDS, domain="every loaded test; html '' and blocks [], and 40 random strings of markup characters")
def test_an_empty_output_fails_with_its_documented_reason_and_markup_noise_never_raises():
    """An empty html (`""`) fails every loaded test except a `page_near_empty` test, which it passes; a
    `table_cell` test then reads `no tables found`; an empty blocks list fails every layout test with `no block
    covers 50% of its place`; a table the cell reader cannot parse (`<td>` outside a `<tr>`) is read as text by a form-field test, so
    the cells of a table that fail it pass it and a value beside the label fails as text (present-text.md); and html
    made of unclosed, stray or nested tag characters never raises, giving a verdict for every test. [M140]
    Why it matters for a score: an empty answer costs its tests and a garbled one is graded, never a
    scorer crash (docs/scoring/layout_kind.md; docs/scoring/table_cell.md, case cell-no-table)."""
    for t in TESTS:
        if t.output_type == "html":
            got = verdict({"html": ""}, t)
            assert got.result == ("pass" if t.test_type == "page_near_empty" else "fail"), (t.id, got)
            if t.test_type == "table_cell":
                assert got.why == "no tables found", (t.id, got)
        else:
            got = verdict({"blocks": []}, t)
            assert (got.result, got.why) == ("fail", "no block covers 50% of its place"), (t.id, got)
    # And a table the cell reader cannot parse (`<td>` outside a `<tr>`) is read as text (present-text.md): the
    # same cells that fail a field test as a table (a value under the label) pass it, and a value beside the
    # label fails as text
    field = runners.Present(runners.Text("Date of birth:", 0), True, runners.Text("__/__/____", 0),
                            (runners.Text("Name:", 0), runners.Text("Place of birth:", 0)))
    rows = "<table><tr><td>Date of birth:</td><td>Place of birth:</td></tr><tr><td>01/02/1990</td><td></td></tr></table>"
    flat = "<table><td>Date of birth:</td><td>Place of birth:</td><td>01/02/1990</td><td></td></table>"
    beside = "<table><td>Date of birth:</td><td>01/02/1990</td></table>"
    assert runners.present(field, views.html(rows)) == (False, "'Date of birth:' cell's value cell (below) holds '01/02/1990'")
    assert runners.present(field, views.html(flat)) == (True, "")
    assert runners.present(field, views.html(beside)) == (False, "'Date of birth:' is followed by '01/02/1990' to the end of the page")
    noise = st.text("<>/=\"'&;!-ptdrbhx\n 5$\\_[]", max_size=60)

    @settings(max_examples=40)
    @given(noise)
    def check(page):
        for t in NOISY:
            assert verdict({"html": page}, t).result in ("pass", "fail"), (t.id, page)

    check()


@relation(HOLDS, domain="the tests of every loaded page (every 20th page of the dataset), scored whole beside a failed "
                        "page of the same tests")
def test_a_failed_page_fails_every_one_of_its_tests_and_costs_no_more():
    """A page the system failed (a prediction that is not `{"pages": [one object]}`, or an empty one) is scored
    with every test failed, each as `no <output> output`, and in a summary it adds its tests to the count and
    nothing to what passed: a family's score is passed over all its tests, a failed page's included. [M141]
    Why it matters for a score: a crash or refusal costs the tests of its page, not a page's share of the
    headline (docs/scoring/README.md, case score-failed-page)."""
    unit = scorer.UnitTests()
    tests = [t for ts in SAMPLE.values() for t in ts]
    failed = unit.score_failure(tests)
    assert failed.result["passed"] == 0 and failed.result["tests"] == len(tests)
    assert [d["result"] for d in failed.details] == ["fail"] * len(tests)
    assert [d["why"] for d in failed.details] == [f"no {t.output_type} output" for t in tests]
    assert unit.prediction({"pages": [{"html": "<p>x</p>"}]}) == {"html": "<p>x</p>"}    # a valid envelope
    for bad in [None, [], {}, {"pages": []}, {"pages": [{}, {}]}, {"pages": "x"}, {"pages": [3]}]:
        with pytest.raises(SystemFailed, match="a row is one page"):
            unit.prediction(bad)
    # Given a page answered right and a page failed; When both are summarized; Then the failed page adds tests only
    ok = [unit.score(merged([answer(t) for t in ts]), ts) for ts in SAMPLE.values()]
    rows = [{"row": {"document": f"a{i}", "suite": "s"}, **r.result} for i, r in enumerate(ok)]
    rows.append({"row": {"document": "b", "suite": "s"}, **failed.result})
    alone = unit.summarize(rows[:-1])
    both = unit.summarize(rows)
    for family, entry in alone["families"].items():
        assert both["families"][family]["tests"] == 2 * entry["tests"], family
        assert both["families"][family]["score"] == pytest.approx(entry["score"] / 2), family


def merged(outputs: list[dict]) -> dict:
    """One prediction holding what each of `outputs` writes, for the same output types."""
    html = "".join(o["html"] for o in outputs if "html" in o)
    blocks = [b for o in outputs for b in o.get("blocks", [])]
    return {"html": html, "blocks": blocks}


# ------------------------------------------------------------------------------------ aggregation

# Restated from docs/scoring/README.md, not read from `vocab`, so a changed family map is caught
FAMILY = {"present": "text", "order": "text", "repeat": "text", "page_near_empty": "text", "table_cell": "tables",
          "layout_kind": "layout", "format": "format"}
READS = {**dict.fromkeys(FAMILY, "html"), "layout_kind": "blocks"}


def make_line(page, document, kind, ok, n):
    return {"page_id": page, "document": document, "suite": "s", "test_id": f"{page}-{n}", "test_type": kind,
            "output_type": READS[kind], "derivation": "d",
            "tags": [], "args": {}, "settings": {}, "result": "pass" if ok else "fail", "why": ""}


def lines_of(plan: dict[str, list[tuple[str, bool]]]) -> list[dict]:
    """Test lines for a plan {page: [(test type, passed)]}; the page's document is its name's first letter."""
    return [make_line(page, page[0], kind, ok, n)
            for page, items in plan.items() for n, (kind, ok) in enumerate(items)]


TYPES = st.sampled_from(["present", "order", "repeat", "page_near_empty", "table_cell", "layout_kind", "format"])
PLAN = st.dictionaries(st.sampled_from(["a1", "a2", "b1", "c1", "c2"]),
                       st.lists(st.tuples(TYPES, st.booleans()), min_size=1, max_size=8), min_size=1, max_size=5)


def expected(plan):
    """Each family's (passed, tests), the headline and the families present, computed from the plan alone."""
    count: dict[str, list[int]] = {}
    for items in plan.values():
        for kind, ok in items:
            c = count.setdefault(FAMILY[kind], [0, 0])
            c[0] += ok
            c[1] += 1
    heads = [p / n for f, (p, n) in count.items() if f in ("text", "tables", "layout")]
    every = [p / n for p, n in count.values()]
    return count, statistics.fmean(heads or every)


@relation(HOLDS, domain="plans of 1 to 5 pages in 3 documents, 1 to 8 tests each, of the 7 test types, "
                        "passing or failing")
@given(PLAN)
def test_a_family_score_is_its_share_of_passed_tests_and_the_headline_their_mean(plan):
    """In a summary of test lines, a family's score is the share of its tests that passed, the families being
    text (present, order, repeat, page_near_empty), tables (table_cell), layout (layout_kind) and format; the
    headline is the plain mean of the text, tables and layout scores that have tests, the format score is
    reported but is not in it, a family with no test is left out, and a run with none of the three has the
    mean of the families it has. [M142]
    Why it matters for a score: this is the number a leaderboard prints (docs/scoring/README.md, cases
    score-headline and score-subset); a family weighs a third of it however many tests it has."""
    # Given test lines of several pages and their verdicts
    got = scorer.summarize(lines_of(plan))
    count, headline = expected(plan)
    # Then each family's score is passed over its tests, the absent ones are left out
    assert set(got["families"]) == set(count)
    for family, (passed, n) in count.items():
        assert got["families"][family]["score"] == passed / n, family
        assert got["families"][family]["tests"] == n, family
    # And the headline is the mean of the headline families present (all families when there is none)
    assert got["score"] == pytest.approx(headline)


@relation(HOLDS, domain="plans, shuffled lines, tests moved to another page of the same document, "
                        "and every test doubled")
@given(PLAN, st.randoms(use_true_random=False))
def test_a_summary_does_not_depend_on_the_order_or_the_page_split_of_its_tests(plan, rnd):
    """The family scores and the headline of a summary stay the same when its test lines are in another order,
    when tests are moved to another page of the same document, and when every test is doubled (a family with
    twice the tests and the same share passed). [M143]
    Why it matters for a score: scores are pooled over tests, so how a run was batched or ordered, or how
    many pages a document is split over, must not move them."""
    base = scorer.summarize(lines_of(plan))

    def scores(s):
        return s["score"], {f: (e["score"], e["tests"]) for f, e in s["families"].items()}

    shuffled = lines_of(plan)
    rnd.shuffle(shuffled)
    assert scores(scorer.summarize(shuffled))[0] == pytest.approx(scores(base)[0])
    assert scores(scorer.summarize(shuffled))[1] == scores(base)[1]
    # Given a test moved to another page of its document (pages 'a1' and 'a2' are one document)
    moved = {p: list(items) for p, items in plan.items()}
    if "a1" in moved and "a2" in moved and len(moved["a1"]) > 1:
        moved["a2"].append(moved["a1"].pop())
        assert scores(scorer.summarize(lines_of(moved)))[0] == pytest.approx(scores(base)[0])
        assert scores(scorer.summarize(lines_of(moved)))[1] == scores(base)[1]
    # And every test doubled, on pages of their own
    doubled = {**plan, **{f"{p}x": items for p, items in plan.items()}}
    got = scorer.summarize(lines_of(doubled))
    assert got["score"] == pytest.approx(base["score"])
    assert {f: e["score"] for f, e in got["families"].items()} == \
        pytest.approx({f: e["score"] for f, e in base["families"].items()})


@relation(HOLDS, domain="every loaded page (every 20th page of the dataset): 4 predictions (all answers, html alone, "
                        "blocks alone, nothing), each page scored and summarized by both paths")
def test_the_page_scores_and_the_test_lines_summarize_to_the_same_headline():
    """The summary of pages scored one by one (`UnitTests.score`, then `summarize` of the page counts) equals the
    summary of the same verdicts as test lines (`lines`, then `summarize`): the same family scores, test
    counts and headline; a run without the `blocks` output has a layout score of 0 and the same text and tables
    scores as the run with it. [M144]
    Why it matters for a score: the harness writes page counts and the report reads test lines; both must give
    the leaderboard's number (docs/scoring/README.md, case score-missing-output)."""
    unit = scorer.UnitTests()
    pages = SAMPLE
    right = {t.id: answer(t) for ts in pages.values() for t in ts}
    results = {}
    for name, keep in [("both", OUTPUTS), ("html", ("html",)), ("blocks", ("blocks",)), ("none", ())]:
        rows, test_lines = [], []
        for page_id, tests in pages.items():
            pred = merged([right[t.id] for t in tests])
            pred = {k: v for k, v in pred.items() if k in keep}
            page = types.SimpleNamespace(page_id=page_id, suite="s", document=page_id)
            rows.append({"row": {"document": page_id, "suite": "s"}, **unit.score(pred, tests).result})
            test_lines += scorer.lines(compare.score(pred, tests), tests, page)
        by_pages, by_lines = unit.summarize(rows), scorer.summarize(test_lines)
        assert by_pages["score"] == pytest.approx(by_lines["score"]), name
        assert {f: (e["score"], e["tests"]) for f, e in by_pages["families"].items()} == \
            {f: (e["score"], e["tests"]) for f, e in by_lines["families"].items()}, name
        results[name] = by_pages
    # The merged page of the answers can fail tests that need their own page (an order test across pages is
    # not graded here): compare families that read one output, which the answers of that output keep alone
    for family in ("layout",):
        assert results["html"]["families"].get(family, {"score": 0.0})["score"] == 0.0, family
        assert results["none"]["families"][family]["score"] == 0.0, family
    for family in ("text", "tables"):
        assert results["blocks"]["families"][family]["score"] == 0.0, family
        assert results["none"]["families"][family]["score"] == 0.0, family
        assert results["html"]["families"][family]["score"] == results["both"]["families"][family]["score"], family
    assert results["both"]["families"]["layout"]["score"] == results["blocks"]["families"]["layout"]["score"]
