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


def test_the_summary_is_the_score_the_families_and_the_slices():
    s = summarize(lines(score({"html": "<p>alpha beta</p>"}, TESTS), TESTS))
    assert set(s) == {"score", "families", "per_tag", "per_suite", "per_test_type", "per_arg_kind",
                      "per_derivation"}
    assert (s["score"], s["families"]) == (2 / 5, {"text": {"score": 2 / 5, "tests": 5, "documents": 1}})


SLICED = {"per_tag": {"eng": {"score": 2 / 3, "tests": 3, "documents": 1},
                      "form": {"score": 0.0, "tests": 1, "documents": 1},
                      "math": {"score": 0.0, "tests": 1, "documents": 1},
                      "table": {"score": 0.0, "tests": 1, "documents": 1}},
          "per_suite": {"s": {"score": 2 / 5, "tests": 5, "documents": 1}},
          "per_test_type": {"present": {"score": 2 / 5, "tests": 5, "documents": 1}},
          "per_arg_kind": {"text": {"score": 2 / 4, "tests": 4, "documents": 1},
                           "latex": {"score": 0.0, "tests": 1, "documents": 1}},
          "per_derivation": {"authored": {"score": 2 / 5, "tests": 5, "documents": 1}}}


def _slices(s: dict) -> dict:
    return {k: v for k, v in s.items() if k.startswith("per_")}


def test_test_lines_are_summarized_by_slice():
    s = summarize(lines(score({"html": "<p>alpha beta</p>"}, TESTS), TESTS))
    assert _slices(s) == SLICED
    assert sum(x["tests"] for x in s["per_tag"].values()) == 6      # "c" counts under eng and table


def test_score_lines_are_summarized_by_slice_the_same_way():
    sc = scorer.UnitTests().score({"html": "<p>alpha beta</p>"}, TESTS)
    line = {"id": "p", "row": scorer.UnitTests().row_fields(PAGE), **sc.result}
    assert _slices(scorer.UnitTests().summarize([line])) == SLICED


def test_an_empty_slice_is_left_out_and_test_types_keep_the_vocabulary_order():
    tests = on_one_page(
        {"id": "a", "test_type": "present", "tags": [], "args": text("alpha")},
        {"id": "r", "test_type": "repeat", "tags": [], "args": text("alpha"),
         "settings": {"expected_count": 1}},
        {"id": "o", "test_type": "order", "tags": [], "args": {"before": text("alpha")["content"],
                                                              "after": text("beta")["content"]}})
    s = summarize(lines(score({"html": "<p>alpha beta</p>"}, tests), tests))
    assert s["per_tag"] == {}
    assert list(s["per_test_type"]) == ["present", "order", "repeat"]


def test_a_failing_text_test_names_the_closest_text_and_a_passing_one_does_not():
    ts = on_one_page({"id": "f", "test_type": "present", "tags": [], "args": text("Total due 40")},
                     {"id": "g", "test_type": "present", "tags": [], "args": text("Total")})
    f, g = score({"html": "<p>Intro. Total dew 41 now</p>"}, ts)
    assert (f.result, g.result) == ("fail", "pass")
    assert f.why.startswith("'Total due 40' not found (best 0.") and "; closest 'total dew 41'" in f.why
    assert g.why == ""


def test_the_closest_text_is_cut_to_120_characters():
    long = on_one_page({"id": "l", "test_type": "present", "tags": [], "args": text("word " * 60)})
    (v,) = score({"html": "<p>" + "other " * 60 + "</p>"}, long)
    assert v.why.endswith("…'") and len(v.why.split("; closest ", 1)[1]) == 120 + 2     # the text, quoted


def test_the_closest_text_of_glued_words_comes_from_the_squeezed_text():
    ts = on_one_page({"id": "s", "test_type": "present", "tags": [], "args": text("net total due")})
    (v,) = score({"html": "<p>nettotaldue</p>"}, ts)
    assert v.result == "pass"
    ts = on_one_page({"id": "s", "test_type": "present", "tags": [], "args": text("net total due 40")})
    (v,) = score({"html": "<p>nettotaldue 41</p>"}, ts)
    assert v.result == "fail" and "; closest 'nettotaldue4'" in v.why


def test_documents_count_each_document_once_across_its_pages():
    pages = [dataclasses.replace(PAGE, page_id=i, document=d, suite="s") for i, d in
             (("p1", "d1"), ("p2", "d1"), ("p3", "d2"))]
    base = {"test_type": "present", "output_type": "html", "derivation": "authored", "tags": ["eng"]}
    xs = [base | {"page_id": p.page_id, "document": p.document, "suite": p.suite, "test_id": p.page_id,
                  "result": r} for p, r in zip(pages, ("pass", "fail", "pass"), strict=True)]
    s = summarize(xs)
    assert s["per_tag"]["eng"] == {"score": 2 / 3, "tests": 3, "documents": 2}
    assert s["per_suite"]["s"] == {"score": 2 / 3, "tests": 3, "documents": 2}


def test_a_test_line_without_suite_tags_or_derivation_is_still_summarized():
    s = summarize([{"document": "d", "test_type": "present", "result": "pass"}])
    assert s["score"] == 1.0 and _slices(s) == {k: {} for k in SLICED} | {"per_test_type": {
        "present": {"score": 1.0, "tests": 1, "documents": 1}}}


def test_a_slice_of_test_lines_is_summarized_the_same_way():
    """Any other breakdown, such as one tag, is the same summary over the lines selected."""
    eng = [x for x in lines(score({"html": "<p>alpha beta</p>"}, TESTS), TESTS) if "eng" in x["tags"]]
    assert summarize(eng)["families"]["text"] == {"score": 2 / 3, "tests": 3, "documents": 1}


def test_scores_are_floats_even_when_every_test_agrees():
    s = summarize(lines(score({"html": "<p>alpha beta</p>"}, TESTS[:2]), TESTS))
    assert type(s["score"]) is float and type(s["families"]["text"]["score"]) is float


def test_a_pages_line_holds_its_counts_and_its_details_every_verdict():
    s = scorer.UnitTests().score({"html": "<p>alpha beta</p>"}, TESTS)
    assert s.result == {"tests": 5, "passed": 2, "per_family": {"text": {"tests": 5, "passed": 2}},
                        "per_tag": {"eng": {"tests": 3, "passed": 2}, "table": {"tests": 1, "passed": 0},
                                    "form": {"tests": 1, "passed": 0}, "math": {"tests": 1, "passed": 0}},
                        "per_test_type": {"present": {"tests": 5, "passed": 2}},
                        "per_arg_kind": {"text": {"tests": 4, "passed": 2},
                                         "latex": {"tests": 1, "passed": 0}},
                        "per_derivation": {"authored": {"tests": 5, "passed": 2}}}
    assert s.details[2] == {"test_id": "c", "test_type": "present", "output_type": "html",
                            "derivation": "authored", "tags": ["eng", "table"], "args": text("gamma"),
                            "settings": {}, "result": "fail", "why": s.details[2]["why"]}


def test_unit_tests_names_its_headline():
    line = {"id": "p", "row": {"document": "d"}, "tests": 1, "passed": 1,
            "per_family": {"text": {"tests": 1, "passed": 1}}}
    assert scorer.UnitTests.headline == "score"
    s = scorer.UnitTests().summarize([line])     # a line kept before the slices were adds nothing to them
    assert (s["score"], s["families"]) == (1.0, {"text": {"score": 1.0, "tests": 1, "documents": 1}})
    assert _slices(s) == {k: {} for k in SLICED}


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
    assert h["score"] == (2 / 3 + 0) / 2   # each family weighs the same, however many tests it has
    only_text = summarize(lines(score({"html": "<p>alpha beta</p>"}, tests[:3]), tests))
    assert set(only_text["families"]) == {"text"}   # a family with no verdicts isn't in it


def test_arg_kinds_are_how_a_tests_content_is_compared():
    kinds = gold.arg_kinds
    assert kinds("present", text("a")) == ("text",)
    assert kinds("present", {"content": {"number": "3.5"}}) == ("number",)
    assert kinds("present", {"content": {"latex": "x^2"}}) == ("latex",)
    # several args of one kind count it once; order and table_cell take only text
    t0, t1 = {"text": "N", "max_diffs": 0}, {"text": "n", "max_diffs": 0}
    cell = {"cell": {"text": "7", "max_diffs": 0}, "headings": [t0, t1]}
    assert kinds("table_cell", cell) == ("text",)
    assert kinds("order", {"before": t0, "after": t1}) == ("text",)
    # mixed kinds, were a test type to take them, come in the order text, number, latex
    mixed = {"x": {"latex": "x"}, "y": {"number": "1"}, "z": t0}
    assert kinds("present", mixed) == ("text", "number", "latex")
    # a layout test's text only labels its place, so it is compared by no kind
    assert kinds("layout_kind", {"content": {"text": "x", "max_diffs": 0, "place": [[0, 0, 1, 1]]}}) == ()


def test_the_arg_kind_slice_counts_a_test_under_each_kind_and_leaves_layout_out():
    tests = on_one_page(
        {"id": "t", "test_type": "present", "tags": ["eng"], "args": text("alpha")},
        {"id": "n", "test_type": "present", "tags": ["eng"], "args": {"content": {"number": "12"}}},
        {"id": "c", "test_type": "table_cell", "tags": ["table"],
         "args": {"cell": {"text": "12", "max_diffs": 0}, "headings": [{"text": "alpha", "max_diffs": 0}]}},
        {"id": "l", "test_type": "layout_kind", "output_type": "blocks", "tags": ["eng"],
         "args": {"content": {"text": "alpha", "max_diffs": 0, "place": [[0.1, 0.1, 0.5, 0.2]]}},
         "settings": {"kind": "text"}})
    s = summarize(lines(score({"html": "<p>alpha 12</p>"}, tests), tests, (dataclasses.replace(
        PAGE, outputs=("html", "blocks")),)))
    assert s["per_arg_kind"]["text"]["tests"] == 2       # the present text test and the table cell
    assert s["per_arg_kind"]["number"]["tests"] == 1     # the present number test
    assert "latex" not in s["per_arg_kind"] and sum(e["tests"] for e in s["per_arg_kind"].values()) == 3
