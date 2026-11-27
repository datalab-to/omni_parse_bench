# ruff: noqa: E501
"""Negative tests need an output: `present` with `{"absent": true}`, `no_excess_repeats` and `layout_absent` fail an output that
writes nothing, unless the page's gold says it is blank (a `page_near_empty` test). docs/scoring/README.md, "Empty output"."""
from __future__ import annotations

import pytest

from omni_parse_bench import score
from omni_parse_bench.scorers.unit_tests import tests as gold

H = "Johnathan Quincy Smithers"
PAGE = "The committee met on Monday to review the budget and the plans for the new library downtown."


def t(test_type, args, settings=None, output="html", i="a"):
    return {"id": i, "test_type": test_type, "output_type": output, "derivation": "authored", "tags": [],
            "args": args, "settings": settings or {}}


NEGATIVE = {
    "absent": (t("present", {"content": {"text": H, "max_diffs": 0}}, {"absent": True}), "html"),
    "no_excess_repeats": (t("no_excess_repeats", {"content": {"text": PAGE, "max_diffs": 0}}), "html"),
    "layout_absent": (t("layout_absent", {}, {"kinds": ["table"]}, output="blocks"), "blocks"),
}
BLANK = t("page_near_empty", {}, {"max_chars": 20}, i="blank")
EMPTY = {"html": "", "blocks": []}
WRITTEN = {"html": f"<p>{PAGE}</p>", "blocks": [{"label": "text", "bbox": [0, 0, 1, 1], "text": PAGE}]}


def verdict(name, pred, blank=False):
    test, _ = NEGATIVE[name]
    g = gold.parse("p", {"tests": [test] + ([BLANK] if blank else [])})
    return {r.id: r for r in score(pred, g)}["a"]


@pytest.mark.parametrize("name", NEGATIVE)
def test_an_empty_output_fails_on_a_normal_page(name):
    r = verdict(name, EMPTY)
    assert r.result == "fail" and r.why.startswith("no output")


@pytest.mark.parametrize("name", ["absent", "no_excess_repeats"])
@pytest.mark.parametrize("html", [" ", "<p> </p><br>", "<img src='scan.png' alt='a long description of a scan'>"])
def test_an_output_with_nothing_to_read_is_empty(name, html):
    assert verdict(name, {"html": html}).result == "fail"


@pytest.mark.parametrize("name", NEGATIVE)
def test_an_empty_output_passes_on_a_blank_page(name):
    assert verdict(name, EMPTY, blank=True).result == "pass"


@pytest.mark.parametrize("name", NEGATIVE)
def test_an_output_that_avoids_the_banned_reading_still_passes(name):
    assert verdict(name, WRITTEN).result == "pass"


def test_the_banned_reading_still_fails_where_it_is_written():
    r = verdict("absent", {"html": f"<p>{H}</p>"})
    assert r.result == "fail" and "found" in r.why


def test_a_missing_output_is_not_a_blank_page():
    assert verdict("absent", {}, blank=False).why == "no html output"


def test_a_blank_page_does_not_excuse_a_written_banned_reading():
    assert verdict("absent", {"html": f"<p>{H}</p>"}, blank=True).result == "fail"


def test_a_page_with_layout_absent_needs_a_page_near_empty_test(tmp_path):
    import json

    from omni_parse_bench import data
    from omni_parse_bench.scorers import unit_tests as scorer

    def page(name, tests, outputs):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps({"tests": tests}))
        return data.Page(name, name, "s", tmp_path / f"{name}.png", path, outputs)

    absent = NEGATIVE["layout_absent"][0]
    with pytest.raises(ValueError, match="page_near_empty"):
        scorer.gold(page("a", [absent], ("blocks",)))
    assert scorer.gold(page("b", [absent, BLANK], ("blocks", "html")))
