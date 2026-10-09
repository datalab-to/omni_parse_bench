"""gold.test: what a test must be to load."""
from __future__ import annotations

import pytest

from omni_parse_bench import gold


def present(tags: list[str]) -> dict:
    return {"id": "t", "test_type": "present", "output_type": "html", "derivation": "authored", "tags": tags,
            "args": {"content": {"text": "a", "max_diffs": 0}}, "settings": {}}


def test_a_tag_is_a_vocabulary_tag_a_language_or_a_script():
    assert gold.test("p", present(["table", "eng", "Latn"])).tags == ("table", "eng", "Latn")
    for bad in ("english", "none", "language", "LATN"):
        with pytest.raises(gold.GoldError, match="unknown tags"):
            gold.test("p", present([bad]))


def with_args(args: dict, test_type: str = "present", settings: dict | None = None, **fields) -> dict:
    output = {"present": "html", "order": "html", "repeat": "html"}[test_type]
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
    with_args({"content": {"text": "abc", "max_diffs": 0}}, id=7),
    with_args({"content": {"text": "abc", "max_diffs": 0}}, id=" "),
])
def test_a_bad_arg_or_setting_is_refused(t):
    with pytest.raises(gold.GoldError):
        gold.test("p", t)


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
    with pytest.raises(gold.GoldError, match=why) as e:
        gold.test("p", with_args({"content": {"latex": latex}}))
    assert "test 't'" in str(e.value) and repr(latex)[:20] in str(e.value)
