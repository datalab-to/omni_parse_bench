"""score and summarize: the results, the families and their documents, the headline, and what a page's line
and details hold."""
from __future__ import annotations

import dataclasses

import pytest

from omni_parse_bench import data, score, summarize, views
from omni_parse_bench.scorers import unit_tests as scorer
from omni_parse_bench.scorers.unit_tests import lines as _lines
from omni_parse_bench.scorers.unit_tests import runners
from omni_parse_bench.scorers.unit_tests import tests as gold

PAGE = data.Page("p", "d", "s", "pages/p.pdf", "gold/p.json", ("html",))


def lines(verdicts, tests, pages=(PAGE,)) -> list[dict]:
    """The score lines of `verdicts`, each on its test's page, of `pages`."""
    by = {p.page_id: p for p in pages}
    vs = list(verdicts)
    tid = {t.id: t.page_id for t in tests}
    return [x for page_id in dict.fromkeys(tid[v.id] for v in vs)
            for x in _lines([v for v in vs if tid[v.id] == page_id], tests, by[page_id])]


def on_one_page(*tests: dict) -> tuple[gold.Test, ...]:
    base = {"output_type": "html", "derivation": "authored", "settings": {}}
    return gold.parse("p", {"tests": [base | t for t in tests]})


def text(s: str) -> dict:
    return {"content": {"text": s, "max_diffs": 0}}


TESTS = on_one_page(
    {"id": "a", "test_type": "present", "tags": ["eng"], "args": text("alpha")},
    {"id": "b", "test_type": "present", "tags": ["eng"], "args": text("beta")},
    {"id": "c", "test_type": "present", "tags": ["eng", "table"], "args": text("gamma")},
    {"id": "d", "test_type": "present", "tags": ["form"], "args": text("delta")},
    {"id": "m", "test_type": "present", "tags": ["math"], "args": {"content": {"latex": "x^2"}}},
)


def test_results():
    vs = {v.id: v.result for v in score({"html": "<p>alpha beta</p>"}, TESTS)}
    assert vs == {"a": "pass", "b": "pass", "c": "fail", "d": "fail", "m": "fail"}


def test_a_missing_output_fails_its_tests():
    assert {v.result for v in score({"html": None}, TESTS[:4])} == {"fail"}
    assert {v.result for v in score({}, TESTS[:4])} == {"fail"}


def test_the_summary_is_the_headline_and_the_families_alone():
    s = summarize(lines(score({"html": "<p>alpha beta</p>"}, TESTS), TESTS))
    assert s == {"headline": 2 / 5, "families": {"text": {"score": 2 / 5, "tests": 5, "documents": 1}}}


def test_a_slice_of_test_lines_is_summarized_the_same_way():
    """Any other breakdown, such as one tag, is the same summary over the lines selected."""
    eng = [x for x in lines(score({"html": "<p>alpha beta</p>"}, TESTS), TESTS) if "eng" in x["tags"]]
    assert summarize(eng)["families"]["text"] == {"score": 2 / 3, "tests": 3, "documents": 1}


def test_scores_are_floats_even_when_every_test_agrees():
    s = summarize(lines(score({"html": "<p>alpha beta</p>"}, TESTS[:2]), TESTS))
    assert type(s["headline"]) is float and type(s["families"]["text"]["score"]) is float


def test_a_pages_line_holds_its_counts_and_its_details_every_verdict():
    s = scorer.UnitTests().score({"html": "<p>alpha beta</p>"}, TESTS)
    assert s.result == {"tests": 5, "passed": 2, "per_family": {"text": {"tests": 5, "passed": 2}}}
    assert s.details[2] == {"test_id": "c", "test_type": "present", "output_type": "html",
                            "derivation": "authored", "tags": ["eng", "table"], "result": "fail",
                            "why": s.details[2]["why"]}


def test_unit_tests_names_its_headline():
    line = {"id": "p", "row": {"document": "d"}, "tests": 1, "passed": 1,
            "per_family": {"text": {"tests": 1, "passed": 1}}}
    assert scorer.UnitTests().summarize([line]) == {
        "headline": 1.0, "headline_is": "the mean of the families' scores",
        "families": {"text": {"score": 1.0, "tests": 1, "documents": 1}}}


def test_the_families_come_in_a_fixed_order_whatever_the_order_met():
    tests = on_one_page(
        {"id": "k", "test_type": "layout_kind", "output_type": "blocks", "tags": [],
         "args": {"content": {"text": "x", "max_diffs": 0, "place": [[0.1, 0.1, 0.5, 0.2]]}},
         "settings": {"kind": "text"}},
        {"id": "k2", "test_type": "layout_kind", "output_type": "blocks", "tags": [],
         "args": {"content": {"text": "y", "max_diffs": 0, "place": [[0.1, 0.3, 0.5, 0.4]]}},
         "settings": {"kind": "text"}},
        {"id": "t", "test_type": "table_cell", "tags": [], "args": {"cell": {"text": "1", "max_diffs": 0}}},
        {"id": "a", "test_type": "present", "tags": [], "args": text("alpha")},
    )
    s = summarize(lines(score({"html": "<p>alpha</p>"}, tests), tests))
    assert list(s["families"]) == ["text", "tables", "layout"]


@pytest.mark.parametrize("output, why", [
    ({"html": 3}, "html must be a string"),
    ({"html": {"text": "alpha"}}, "html must be a string"),
])
def test_a_malformed_html_output_fails(output, why):
    vs = score(output, TESTS[:2])
    assert {v.result for v in vs} == {"fail"} and all(why in v.why for v in vs)


LAYOUT = on_one_page({"id": "k", "test_type": "layout_kind", "output_type": "blocks", "tags": [],
                      "args": {"content": {"text": "Title", "max_diffs": 0, "place": [[0.1, 0.1, 0.5, 0.2]]}},
                      "settings": {"kind": "heading"}})


@pytest.mark.parametrize("blocks", [
    {"label": "heading"},
    [{"bbox": [0, 0, 1, 1]}],
    [{"label": "title", "bbox": [0, 0, 1, 1]}],
    [{"label": "heading", "bbox": [0, 0, 1]}],
    [{"label": "heading", "bbox": [0, 0, 2, 1]}],
    [{"label": "heading", "bbox": "0 0 1 1"}],
    [{"label": "heading", "bbox": [0, 0, 1, 1], "text": 7}],
    ["heading"],
])
def test_a_malformed_blocks_output_fails(blocks):
    with pytest.raises(views.MalformedOutput):
        views.blocks(blocks)
    [v] = score({"blocks": blocks}, LAYOUT)
    assert v.result == "fail" and v.why.startswith("malformed blocks output")


def test_a_runner_raising_on_a_well_formed_output_is_raised_naming_its_test(monkeypatch):
    """A bug of ours, never the provider's fault: raised, since a score with the test left out is wrong."""
    def broken(t, v):
        raise KeyError("oops")
    monkeypatch.setitem(runners.TYPES, "present", (runners.Present, broken))
    with pytest.raises(KeyError) as e:
        score({"html": "<p>alpha</p>"}, TESTS)
    assert TESTS[0].id in " ".join(e.value.__notes__)


def test_a_view_raising_on_a_well_formed_output_is_raised(monkeypatch):
    def broken(s):
        raise RecursionError("deep")
    monkeypatch.setitem(scorer.compare.VIEWS, "html", broken)
    with pytest.raises(RecursionError):
        score({"html": "<p>alpha</p>"}, TESTS)


def pages_and_tests(documents: int, per: int = 4, test_type: str = "present") -> tuple[list, list]:
    """`documents` pages, each its own document, with `per` tests each."""
    pages = [data.Page(f"p{k}", f"d{k}", "s", f"pages/p{k}.pdf", f"gold/p{k}.json", ("html",))
             for k in range(documents)]
    args = text("x") if test_type == "present" else {"cell": {"text": "x", "max_diffs": 0}}
    tests = [gold.test(f"p{i // per}", {"id": f"{test_type}{i}", "test_type": test_type,
                                        "output_type": "html", "derivation": "authored", "tags": ["table"],
                                        "args": args, "settings": {}}) for i in range(documents * per)]
    return pages, tests


def half(tests: list, per: int = 4) -> list:
    """Every other page's tests pass, each page's together."""
    return [scorer.Verdict(t.id, "pass" if (i // per) % 2 else "fail", "") for i, t in enumerate(tests)]


def test_each_score_counts_the_documents_its_tests_are_from():
    pages, tests = pages_and_tests(9)
    s = summarize(lines(half(tests), tests, pages))
    assert s["families"]["text"]["documents"] == 9
    one = [dataclasses.replace(p, document="d") for p in pages]
    assert summarize(lines(half(tests), tests, one))["families"]["text"]["documents"] == 1


def test_every_test_type_has_a_family():
    from omni_parse_bench import vocab
    assert set(vocab.FAMILIES) == set(runners.TYPES)


def test_headline_is_the_mean_of_the_graded_families():
    tests = on_one_page(
        {"id": "a", "test_type": "present", "tags": [], "args": text("alpha")},
        {"id": "b", "test_type": "present", "tags": [], "args": text("beta")},
        {"id": "c", "test_type": "present", "tags": [], "args": text("gamma")},
        {"id": "k", "test_type": "table_cell", "tags": [], "args": {"cell": {"text": "1", "max_diffs": 0}}},
    )
    h = summarize(lines(score({"html": "<p>alpha beta</p>"}, tests), tests))
    assert h["families"] == {"text": {"score": 2 / 3, "tests": 3, "documents": 1},
                             "tables": {"score": 0, "tests": 1, "documents": 1}}
    assert h["headline"] == (2 / 3 + 0) / 2   # each family weighs the same, however many tests it has
    only_text = summarize(lines(score({"html": "<p>alpha beta</p>"}, tests[:3]), tests))
    assert set(only_text["families"]) == {"text"}   # a family with no verdicts isn't in it
