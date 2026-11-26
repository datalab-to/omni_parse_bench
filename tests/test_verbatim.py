# ruff: noqa: E501
"""`verbatim`: what a gold file may say, and the verdicts it gives on closed stretches of a page: blank fields,
the end of a table, captions and whole short pages, written right, padded, filled, duplicated or split
(docs/scoring/verbatim.md)."""
from __future__ import annotations

import pytest

from omni_parse_bench import markdown, score, views
from omni_parse_bench.scorers.unit_tests import runners as R
from omni_parse_bench.scorers.unit_tests import tests as gold

DOB, POB = "Date of birth:", "Place of birth:"


def text(s: str, md: int = 0) -> dict:
    return {"text": s, "max_diffs": md}


def gold_of(args: dict, settings: dict | None = None) -> tuple[gold.Test, ...]:
    return gold.parse("p", {"tests": [{"id": "a", "test_type": "verbatim", "output_type": "html",
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
    assert isinstance(p, R.Verbatim)
    assert (p.start, p.end) == tuple(args[r]["text"] if r in args else None for r in ("start", "end"))
    assert (p.content, p.max_diffs) == ((args["content"]["text"], args["content"]["max_diffs"])
                                        if "content" in args else (None, 0))
    assert gold.arg_kinds("verbatim", args) == (("text",) if args else ())


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
        "'acme corp annual report' (6 edits, max_diffs 0)")
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


@pytest.mark.parametrize("got, want", [
    ("Total 12 500", "Total 12500"), ("Total 12500 1", "Total 12500"), ("Total 1250", "Total 12500"),
    ("Total 12,500", "Total 12500"), ("Total 125OO", "Total 12500"), ("Net +12.5", "Net -12.5"),
    ("Net 12.5", "Net -12.5"), ("Rate 1,25", "Rate 1.25"), ("Rate 125", "Rate 1.25"), ("Up 5", "Up 5%"),
    ("Rate 5", "Rate .5"), ("Rate .5", "Rate 5"), ("Net +.5", "Net -.5"),
])
def test_numbers_are_exact_at_any_budget(got, want):
    assert verdict(f"<p>{want}</p>", None, None, want, md=2)[0]
    ok, _ = verdict(f"<p>{got}</p>", None, None, want, md=2)
    # Note: "12,500" keeps the digits but adds a comma (one edit, within the budget); its runs differ: 12, 500
    assert not ok


def test_a_run_of_white_space_is_one_space_and_a_word_boundary_is_text():
    assert verdict("<p>Total \n  12 500</p>", None, None, "Total 12 500")[0]
    assert verdict("<p>Total<br>12 500</p>", None, None, "Total 12 500")[0]
    for got, want in (("To tal 12 500", "Total 12 500"), ("Total 12500", "Total 12 500"),
                      ("TotalDue", "Total Due"), ("into", "in to"), ("in to", "into")):
        assert not verdict(f"<p>{got}</p>", None, None, want)[0], (got, want)


@pytest.mark.parametrize("got", ["A self-aware system", "A self- aware system", "A self-\naware system",
                                 "A self-<br>aware system"])
def test_a_hyphen_a_line_broke_after_may_be_kept_or_joined(got):
    assert verdict(f"<p>{got}</p>", None, None, "A self-aware system")[0]
    # Note: a hyphen a line broke after may also be the line's own, so the gold may hold the word joined
    assert verdict(f"<p>{got}</p>", None, None, "A selfaware system")[0] is (got != "A self-aware system")


@pytest.mark.parametrize("got, want", [
    ("resign the contract", "re-sign the contract"), ("re-sign the contract", "resign the contract"),
    ("A selfaware system", "A self-aware system"), ("foobar", "foo_bar"), ("foo_bar", "foobar"),
    ("foo bar", "foo_bar"),
])
def test_a_hyphen_or_an_underscore_inside_a_word_is_text(got, want):
    assert not verdict(f"<p>{got}</p>", None, None, want)[0]
    assert verdict(f"<p>{want}</p>", None, None, want)[0]


def test_a_printed_underscore_line_is_not_compared():
    assert verdict(form("__/__/____"), content="__/__/____")[0]
    assert verdict(form("//"), content="__/__/____")[0]
    assert verdict(form("___ (signature)"), content="(signature)")[0]
    assert not verdict(form("12/03/1985"), content="__/__/____")[0]


def test_a_footnote_marker_is_content():
    page = "<p>Abstract</p><p>We study parsing.<sup>1</sup></p><p>Introduction</p>"
    assert not verdict(page, "Abstract", "Introduction", "We study parsing.")[0]
    # Note: the text view writes a superscript as a word of its own, so the content does too
    assert verdict(page, "Abstract", "Introduction", "We study parsing. 1")[0]
    assert not verdict(page, "Abstract", "Introduction", "We study parsing.1")[0]


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


def test_an_anchor_is_counted_as_the_scorer_finds_it():
    page = "Date of birth: 1985\nMother's Date of birth: 1960\nBirthdate of birth: x\nDate of birth:s"
    # Note: inside "Birthdate" is not at a word edge; after "birth:" a word edge is the colon itself
    assert R.verbatim_anchor_copies(page, DOB) == 3
    assert R.verbatim_anchor_copies("Report 2024 | p. 3\nThe report", "Report") == 2
    assert R.verbatim_anchor_copies("Place of birth: Paris", POB) == 1
    assert R.verbatim_anchor_copies("PlaceOfBirth: Paris", POB) == 0


def test_white_space_inside_an_anchor_or_the_region_is_one_space():
    page = "<pre>Date  of\n\n birth:   12\n\n  500 Place of birth:</pre>"
    assert verdict(page, content="12 500")[0]


def test_a_list_bullet_inside_a_line_is_not_compared():
    assert verdict("<p>Items: • Rent ‣ Fuel</p>", None, None, "Items: Rent Fuel")[0]
    assert not verdict("<p>Items: * Rent - Fuel</p>", None, None, "Items: Rent Fuel")[0]
    # Note: a bullet glued to its word is text, and costs an edit
    assert not verdict("<p>Items: •Rent</p>", None, None, "Items: Rent")[0]
    assert verdict("<p>Items: •Rent</p>", None, None, "Items: Rent", md=1)[0]


def test_a_swap_costs_one_edit_beside_a_line_hyphen_too():
    # Note: two paths count edits, one for text with a hyphen a line broke and one without; both count a swap
    # of two adjacent characters as one edit
    for page in ("<p>Teh self-aware unit</p>", "<p>Teh self-<br>aware unit</p>"):
        assert verdict(page, None, None, "The self-aware unit", md=1)[0], page
        assert not verdict(page, None, None, "The self-aware unit")[0], page


@pytest.mark.parametrize("got, want", [
    ("re- sign", "re sign"), ("self-\naware", "self aware"), ("x -.5", "x +.5"), ("x .5", "x 5"), ("x 5", "x .5"),
    ("token", "_token"), ("_token", "token"), ("foo bar", "foo___bar"), ("foo__bar", "foo___bar"), ("init", "__init__"),
    ("Anglo- Saxon", "Anglo-Saxon"),
])
def test_a_zero_edit_region_changes_no_text(got, want):
    assert not verdict(f"<p>{got}</p>", None, None, want)[0]
    assert verdict(f"<p>{want}</p>", None, None, want)[0]


def test_a_line_end_hyphen_is_one_unit_kept_or_joined():
    for want, ok in (("re-sign", True), ("resign", True), ("re sign", False), ("re- sign", True)):
        assert verdict("<p>re-<br>sign</p>", None, None, want)[0] is ok, want
    # Note: the gold may hold the line break too, from a text layer; either side may drop it or read it as a hyphen
    for got, ok in (("re-sign", True), ("resign", True), ("re sign", False), ("re-<br>sign", True)):
        assert verdict(f"<p>{got}</p>", None, None, "re-\nsign")[0] is ok, got


def test_an_anchor_is_found_under_fold_and_only_there():
    page = "<p>Date of self-<br>aware birth: </p><p>Place of birth:</p>"
    assert verdict(page, "Date of selfaware birth:", POB)[0]
    assert not verdict(page, "Date of self aware birth:", POB)[0]
    assert R.verbatim_anchor_copies("A self-\naware x", "selfaware") == 1
    assert R.verbatim_anchor_copies("A self-\naware x", "self-aware") == 0


@pytest.mark.parametrize("anchor", ["Self-aware systems", "Date of self-aware birth:", "Self-", "SELF‐AWARE"])
@pytest.mark.parametrize("role", ["start", "end"])
def test_an_anchor_with_a_hyphen_after_a_letter_is_refused(anchor, role):
    with pytest.raises(ValueError, match="hyphen after a letter"):
        gold_of({role: text(anchor), "content": text("x")})


def test_why_a_hyphen_after_a_letter_cannot_be_an_anchor():
    # Note: the loader refuses it, since a faithful page that breaks the line at the hyphen does not hold it
    t = R.Verbatim("Self-aware systems", None, "Learn.", 0)
    assert R.verbatim(t, views.html("<h1>Self-aware systems</h1><p>Learn.</p>"))[0]
    assert not R.verbatim(t, views.html("<h1>Self-<br>aware systems</h1><p>Learn.</p>"))[0]


@pytest.mark.parametrize("anchor", ["3-D model", "pages 10-12", "COVID 19", "Name -"])
def test_a_hyphen_after_no_letter_may_be_in_an_anchor(anchor):
    [t] = gold_of({"start": text(anchor), "content": text("x")})
    assert t.params.start == anchor


@pytest.mark.parametrize("got, want", [
    ("Concentration 1e+3 M", "Concentration 1e-3 M"), ("Concentration 1e3 M", "Concentration 1e-3 M"),
    ("Concentration 1 -3 M", "Concentration 1e-3 M"), ("Rate 1 3", "Rate 1e3"), ("Rate 2.5e4", "Rate 2.5e+4"),
    ("Readings 10+12", "Readings 10-12"), ("Net +5", "Net -5"), ("Net 5", "Net -5"), ("x -5", "x +5"),
])
def test_a_number_with_its_sign_and_exponent_is_exact_at_any_budget(got, want):
    ok, why = verdict(f"<p>{got}</p>", None, None, want, 1)
    assert not ok and why.endswith("(a number differs)"), why
    assert verdict(f"<p>{want}</p>", None, None, want, 1)[0]


@pytest.mark.parametrize("got, want", [("Strain COVID 19", "Strain COVID-19"), ("Δ+12", "Δ-12"), ("A+12", "A-12")])
def test_a_hyphen_after_a_letter_is_no_sign(got, want):
    # Note: as the number guard of `present` reads it: "COVID-19" holds a hyphen, so a space costs one edit
    assert verdict(f"<p>{got}</p>", None, None, want, 1)[0]
    assert not verdict(f"<p>{got}</p>", None, None, want, 0)[0]


@pytest.mark.parametrize("got, want, md", [("pages 10–12", "pages 10-12", 0), ("12/05/2021", "12-05-2021", 2)])
def test_a_hyphen_after_a_digit_joins_two_numbers(got, want, md):
    assert verdict(f"<p>{got}</p>", None, None, want, md)[0]


@pytest.mark.parametrize("got, want", [("token", "token____"), ("token____", "token"), ("set token now", "set token____ now"), ("token", "____token"),
                                       ("____token", "token"), ("foo bar", "foo___bar"), ("foobar", "foo___bar")])
def test_an_underscore_run_touching_a_letter_on_either_side_is_text(got, want):
    assert not verdict(f"<p>{got}</p>", None, None, want)[0]
    assert verdict(f"<p>{want}</p>", None, None, want)[0]


@pytest.mark.parametrize("got", ["Name: ____", "Name: ", "Name:______ ", "Name: ____  ______"])
def test_an_underscore_run_touching_no_letter_is_a_line_to_write_on(got):
    assert verdict(f"<p>{got}</p>", None, None, "Name:")[0]


def test_a_nul_is_refused_in_the_gold_and_read_as_a_replacement_on_the_page():
    with pytest.raises(ValueError, match="NUL"):
        gold_of({"content": text("re\x00sign")}, None)
    assert not verdict("<p>re\x00sign</p>", None, None, "resign")[0]
    assert not verdict("<p>re\x00sign</p>", None, None, "re-sign")[0]
