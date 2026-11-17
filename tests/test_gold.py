"""gold.test: what a test must be to load."""
from __future__ import annotations

import pytest

from omni_parse_bench.scorers.unit_tests import tests as gold


def present(tags: list[str]) -> dict:
    return {"id": "t", "test_type": "present", "output_type": "html", "derivation": "authored", "tags": tags,
            "args": {"content": {"text": "a", "max_diffs": 0}}, "settings": {}}


def test_a_tag_is_a_vocabulary_tag_a_language_or_a_script():
    assert gold.test("p", present(["table", "eng", "Latn"])).tags == ("table", "eng", "Latn")
    for bad in ("english", "none", "language", "LATN"):
        with pytest.raises(ValueError, match="unknown tags"):
            gold.test("p", present([bad]))


def with_args(args: dict, test_type: str = "present", settings: dict | None = None, **fields) -> dict:
    output = {"present": "html", "order": "html", "repeat": "html", "page_near_empty": "html",
              "table_cell": "html", "layout_kind": "blocks"}[test_type]
    return {"id": "t", "test_type": test_type, "output_type": output, "derivation": "authored", "tags": [],
            "args": args, "settings": settings or {}} | fields


@pytest.mark.parametrize("t", [
    with_args({"content": {"text": "abc", "max_diffs": -3}}),
    with_args({"content": {"text": "abc", "max_diffs": "2"}}),
    with_args({"content": {"text": "abc", "max_diffs": True}}),
    with_args({"content": {"text": "abc", "max_diffs": 3}}),
    with_args({"content": {"text": " \u200b ", "max_diffs": 0}}),
    with_args({"content": {"text": "", "max_diffs": 0}}),
    with_args({"content": {"latex": ""}}),
    with_args({"content": {"latex": 3}}),
    with_args({"content": {"number": 2}}),
    with_args({"before": {"text": "ab", "max_diffs": 2}, "after": {"text": "abcdef", "max_diffs": 2}},
              "order"),
    with_args({"content": {"text": "abc", "max_diffs": 0}}, "repeat", {"expected_count": 0}),
    with_args({"content": {"text": "abc", "max_diffs": 0}}, "repeat", {"expected_count": -1}),
    with_args({"content": {"text": "abc", "max_diffs": 0}}, "repeat", {"expected_count": True}),
    with_args({"content": {"text": "abc", "max_diffs": 0, "exact_case": "yes"}}),
    with_args({"content": {"text": "abc", "max_diffs": 0, "exact_case": 1}}),
    with_args({"content": {"text": "abc", "max_diffs": 0, "exact_case": None}}),
    with_args({"content": {"text": "abcdef", "max_diffs": 1, "exact_case": True}}),  # budget
    with_args({"content": {"number": "12", "exact_case": True}}),
    with_args({"content": {"latex": "x", "exact_case": True}}),
    with_args({"content": {"text": "abc", "max_diffs": 0, "exact_case": True}},
              settings={"exact_case": True}),
    with_args({"content": {"text": "abc", "max_diffs": 0}}, settings={"exact_case": True}),
    with_args({"before": {"text": "abc", "max_diffs": 0, "exact_case": True},
               "after": {"text": "xyz", "max_diffs": 0}}, "order"),
    with_args({"content": {"text": "abc", "max_diffs": 0, "exact_case": True}}, "repeat",
              {"expected_count": 1}),
    with_args({"cell": {"text": "abc", "max_diffs": 0, "exact_case": True}}, "table_cell"),
    with_args({"content": {"text": "abc", "max_diffs": 0, "exact_case": True, "place": [[0, 0, 1, 1]]}},
              "layout_kind", {"kind": "text"}),
    with_args({"content": {"text": "abc", "max_diffs": 0}}, id=7),
    with_args({"content": {"text": "abc", "max_diffs": 0}}, id=" "),
])
def test_a_bad_arg_or_setting_is_refused(t):
    with pytest.raises(ValueError):
        gold.test("p", t)


def test_exact_case_is_a_bool_arg_field_of_a_present_text():
    t = gold.test("p", with_args({"content": {"text": "iPhone", "max_diffs": 0, "exact_case": True}}))
    assert t.params.content.exact_case is True
    assert gold.arg_kinds(t.test_type, t.args) == ("text",)
    t = gold.test("p", with_args({"content": {"text": "iPhone", "max_diffs": 0, "exact_case": False}}))
    assert t.params.content.exact_case is False


@pytest.mark.parametrize("limit", [0, 1, 20])
def test_page_near_empty_takes_no_args_and_a_limit(limit):
    t = gold.test("p", with_args({}, "page_near_empty", {"max_chars": limit}))
    assert t.params.max_chars == limit
    assert t.output_type == "html"
    assert gold.arg_kinds(t.test_type, t.args) == ()


@pytest.mark.parametrize("settings", [
    {}, {"max_chars": -1}, {"max_chars": 2.5}, {"max_chars": True}, {"max_chars": "0"},
    {"max_chars": None}, {"max_chars": 0, "extra": 1},
])
def test_page_near_empty_refuses_invalid_settings(settings):
    with pytest.raises(ValueError):
        gold.test("p", with_args({}, "page_near_empty", settings))


def test_page_near_empty_refuses_args_and_non_html_outputs():
    with pytest.raises(ValueError, match="no role"):
        gold.test("p", with_args({"content": {"text": "abc", "max_diffs": 0}},
                                 "page_near_empty", {"max_chars": 20}))
    with pytest.raises(ValueError, match="reads 'html'"):
        gold.test("p", with_args({}, "page_near_empty", {"max_chars": 0}, output_type="blocks"))


def test_max_diffs_may_be_one_less_than_the_folded_text():
    t = gold.test("p", with_args({"content": {"text": "ABC", "max_diffs": 2}}))
    assert t.params.content.max_diffs == 2
    assert gold.test("p", with_args({"content": {"latex": "x^2"}})).params.content.latex == "x^2"


@pytest.mark.parametrize("latex, why", [
    (r"\frac{a}{", "doesn't render"),
    (r"\notacommand x", "doesn't render"),
    (r"\quad", "renders to nothing"),
    (r"\, \;", "renders to nothing"),
])
def test_latex_must_render_to_something(latex, why):
    with pytest.raises(ValueError, match=why) as e:
        gold.test("p", with_args({"content": {"latex": latex}}))
    assert "test 't'" in str(e.value) and repr(latex)[:20] in str(e.value)
