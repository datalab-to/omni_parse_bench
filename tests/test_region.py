# ruff: noqa: E501
"""`region`: what a gold file may say, and the verdicts it gives on closed stretches of a page: blank fields,
the end of a table, captions and whole short pages, written right, padded, filled, duplicated or split
(docs/scoring/region.md)."""
from __future__ import annotations

import pytest

from omni_parse_bench import markdown, score
from omni_parse_bench.scorers.unit_tests import runners as R
from omni_parse_bench.scorers.unit_tests import tests as gold

DOB, POB = "Date of birth:", "Place of birth:"


def text(s: str, md: int = 0) -> dict:
    return {"text": s, "max_diffs": md}


def gold_of(args: dict, settings: dict | None = None) -> tuple[gold.Test, ...]:
    return gold.parse("p", {"tests": [{"id": "a", "test_type": "region", "output_type": "html",
                                       "derivation": "authored", "tags": [], "args": args,
                                       "settings": settings or {}}]})


def verdict(html: str, start: str | None = DOB, end: str | None = POB, content: str | None = None,
            md: int = 0) -> tuple[bool, str]:
    args = {r: text(x) for r, x in (("start", start), ("end", end)) if x is not None}
    if content is not None:
        args["content"] = text(content, md)
    r = score({"html": html}, gold_of(args))[0]
    return r.result == "pass", r.why


def form(value: str) -> str:
    return f"<p>Name: Ann Lee</p><p>Date of birth: {value}</p><p>Place of birth: Paris</p>"


# ------------------------------------------------------------------------------------------- the loader


@pytest.mark.parametrize("args", [
    {}, {"start": text("a b")}, {"end": text("a b")}, {"content": text("a b", 1)},
    {"start": text(DOB), "end": text(POB)}, {"start": text(DOB), "end": text(POB), "content": text("12 May", 2)},
])
def test_the_loader_takes_any_mix_of_the_three_roles(args):
    [t] = gold_of(args)
    p = t.params
    assert isinstance(p, R.Region)
    assert (p.start, p.end) == tuple(args[r]["text"] if r in args else None for r in ("start", "end"))
    assert (p.content, p.max_diffs) == ((args["content"]["text"], args["content"]["max_diffs"])
                                        if "content" in args else (None, 0))
    assert gold.arg_kinds("region", args) == (("text",) if args else ())


@pytest.mark.parametrize("args, settings, why", [
    ({"start": text(DOB, 1)}, {}, "start is matched exactly"),
    ({"end": text(POB, 1)}, {}, "end is matched exactly"),
    ({"start": {"text": DOB, "max_diffs": 0, "exact_case": True}}, {}, "exact_case"),
    ({"content": {"text": "x y", "max_diffs": 0, "place": [[0, 0, 1, 1]]}}, {}, "is a text arg"),
    ({"content": {"number": "12"}}, {}, "is a text arg"),
    ({"content": text("ab", 2)}, {}, "max_diffs must be a whole number from 0 to 1"),
    ({"content": text("___")}, {}, "something left after folding"),
    ({"start": text("Total"), "end": text("TOTAL")}, {}, "start and end must differ"),
    ({"start": text("Total"), "content": text("Total due 12")}, {}, "holds its start"),
    ({"end": text("Mean"), "content": text("the mean value")}, {}, "holds its end"),
    ({"start": text(DOB)}, {"max_diffs": 1}, "no settings expected"),
    ({"middle": text(DOB)}, {}, "has no role"),
])
def test_the_loader_refuses_what_a_region_cannot_check(args, settings, why):
    with pytest.raises(ValueError, match=why):
        gold_of(args, settings)


def test_a_content_word_that_only_starts_like_an_anchor_is_allowed():
    # Note: an anchor inside a longer word is no copy, so it cannot cut the region.
    [t] = gold_of({"end": text("Mean"), "content": text("Meanwhile, nothing")})
    assert t.params.content == "Meanwhile, nothing"


# ------------------------------------------------------------------------------------------- blank fields


@pytest.mark.parametrize("value", ["", " ", "&nbsp;", "<br>", "____", ".....", "…", "<span></span>",
                                   "<input type=text>", "​", "<b></b>"])
def test_a_blank_field_passes_however_the_blank_is_written(value):
    assert verdict(form(value)) == (True, "")


@pytest.mark.parametrize("value", ["N/A", "-", "—", "0", "x", "none", "[blank]", "☐", "12/03/1985",
                                   "<sup>1985</sup>", "<table><tr><td>1985</td></tr></table>"])
def test_anything_written_in_a_blank_field_fails(value):
    ok, why = verdict(form(value))
    assert not ok and why.startswith(f"between {DOB!r} and {POB!r} holds "), why


def test_the_printed_mask_is_the_content_and_markdown_may_read_it_as_emphasis():
    md = markdown.to_html(f"Name: Ann Lee\n\n{DOB} __/__/____\n\n{POB} Paris")
    assert verdict(md, content="__/__/____") == (True, "")
    assert verdict(form("__/__/____"), content="__/__/____") == (True, "")
    assert not verdict(form("12/03/1985"), content="__/__/____")[0]


@pytest.mark.parametrize("html", [
    form("") + form("1985"), form("1985") + form(""),
    "<table><tr><td>Date of birth:</td><td></td><td>1985</td></tr><tr><td>Place of birth:</td></tr></table>",
    "<table><tr><td>Date of birth:</td></tr></table><table><tr><td>1985</td></tr></table><p>Place of birth:</p>",
    "<p>Dateofbirth:1985 Placeofbirth: Paris</p>",
    "<p>Mother's Date of birth: 1985</p><p>Place of birth: Paris</p>",
])
def test_the_holes_of_an_any_copy_guard_are_closed(html):
    # Note: each of these passes a guard that judges only some copy of the label, or only its first cell.
    assert not verdict(html)[0]


def test_every_copy_of_the_start_is_judged_and_each_is_named():
    ok, why = verdict(form("") + form("1985") + form("1990"))
    assert not ok
    assert why == (f"copy 2 of 3: between {DOB!r} and {POB!r} holds '1985' where the gold has nothing "
                   "(4 edits, max_diffs 0) (and 1 more)")
    assert verdict(form("") * 3) == (True, "")


# ------------------------------------------------------------------------------------------- anchors


@pytest.mark.parametrize("html, why", [
    ("<p>Place of birth: Paris</p>", f"start {DOB!r} not found whole, at a word edge"),
    ("<p>Date of birth:</p>", f"end {POB!r} not found whole, at a word edge"),
    ("<p>Place of birth:</p><p>Date of birth:</p>", f"no end {POB!r} after start {DOB!r}"),
    ("<p>XDate of birth:</p><p>Place of birth:</p>", f"start {DOB!r} not found whole, at a word edge"),
])
def test_a_missing_anchor_fails_with_its_reason(html, why):
    assert verdict(html) == (False, why)


def test_a_start_inside_a_longer_end_belongs_to_the_end():
    page = "<p>Table 3</p><p>Rent 100</p><p>Table 3 (continued)</p><p>Fuel 70</p>"
    assert verdict(page, "Table 3", "Table 3 (continued)", "Rent 100") == (True, "")


def test_without_anchors_the_region_is_the_page():
    assert verdict("<p>Page intentionally<br>left blank</p>", None, None, "Page intentionally left blank")[0]
    assert not verdict("<p>Page intentionally left blank. Nothing here.</p>", None, None,
                       "Page intentionally left blank")[0]
    assert verdict("", None, None) == (True, "")
    assert verdict("<img alt='a stamp'>", None, None) == (True, "")
    assert not verdict("<p>.</p>", None, None)[0]


def test_from_the_page_start_and_to_the_page_end():
    page = "<p>ACME Corp</p><p>Annual report</p><h1>Results</h1><p>We grew.</p>"
    assert verdict(page, None, "Results", "ACME Corp Annual report")[0]
    assert verdict("<p>Draft</p>" + page, None, "Results", "ACME Corp Annual report")[1] == (
        "from the page start to 'Results' holds 'draft acme corp annual report' where the gold has "
        "'acme corp annual report' (5 edits, max_diffs 0)")
    assert verdict(page, "Results", None, "We grew.")[0]
    assert verdict(page + "<p>We grew.</p>", "Results", None, "We grew.")[1].startswith(
        "after 'Results' to the page end holds")


# ------------------------------------------------------------------------------------------- the comparison


def test_the_region_is_compared_whole_not_searched():
    # Note: a present test passes on any page that holds its text; a region fails on one that holds more.
    page = "<p>Table 3 Results of the trial. Source: WHO</p><p>Mean</p>"
    assert R.present(R.Present(R.Text("Results of the trial", 0)), R.views.html(page))[0]
    assert not verdict(page, "Table 3", "Mean", "Results of the trial", md=3)[0]


@pytest.mark.parametrize("got, ok", [
    ("Results of the trial", True), ("Results of the trail", True), ("Resultsofthe trial", True),
    ("Results of the tri", True), ("Results of trial", False), ("Results of the trial ok!", False),
])
def test_the_budget_is_spent_over_the_whole_region(got, ok):
    assert verdict(f"<p>Table 3 {got}</p><p>Mean</p>", "Table 3", "Mean", "Results of the trial", md=2)[0] is ok


@pytest.mark.parametrize("got", ["Total 12 500", "Total 12500 1", "Total 1250", "Total 12,500", "Total 125OO"])
def test_numbers_are_exact_at_any_budget(got):
    ok, _ = verdict(f"<p>{got}</p>", None, None, "Total 12500", md=2)
    # Note: "12,500" keeps the digits but adds a comma (one edit, within the budget); its runs differ: 12, 500
    assert not ok


def test_a_space_between_digits_is_content_and_other_spacing_is_not():
    assert verdict("<p>Total   12 500</p>", None, None, "Total 12 500")[0]
    assert verdict("<p>To tal 12 500</p>", None, None, "Total 12 500")[0]
    assert not verdict("<p>Total 12500</p>", None, None, "Total 12 500")[0]


@pytest.mark.parametrize("got", ["A self-aware system", "A self- aware system", "A selfaware system",
                                 "A self-\naware system"])
def test_a_hyphen_between_letters_may_be_kept_or_dropped(got):
    assert verdict(f"<p>{got}</p>", None, None, "A self-aware system")[0]


def test_a_footnote_marker_is_content():
    page = "<p>Abstract</p><p>We study parsing.<sup>1</sup></p><p>Introduction</p>"
    assert not verdict(page, "Abstract", "Introduction", "We study parsing.")[0]
    assert verdict(page, "Abstract", "Introduction", "We study parsing.1")[0]


def test_an_image_description_is_not_read_and_an_empty_element_is_nothing():
    assert verdict(form("<img alt='12/03/1985'>")) == (True, "")
    assert verdict(form("<math></math><ol><li></li></ol><input type=hidden value=1985>")) == (True, "")


def test_a_region_runs_across_a_table_and_past_its_end():
    table = "<table><tr><td>Rent</td><td>100</td></tr><tr><td>Fuel</td><td>70</td></tr></table>"
    assert verdict(f"<p>Table 2</p>{table}<p>The costs fell.</p>", "Table 2", "The costs fell", "Rent 100 Fuel 70")[0]
    assert verdict(f"{table}<p>The costs fell.</p>", "Fuel 70", "The costs fell")[0]
    for extra in ("<p>Total 170</p>", "<table><tr><td>Tax</td><td>9</td></tr></table>", "<p>* estimated</p>"):
        assert not verdict(f"{table}{extra}<p>The costs fell.</p>", "Fuel 70", "The costs fell")[0], extra
    split = "<table><tr><td>Rent</td><td>100</td></tr></table><table><tr><td>Fuel</td><td>70</td></tr></table>"
    assert verdict(f"<p>Table 2</p>{split}<p>The costs fell.</p>", "Table 2", "The costs fell", "Rent 100 Fuel 70")[0]


def test_a_long_page_is_graded_quickly():
    import time
    body = " ".join(f"word{i}" for i in range(3000))
    t0 = time.perf_counter()
    assert verdict(f"<p>{body}</p>", None, None, body)[0]
    assert not verdict(f"<p>{body} word1</p>", None, None, body)[0]
    assert time.perf_counter() - t0 < 2
