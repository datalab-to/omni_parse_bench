"""Each runner on a hand-written output: the cases each runner's docstring describes."""
from __future__ import annotations

import re

import pytest

from omni_parse_bench import normalize, views
from omni_parse_bench.scorers.unit_tests import runners as R


def html(s: str) -> views.Html:
    return views.html(s)


@pytest.mark.parametrize("prefix", [
    "", " ", "(", "[", "-", "+", "−", "±", "$", "£", "€", "¥", "<", "=", "≈", "~", "×", "/", ":", "_",
])
@pytest.mark.parametrize("dot", ["·", "∙"])
def test_a_leading_raised_decimal_point_matches_a_full_stop(prefix, dot):
    raised, point = f"{prefix}{dot}2480550383", f"{prefix}.2480550383"
    assert normalize.fold(raised) == normalize.fold(point)
    assert R.found(R.Text(raised, 0), html(f"<p>{point}</p>"))[0]
    assert R.found(R.Text(point, 0), html(f"<p>{raised}</p>"))[0]


@pytest.mark.parametrize("text", ["太原·2020", "A·1", "太原∙2020", "A∙1", "(a)·1", "x)·2", "x]·2"])
def test_a_middle_dot_after_a_letter_is_not_a_decimal_point(text):
    assert normalize.fold(text) == text.lower()
    assert not R.found(R.Text(text, 0), html(f"<p>{text.replace('·', '.').replace('∙', '.')}</p>"))[0]


@pytest.mark.parametrize("source, count", [
    ("", 0),
    ("<p> \t\n&nbsp;\u2003</p>", 0),
    ('<img alt="a blank, ruled sheet of paper">', 0),
    ("<p>A caption</p>", 8),
    ("<p>A</p><p>B</p>", 2),
    ('<img alt="description"><p>Invented!</p>', 9),
    ("<p>é 中!</p>", 3),
])
def test_page_near_empty_counts_non_space_characters_outside_alt_text(source, count):
    v = html(source)
    assert R.page_near_empty(R.PageNearEmpty(count), v) == (True, "")
    if count:
        assert R.page_near_empty(R.PageNearEmpty(count - 1), v) == (
            False, f"{count} non-space characters (limit {count - 1})")


def test_present_allows_exactly_the_edits_it_says():
    assert R.present(R.Present(R.Text("a" * 39, 2)), html("<p>" + "a" * 37 + "bb</p>"))[0]
    assert not R.present(R.Present(R.Text("a" * 39, 1)), html("<p>" + "a" * 37 + "bb</p>"))[0]


@pytest.mark.parametrize("gold, page, edits", [
    ("lorem ipsum dolor sit amet", "lorem izpsum dolqor sit amjet", 3),    # 3 letters inserted
    ("lorem ipsum dolor sit amet", "lorem ipsum dolor sit a", 3),          # 3 letters deleted at the end
    ("lorem ipsum dolor sit amet", "lorem ipsu dolr sit amet", 2),         # 2 deleted from a page of the gold
    ("lorem ipsum", "abc xxxem ipsum", 3),                                 # 3 substituted, at the page's end
    ("lorem ipsum", "lorem ipxxx abc", 3),                                 # and at its start
    ("abcdefgh", "zz acdebfgh zz", 2),                                     # b moved 3 places
    ("britian", "a britain b", 1),                                         # two letters swapped: one edit
    ("total", "otatl", 2),                                                 # two swaps
])
def test_present_needs_one_edit_per_edit_at_any_place(gold, page, edits):
    """A present text passes with `max_diffs` equal to the edit distance of its best match (a letter
    substituted, inserted or deleted, or two adjacent letters swapped, is one edit), and fails with one fewer:
    an inserted, deleted, or moved letter, or a text at the edge of the page, gets no discount."""
    def passes(k):
        return R.present(R.Present(R.Text(gold, k)), html(f"<p>{page}</p>"))[0]
    assert passes(edits)
    assert not passes(edits - 1)


@pytest.mark.parametrize("needle, text, passes", [
    ("3 Park Street, Boston, Mass.", "13 Park Street, Boston, Mass.", False),
    ("10 000", "10 0000", False),
    ("05/21/2025", "1205/21/2025", False),
    ("МФО 313399", "МФО 31339969035", False),
    ("1,000", "21,000", False),
    ("1,000", "x 1.1,000", False),
    ("5", "+5", False),
    ("5", "\u22125", False),
    ("12", "12.5", False),
    ("12", "12,5", False),
    ("3 Park Street", "13 Park Street and 3 Park Street", True),
    ("3 Park Street", "3 Park Street and 13 Park Street", True),
    ("-5", "x-5", True),
    ("5", "x-5", True),
    ("5", "a +5", False),
    ("12", "12. Next", True),
    ("12", "ref 12, next", True),
    ("park street 3", "park street 31", False),
    ("Park Street", "Spark Streets", True),
    ("abc 12", "xabc 12", True),
    ("3 Park Street, Boston, Mass.", "3 Park Street, Boston, Mass.", True),
])
def test_an_exact_match_is_not_cut_out_of_a_longer_number(needle, text, passes):
    assert R.present(R.Present(R.Text(needle, 0)), html(f"<p>{text}</p>"))[0] is passes


@pytest.mark.parametrize("text, passes", [
    ("1. Introduction ... 2. Methods", True),
    ("2. Methods ... 1. Introduction", False),
    ("11. Introduction ... 22. Methods", False),
    ("11. Introduction ... 2. Methods", False),
    ("1. Introduction ... 22. Methods", False),
    ("11. Introduction and 1. Introduction ... 2. Methods", True),
    ("1. Intro duction ... 2. Methods", True),
])
def test_order_items_are_not_cut_out_of_a_longer_number(text, passes):
    assert R.order(R.Order("1. Introduction", "2. Methods", 0), html(f"<p>{text}</p>"))[0] is passes


@pytest.mark.parametrize("text, passes", [
    ("Set of 6pcs Summicron used lenses T2.0 then 18mm/f", True),
    ("Set of 6pcs Summicron used lenses t2.018mm/f then 18mm/f", False),
    ("Set of 6pcs Summicron used lenses t2.0 18mm/f", True),
])
def test_order_squeezed_item_is_not_cut_out_of_a_longer_number(text, passes):
    v = html(f"<p>{text}</p>")
    assert R.order(R.Order("Set of 6pcs Summicron used lenses T2.0", "18mm/f", 0), v)[0] is passes


@pytest.mark.parametrize("needle, text, passes", [
    ("7777777 77", "id 7777777777777777777 x", False),
    ("7777777 77", "id 7777777 77 x", True),
    ("26a. Provide", "512 6a. provide", False),
    ("35 \u00b1 6", "35 \u00b1 6 33 \u00b1 8", True),
    ("305357", "3 0 5 3 5 7", False),         # a space splits a number, at any budget
    ("305357", "x 3 0 5 3 5 7 y", False),
])
def test_a_squeezed_match_is_not_glued_to_the_digits_around_it(needle, text, passes):
    assert R.present(R.Present(R.Text(needle, 0)), html(f"<p>{text}</p>"))[0] is passes


def test_a_number_is_strict_on_digits_and_separators():
    v = html("<p>total 1 234 567,89 EUR and 1,234,567.89 USD</p>")
    assert R.found(R.Number("1,234,567.89"), v)[0]
    assert not R.found(R.Number("1,234,567.80"), v)[0]
    assert not R.found(R.Number("1,234,567.89"), html("<p>total 1 234 567,89 EUR</p>"))[0]


@pytest.mark.parametrize("gold, text, passes", [
    ("1,240", "1,240", True),
    ("1,240", "1240", False),
    ("1,240", "1 240", False),
    ("1,240", "1.240", False),
    ("1240", "1,240", False),
    ("1 240", "1\u202f240", True),
    ("12.5", "12,5", False),
    ("8.455", "8.455", True),
    ("8.455", "score 8.455.", True),
    ("8.455", "8,455", False),
    ("8.455", "18.455", False),
    ("8.455", "8.4551", False),
    ("-4.8%", "(\u20134.8 %)", True),
    ("1,240.00", "$1,240.00", True),
])
def test_a_number_matches_separators_as_the_gold_writes_them(gold, text, passes):
    assert R.VALID["present"][0](R.Present(R.Number(gold)))
    assert R.found(R.Number(gold), html(f"<p>{text}</p>"))[0] is passes


@pytest.mark.parametrize("gold, text, passes", [
    ("12.5", "12.5.7", False),
    ("12.5", "12.5,3", False),
    ("12.5", "12,5,3", False),
    ("12.5", "total 12.5", True),
    ("12.5", "12.5. Next", True),
    ("12.5", "(12.5)", True),
    ("12.5", "12.5, then", True),
    ("12.5", "12.55", False),
    ("12", "12.5", False),
    ("12", "12.5.7", False),
    ("12", "12. Next", True),
])
def test_a_number_is_not_cut_out_of_a_longer_decimal(gold, text, passes):
    assert R.found(R.Number(gold), html(f"<p>{text}</p>"))[0] is passes


def test_a_number_keeps_sign_and_percent():
    v = html("<p>change 4.8% and 12.5</p>")
    assert R.found(R.Number("4.8%"), v)[0]
    assert not R.found(R.Number("-4.8%"), v)[0]
    assert not R.found(R.Number("12.5%"), v)[0]


def test_a_number_sees_through_latex():
    v = html(r"<p>mass <math>m_{\text{r}}\,2.8 \times 10^6</math></p>")
    assert R.found(R.Number("2.8"), v)[0]


@pytest.mark.parametrize("token, core", [
    ("1,240.00", "1240.00"), ("(39%)", "39"), ("12,345", "12345"), ("4.500", "4.500"), ("8.455", "8.455"),
    ("0,250", "0.250"), ("16,17", None), ("12,5", None)])
def test_number_reads_separators(token, core):
    n = R.number(token)
    assert (n.core if n else None) == core


def test_order_reads_folded_text():
    v = html("<p>Alpha section</p><p>Beta section</p>")
    assert R.order(R.Order("ALPHA section", "beta SECTION", 1), v)[0]


def test_repeat_does_not_count_a_longer_word():
    v = html("<p>Passive Income and Loss</p><p>Nonpassive Income and Loss</p><p>Passive Income and Loss</p>")
    assert R.repeat(R.Repeat(R.Text("Passive Income and Loss", 0), 2), v)[0]


# Cases: other separators, a longer number, a sign, parentheses, a currency or percent sign, an image
# description; and, strict, a comma, a trailing zero or a moved decimal point make another number.
@pytest.mark.parametrize("gold, count, text, passes", [
    ("1,240", 2, "<p>1,240</p><p>1,240</p>", True),
    ("1,240", 2, "<p>1,240</p>", False),
    ("1,240", 2, "<p>1,240</p><p>1,240</p><p>1,240</p>", False),
    ("1,240", 1, "<p>1,240 and 1240 and 1.240 and 1 240</p>", True),
    ("1,240", 1, "<p>11,240 and 1,2405 and 1,240</p>", True),
    ("1,240", 2, "<p>11,240 and 1,2405 and 1,240</p>", False),
    ("12.5", 2, "<p>12.5, then 12.5. Next, 12.5.7 and 12.5,77</p>", True),
    ("12.5", 1, "<p>(12.5) and $12.5 and 12.5%</p>", False),
    ("12.5", 3, "<p>(12.5) and $12.5 and 12.5%</p>", True),
    ("-4.8%", 1, "<p>-4.8% and 4.8% and \u20134.8 %</p>", False),
    ("-4.8%", 2, "<p>-4.8% and 4.8% and \u20134.8 %</p>", True),
    ("4.8", 1, "<p>-4.8 and 4.8</p>", True),
    ("1,240", 1, "<table><tr><td>1,240</td><td><img alt='1,240'></td></tr></table>", True),
    ("1,000", 1, "<p>1000</p>", False),
    ("1000", 1, "<p>1,000</p>", False),
    ("1,000", 1, "<p>1.000</p>", False),
    ("8.455", 1, "<p>8.4550</p>", False),
    ("8.4550", 1, "<p>8.455</p>", False),
    ("0.50", 1, "<p>0.5</p>", False),
    ("12.50", 1, "<p>1.250</p>", False),
    # lines: a block or a <br> ends a line, a space groups digits within one
    ("500", 1, "<p>Page 12</p><p>500 items</p>", True),
    ("12 500", 1, "<p>Page 12</p><p>500 items</p>", False),
    ("12 500", 1, "<table><tr><td>12</td><td>500</td></tr></table>", False),
    ("12 500", 1, "<p>12<br>500</p>", False),
    ("12 500", 1, "<p>Total 12 500</p>", True),
    ("500", 2, "<p>Total 12 500</p><p>Fee 500</p>", False),
    ("500", 1, "<p>Total 12 500</p><p>Fee 500</p>", True),
    ("000", 2, "<p>1 000 000</p>", False),
    ("12", 1, "<p>12 500</p>", False),
    ("12", 1, "<p>12 5</p>", True),
    ("10", 2, "<p>10<br>10</p>", True),
    ("10", 2, "<p>10 10</p>", True),
    # copies side by side on one line
    ("1,240", 2, "<p>1,240 1,240</p>", True),
    ("1,240", 2, "<p>1,240/1,240</p>", True),
    ("10", 2, "<p>10-10</p>", True),
    ("1,240", 1, "<p>1,240,1,240</p>", False),
    ("5", 1, "<p>5,5</p>", False),
    # digits the page does not print as a number: a footnote mark, a list's numbers
    ("2", 1, "<p>Revenue<sup>2</sup> was 2</p>", True),
    ("1", 1, "<p>Smith[1] scored 1</p>", True),
    ("2", 1, "<ol><li>a</li><li>b 2</li></ol>", True),
    ("2", 2, "<ol><li>a</li><li>b 2</li></ol>", False),
])
def test_repeat_counts_a_number_as_present_finds_it(gold, count, text, passes):
    t = R.Repeat(R.Number(gold), count)
    assert R.VALID["repeat"][0](t)
    ok, why = R.repeat(t, html(text))
    assert ok is passes, why


def test_repeat_of_a_number_says_how_many_copies_it_found():
    ok, why = R.repeat(R.Repeat(R.Number("1,240"), 3), html("<p>1,240</p><p>1,240</p>"))
    assert not ok and why == "'1,240' appears 2x, not 3x"


def test_table_cell_checks_neighbours_and_headings():
    v = html("<table><tr><th>Year</th><th>Total</th></tr><tr><td>2024</td><td>1,240</td></tr></table>")
    assert R.table_cell(R.TableCell("1,240", {"left": "2024", "top_heading": "Total"}, 0), v)[0]
    assert not R.table_cell(R.TableCell("1,240", {"left": "2023"}, 0), v)[0]


HEADED = ("<table><tr><th rowspan='2'>Model</th><th colspan='2'>Univariable</th></tr>"
          "<tr><th>HR</th><th>P</th></tr>"
          "<tr><td>A. Overall</td><td></td><td></td></tr>"
          "<tr><td>Risk</td><td>1.39</td><td>0.120</td></tr></table>")


@pytest.mark.parametrize("output, passes", [
    (HEADED, True),
    # the heading repeated in each column it covers
    (HEADED.replace("<th colspan='2'>Univariable</th>", "<th>Univariable</th><th>Univariable</th>"), True),
    # the heading written once beside an empty cell, as a printed table shows a merged heading
    (HEADED.replace("<th colspan='2'>Univariable</th>", "<th>Univariable</th><th></th>"), True),
    # the same with the top-left corner empty too
    (HEADED.replace("<th rowspan='2'>Model</th><th colspan='2'>Univariable</th></tr><tr>",
                    "<th></th><th>Univariable</th><th></th></tr><tr><th>Model</th>"), True),
    # another heading written beside it: P's column is under that one, not Univariable
    (HEADED.replace("<th colspan='2'>Univariable</th>", "<th>Univariable</th><th>Multivariable</th>"), False),
    # the section row dropped
    (HEADED.replace("<tr><td>A. Overall</td><td></td><td></td></tr>", ""), False),
    # the section row merged across the table
    (HEADED.replace("<td>A. Overall</td><td></td><td></td>", "<td colspan='3'>A. Overall</td>"), True),
])
def test_cell_under_headings_and_section(output, passes):
    t = R.TableCell("0.120", {}, 0, headings=("Univariable", "P"), section="A. Overall")
    assert R.table_cell(t, html(output))[0] is passes


def test_cell_in_row_group():
    merged = ("<table><tr><th>Meeting</th><th>Date</th></tr><tr><td rowspan='2'>Board</td><td>May</td></tr>"
              "<tr><td>June</td></tr></table>")
    # the label written once above an empty cell, as a printed table shows a merged label
    flat = merged.replace(" rowspan='2'", "").replace("<tr><td>June", "<tr><td></td><td>June")
    other = merged.replace(" rowspan='2'", "").replace("<tr><td>June", "<tr><td>Committee</td><td>June")
    lines = "<table><tr><th>Meeting</th><th>Date</th></tr><tr><td>Board</td><td>May<br>June</td></tr></table>"
    t = R.TableCell("June", {}, 0, headings=("Date",), row_groups=("Board",))
    assert R.table_cell(t, html(merged))[0]
    assert R.table_cell(t, html(flat))[0]
    assert not R.table_cell(t, html(other))[0]
    assert R.table_cell(t, html(lines))[0]


def test_a_block_covering_half_a_place_holds_it_at_any_scale():
    place = (0.623881554931733, 0.0, 0.9572148882650664, 0.5)
    half = (0.623881554931733, 0.0, 0.7905482215983997, 0.5)
    for scale in (1.0, 0.375):
        t = R.LayoutKind(R.Text("x", 0, (tuple(x * scale for x in place),)), "text")
        assert R.layout_kind(t, (R.Block("text", tuple(x * scale for x in half), ""),))[0], scale


def test_layout_kind_reads_the_smallest_block_holding_the_place():
    place = ((0.1, 0.1, 0.4, 0.15),)
    page = R.Block("table", (0.0, 0.0, 1.0, 1.0), "")
    line = R.Block("heading", (0.09, 0.09, 0.5, 0.16), "Results")
    t = R.LayoutKind(R.Text("Results", 0, place), "heading")
    assert R.layout_kind(t, (page, line))[0]
    assert not R.layout_kind(t, (page,))[0]
    assert not R.layout_kind(t, (R.Block("heading", (0.5, 0.5, 0.9, 0.9), ""),))[0]


def test_of_two_blocks_of_equal_area_the_first_listed_holds_the_place():
    # Both areas are 0.02 in exact arithmetic; in floats the second is a hair smaller.
    place = ((0.2, 0.8, 0.3, 0.9),)
    heading, text = R.Block("heading", (0.2, 0.8, 0.4, 0.9), ""), R.Block("text", (0.2, 0.8, 0.3, 1.0), "")
    assert R.holder(place, (heading, text)) is heading
    assert R.holder(place, (text, heading)) is text


def test_the_area_tie_does_not_depend_on_the_scale_of_the_boxes():
    # The heading is 1e-6 larger in area than the text block: the text block holds the place at any scale.
    for k in (1, 0.05, 0.001):
        place = ((0, 0, 0.1 * k, 0.1 * k),)
        heading = R.Block("heading", (0, 0, 0.1000001 * k, 0.1 * k), "")
        text = R.Block("text", (0, 0, 0.1 * k, 0.1 * k), "")
        assert R.holder(place, (heading, text)) is text, k


def test_a_list_item_or_form_field_block_is_text_and_nothing_else_is():
    place = ((0.1, 0.1, 0.4, 0.15),)
    text, heading = (R.LayoutKind(R.Text("1. Mix well", 0, place), k) for k in ("text", "heading"))
    for label in ("text", "list", "form", "table", "heading"):
        block = (R.Block(label, (0.09, 0.09, 0.5, 0.16), ""),)
        assert R.layout_kind(text, block)[0] == (label in ("text", "list", "form")), label
        assert R.layout_kind(heading, block)[0] == (label == "heading"), label


def test_every_registered_type_has_parameters_and_a_runner():
    for name, (params, runner) in R.TYPES.items():
        assert hasattr(params, "_fields") and callable(runner), name




@pytest.mark.parametrize("latex, plain", [
    ("3\\sigma", True), ("\\alpha = 0.05", True), ("x^2 + y^2", True), ("H_2O", True),
    ("\\frac{a}{b}", False), ("2\\sqrt{\\alpha\\beta}", False), ("e^{-Knt_0}", False), ("\\hat{Y}_t", False),
    ("n", False),
])
def test_plain_is_equations_text_writes_without_loss(latex, plain):
    assert R.plain(latex) is plain


def test_latex_accepts_the_plain_text_of_a_plain_equation():
    assert R.found(R.Latex("\\alpha = 0.05"), views.html("<p>p at α = 0.05</p>"))[0]
    assert not R.found(R.Latex("\\frac{a}{b}"), views.html("<p>a/b</p>"))[0]


def test_a_section_label_may_be_written_as_the_rows_first_cell():
    # The page prints "valine tDNA" on its own line above its numbers; writing it beside them is as faithful.
    t = R.TableCell("76 (60)", {}, 0, section="valine tDNA")
    above = html("<table><tr><th>locus</th><th>sites</th></tr><tr><td colspan='2'>valine tDNA</td></tr>"
                 "<tr><td></td><td>76 (60)</td></tr></table>")
    beside = html("<table><tr><th>locus</th><th>sites</th></tr>"
                  "<tr><td>valine tDNA</td><td>76 (60)</td></tr></table>")
    elsewhere = html("<table><tr><th>locus</th><th>sites</th></tr>"
                     "<tr><td>16S rDNA</td><td>76 (60)</td></tr></table>")
    assert R.table_cell(t, above)[0] and R.table_cell(t, beside)[0]
    assert not R.table_cell(t, elsewhere)[0]


@pytest.mark.parametrize("output", ["<p>Total 1,240<sup>1</sup></p>", "<p>Total 1,240¹</p>",
                                    "<p>Total 1,240<sup>a</sup></p>"])
def test_a_footnote_marker_after_a_number_is_not_one_of_its_digits(output):
    assert R.found(R.Number("1,240"), html(output))[0]
    assert not R.found(R.Number("1,2401"), html(output))[0]


@pytest.mark.parametrize("gold, output", [
    ("Smith and Jones", "<p>Smith[1] and Jones</p>"),
    ("Smith and Jones", "<p>Smith [12] and Jones</p>"),
    ("Smith and Jones", "<p>Smith[^a] and Jones</p>"),
    ("1,240 units", "<p>1,240[1] units</p>"),
    ("Smith", "<p>Smith[1]</p>"),
])
def test_a_bracketed_footnote_marker_inside_the_text_is_ignored(gold, output):
    assert R.present(R.Present(R.Text(gold, 0)), html(output))[0]


@pytest.mark.parametrize("gold, output, passes", [
    ("[1] item", "<p>[1] item</p>", True),
    ("x[2] and y", "<p>x[2] and y</p>", True),
    ("x[2] and y", "<p>x and y</p>", False),
    ("Smith 2 and Jones", "<p>Smith[1] and Jones</p>", False),
    ("124", "<p>12[3]4</p>", False),
    ("12 4", "<p>12[3] 4</p>", False),
])
def test_a_footnote_marker_is_ignored_only_on_the_page_and_never_joins_digits(gold, output, passes):
    assert R.present(R.Present(R.Text(gold, 0)), html(output))[0] == passes


@pytest.mark.parametrize("output", ["<p><sup>1</sup>1,240</p>", "<p>Total<sup>1</sup>1,240</p>",
                                    "<p><sup>1</sup><b>1,240</b></p>", "<p><sup>*</sup>1,240</p>"])
def test_a_footnote_mark_before_a_number_is_not_one_of_its_digits(output):
    assert R.found(R.Number("1,240"), html(output))[0]
    assert not R.found(R.Number("11,240"), html(output))[0]


def test_a_footnote_mark_before_a_negative_number_leaves_its_sign():
    assert R.found(R.Number("-4.8%"), html("<p><sup>1</sup>-4.8%</p>"))[0]


@pytest.mark.parametrize("gold, output", [
    ("Probiotic strains", "<p>Probiotic<sup>1</sup> strains</p>"),
    ("Smith and Jones", "<p>Smith<sup>12</sup> and Jones</p>"),
    ("Smith and Jones", "<p>Smith <sup> 3 </sup> and Jones</p>"),
    ("Smith and Jones", "<p>Smith<sup>†</sup> and Jones</p>"),
    ("Smith and Jones", "<p>Smith<sup>**</sup> and Jones</p>"),
    ("Smith and Jones", "<p><b>Smith</b><sup class='fn'><a href='#n1'>1</a></sup> and Jones</p>"),
    ("Smith and Jones", "<p>Smith<sup>1</sup> and[2] Jones</p>"),
])
def test_a_footnote_mark_set_as_a_superscript_inside_the_text_is_ignored(gold, output):
    assert R.present(R.Present(R.Text(gold, 0)), html(output))[0]


@pytest.mark.parametrize("gold, output", [
    # after a digit, a superscript is an exponent, not a mark
    ("10 cells", "<p>10<sup>5</sup> cells</p>"),
    ("10 cells", "<p>10<b></b><sup>5</sup> cells</p>"),
    # only a short run of digits or a footnote symbol is a mark: not a word, an ordinal, or four digits
    ("the place", "<p>the 1<sup>st</sup> place</p>"),
    ("Smith and Jones", "<p>Smith<sup>a</sup> and Jones</p>"),
    ("Smith and Jones", "<p>Smith<sup>1234</sup> and Jones</p>"),
    ("H ion", "<p>H<sup>+</sup> ion</p>"),
    # an exponent in math is never a mark
    ("x + y", "<p>$x^2 + y^2$</p>"),
    ("x + y", "<p>x² + y²</p>"),
    ("x + y", "<p><math>x^{2} + y^{2}</math></p>"),
])
def test_a_superscript_that_is_no_footnote_mark_still_counts(gold, output):
    assert not R.present(R.Present(R.Text(gold, 0)), html(output))[0]


def test_a_text_test_still_finds_a_superscript_written_inline():
    assert R.present(R.Present(R.Text("m2 area", 0)), html("<p>m<sup>2</sup> area</p>"))[0]
    assert R.order(R.Order("x2", "y", 0), html("<p>x<sup>2</sup> then y</p>"))[0]


def test_an_image_description_beside_a_cells_text_doesnt_cost():
    v = html('<table><tr><td><img alt="photo: Shangjr Gwo">Shangjr Gwo</td>'
             '<td>Tsing Hua University</td></tr></table>')
    assert R.table_cell(R.TableCell("Tsing Hua University", {"left": "Shangjr Gwo"}, 0), v)[0]


def test_a_cell_that_is_only_an_image_reads_as_its_alt_text():
    v = html('<table><tr><td>Status</td><td><img alt="red circle"></td></tr></table>')
    assert R.table_cell(R.TableCell("red circle", {"left": "Status"}, 0), v)[0]


def test_a_squeezed_present_cut_out_of_a_longer_number_says_so():
    ok, why = R.present(R.Present(R.Text("7777777 77", 0)), html("<p>id 7777777777777777777 x</p>"))
    assert not ok and why == "'7777777 77' found only inside a longer number"


@pytest.mark.parametrize("max_diffs", [0, 1])
@pytest.mark.parametrize("needle, text", [
    ("Total: 40", "Total: 401"),
    ("Total: 40", "x Total: 40.5"),
])
def test_a_present_cut_out_of_a_longer_number_says_so(needle, text, max_diffs):
    ok, why = R.present(R.Present(R.Text(needle, max_diffs)), html(f"<p>{text}</p>"))
    assert not ok and why == f"{needle!r} found only inside a longer number"


@pytest.mark.parametrize("max_diffs", [0, 1])
def test_a_present_that_is_absent_still_says_not_found(max_diffs):
    ok, why = R.present(R.Present(R.Text("Total: 40", max_diffs)), html("<p>Subtotal 99</p>"))
    assert not ok and why.startswith("'Total: 40' not found (best ")


@pytest.mark.parametrize("before, after, text, why", [
    ("1. Introduction", "2. Methods", "11. Introduction ... 2. Methods",
     "'before' text '1. Introduction' found only inside a longer number"),
    ("1. Introduction", "2. Methods", "1. Introduction ... 22. Methods",
     "'after' text '2. Methods' found only inside a longer number"),
    ("1. Intro duction", "2. Methods", "11. Introduction ... 2. Methods",
     "'before' text '1. Intro duction' found only inside a longer number"),
    ("1. Introduction", "2. Methods", "Preface ... 2. Methods",
     "'before' text '1. Introduction' not found"),
])
def test_an_order_item_cut_out_of_a_longer_number_says_so(before, after, text, why):
    assert R.order(R.Order(before, after, 0), html(f"<p>{text}</p>")) == (False, why)


def _edited(n: int, k: int) -> tuple[str, str]:
    """An n-letter cell and the same cell with its first k letters replaced by digits."""
    want = "".join("abcdefghij"[i % 10] if i % 3 else "klmnopqrst"[i % 10] for i in range(n))
    return want, "5" * k + want[k:]


# Note: 1 - k/n is not exactly representable for most n, and rapidfuzz's ratio for k substitutions lands a
# hair under it, so the cell comparisons need the same slack `present` has.
# Past half the cell the floor `TABLE_MIN_RATIO` decides, not the edits.
EDIT_CASES = [(n, k) for n in (3, 6, 7, 10, 26, 49) for k in (1, 2, 3) if k / n <= 0.5]


@pytest.mark.parametrize("n, k", EDIT_CASES)
def test_a_cell_allows_exactly_max_diffs_edits(n, k):
    want, got = _edited(n, k)
    table = html(f"<table><tr><td>{got}</td></tr></table>")
    assert R.table_cell(R.TableCell(want, {}, k), table)[0]
    assert not R.table_cell(R.TableCell(want, {}, k - 1), table)[0]


@pytest.mark.parametrize("n, k", EDIT_CASES)
def test_a_relation_allows_exactly_max_diffs_edits(n, k):
    want, got = _edited(n, k)
    table = html(f"<table><tr><th>Year</th><th>Total</th></tr><tr><td>{got}</td><td>1,240</td></tr></table>")
    for kind, rel in (("left", "left"), ("top_heading", "top_heading")):
        if kind == "left":
            t = R.TableCell("1,240", {"left": want}, k)
        else:
            table = html(f"<table><tr><th>{got}</th></tr><tr><td>1,240</td></tr></table>")
            t = R.TableCell("1,240", {"top_heading": want}, k)
        assert R.table_cell(t, table)[0], (n, k, kind)
        t = R.TableCell("1,240", {rel: want}, k - 1)
        assert not R.table_cell(t, table)[0], (n, k, kind)


@pytest.mark.parametrize("n, k", EDIT_CASES)
def test_cell_headings_allow_exactly_max_diffs_edits(n, k):
    want, got = _edited(n, k)
    table = html(f"<table><tr><th>{got}</th></tr><tr><td>1,240</td></tr></table>")
    assert R.table_cell(R.TableCell("1,240", {}, k, headings=(want,)), table)[0]
    assert not R.table_cell(R.TableCell("1,240", {}, k - 1, headings=(want,)), table)[0]


# --------------------------------------------------------------------------- right-to-left tables
# A right-to-left table written in reading order puts its first cell at the right edge. The roles follow
# the html's order, so it reads the same as its mirrored left-to-right table.

RTL_ROW = ("<table><tr><th>المجموع</th><td>1,240</td><td>٣</td></tr></table>", "المجموع", "1,240", "٣")
LTR_ROW = ("<table><tr><th>Total</th><td>1,240</td><td>3</td></tr></table>", "Total", "1,240", "3")


@pytest.mark.parametrize("markup, label, cell, last", [RTL_ROW, LTR_ROW])
def test_left_heading_is_the_first_cell_of_the_row_in_html_order(markup, label, cell, last):
    table = html(markup)
    assert R.table_cell(R.TableCell(cell, {"left_heading": label}, 0), table)[0]
    assert not R.table_cell(R.TableCell(cell, {"left_heading": last}, 0), table)[0]


@pytest.mark.parametrize("markup, first, cell, label", [
    ("<table><tr><td>٣</td><td>1,240</td><th>المجموع</th></tr></table>", "٣", "1,240", "المجموع"),
    ("<table><tr><td>3</td><td>1,240</td><th>Total</th></tr></table>", "3", "1,240", "Total"),
])
def test_right_heading_is_the_last_cell_of_the_row_in_html_order(markup, first, cell, label):
    table = html(markup)
    assert R.table_cell(R.TableCell(cell, {"right_heading": label}, 0), table)[0]
    assert not R.table_cell(R.TableCell(cell, {"right_heading": first}, 0), table)[0]


def test_dir_rtl_does_not_change_the_roles():
    table = html('<table dir="rtl"><tr><th>المجموع</th><td>1,240</td><td>٣</td></tr></table>')
    t = R.TableCell("1,240", {"left_heading": "المجموع", "left": "المجموع", "right": "٣"}, 0)
    assert R.table_cell(t, table)[0]


def test_right_heading_skips_empty_cells_like_left_heading():
    table = html("<table><tr><td>1,240</td><td></td><th>Total</th></tr></table>")
    assert R.table_cell(R.TableCell("1,240", {"right_heading": "Total"}, 0), table)[0]


def test_right_heading_takes_a_max_diffs_edit():
    table = html("<table><tr><td>1,240</td><th>Totaal</th></tr></table>")
    assert R.table_cell(R.TableCell("1,240", {"right_heading": "Total"}, 1), table)[0]
    assert not R.table_cell(R.TableCell("1,240", {"right_heading": "Total"}, 0), table)[0]


def _mirror(markup: str) -> str:
    """The same table with each row's cells in reverse order."""
    rows = re.findall(r"<tr>(.*?)</tr>", markup)
    cells = lambda row: re.findall(r"<t[hd].*?</t[hd]>", row)  # noqa: E731
    return "<table>" + "".join("<tr>" + "".join(reversed(cells(r))) + "</tr>" for r in rows) + "</table>"


# (table, the label at the start of the 1,240 row, the label at its end)
MIRROR_CASES = [
    ("<table><tr><th>Total</th><td>1,240</td><th>Sum</th></tr></table>", "Total", "Sum"),
    ("<table><thead><tr><th>Item</th><th>Value</th><th>Rank</th></tr></thead>"
     "<tr><th>Total</th><td>1,240</td><th>Sum</th></tr></table>", "Total", "Sum"),
    ("<table><tr><th>A</th><td>x</td><th>B</th></tr><tr><th>Total</th><td>1,240</td><th>Sum</th></tr></table>",
     "Total", "Sum"),
]


@pytest.mark.parametrize("markup, start, end", MIRROR_CASES)
def test_a_mirrored_table_swaps_left_heading_and_right_heading(markup, start, end):
    table, mirrored = html(markup), html(_mirror(markup))
    for a, b, label in (("left_heading", "right_heading", start), ("right_heading", "left_heading", end)):
        assert R.table_cell(R.TableCell("1,240", {a: label}, 0), table)[0]
        assert R.table_cell(R.TableCell("1,240", {b: label}, 0), mirrored)[0]
        assert not R.table_cell(R.TableCell("1,240", {b: label}, 0), table)[0]


def test_right_heading_falls_back_to_the_last_cell_when_no_th_is_found():
    table = html("<table><tr><td>1,240</td><td>3</td><td>Sum</td></tr></table>")
    assert R.table_cell(R.TableCell("1,240", {"right_heading": "Sum"}, 0), table)[0]
    assert not R.table_cell(R.TableCell("1,240", {"right_heading": "3"}, 0), table)[0]


def test_right_heading_reads_a_colspan_cell_at_the_end_of_the_row():
    table = html("<table><tr><td>1,240</td><th colspan='2'>Sum</th></tr></table>")
    assert R.table_cell(R.TableCell("1,240", {"right_heading": "Sum"}, 0), table)[0]


@pytest.mark.parametrize("markup, cell, role, want", [
    ("<table><tr><th>Male</th><td>5</td></tr></table>", "Male", "right_heading", "5"),
    ("<table><tr><td>5</td><th>Male</th></tr></table>", "Male", "left_heading", "5"),
    ("<table><tr><td>x</td></tr><tr><th>Male</th></tr></table>", "Male", "top_heading", "x"),
])
def test_a_heading_cell_with_no_other_heading_reads_the_cell_at_the_edge(markup, cell, role, want):
    assert R.table_cell(R.TableCell(cell, {role: want}, 0), html(markup))[0]


SPAN = "<table><tr><td>a</td><td rowspan=2>m</td><th>H</th></tr><tr><td>5</td><td>z</td></tr></table>"


def test_a_heading_walk_stays_in_the_rows_of_its_cell():
    assert R.table_cell(R.TableCell("5", {"right_heading": "z"}, 0), html(SPAN))[0]
    assert not R.table_cell(R.TableCell("5", {"right_heading": "H"}, 0), html(SPAN))[0]


@pytest.mark.parametrize("blank", ["\u200b", "\ufeff", "\u00ad", "<math></math>", "<ol><li></li></ol>",
                                   "<input type=hidden value=v>"])
def test_page_near_empty_does_not_count_what_shows_nothing(blank):
    assert R.page_near_empty(R.PageNearEmpty(0), html(f"<p>{blank}</p>")) == (True, "")


def test_page_near_empty_counts_a_list_items_number():
    assert not R.page_near_empty(R.PageNearEmpty(0), html("<ol><li>x</li></ol>"))[0]

@pytest.mark.parametrize("text, passes", [
    ("<p>Totl: 40</p>", True),
    ("<p>Total: 400</p><p>Totl: 40</p>", True),     # a glued copy does not veto a separate fuzzy one
    ("<p>Totl: 40</p><p>Total: 400</p>", True),
    ("<p>Total: 400</p>", False),                   # nor does any window of the glued copy count
    ("<p>Total: 400</p><p>Total: 41</p>", False),   # and an edit may not touch the number
])
def test_a_glued_copy_does_not_veto_a_fuzzy_match_elsewhere(text, passes):
    assert R.present(R.Present(R.Text("Total: 40", 1)), html(text))[0] is passes


def test_a_squeezed_glued_copy_does_not_veto_a_fuzzy_match_elsewhere():
    assert R.present(R.Present(R.Text("ab 1 2", 1)), html("<p>ab 123</p><p>xb 1 2</p>"))[0]
    assert not R.present(R.Present(R.Text("ab 1 2", 1)), html("<p>ab 123</p>"))[0]


@pytest.mark.parametrize("text, passes", [
    ("<p>40</p>", True),
    ("<p>400 40</p>", True),              # a glued copy does not veto a clean one beside it
    ("<p>400</p><p>40</p>", True),        # nor one in another paragraph
    ("<p>4 0</p>", False),                # a spaced copy is two numbers
    ("<p>400 4 0</p>", False),
    ("<p>400</p>", False),
    ("<p>4 00</p>", False),
    ("<p>1400</p>", False),
])
def test_a_glued_copy_does_not_veto_a_spaced_copy_elsewhere(text, passes):
    assert R.present(R.Present(R.Text("40", 0)), html(text))[0] is passes


@pytest.mark.parametrize("md", [0, 1, 2])
def test_order_more_edits_never_lose_an_exact_start(md):
    assert R.order(R.Order("a a", "a a", md), html("<p>a a a a</p>"))[0]
    assert R.order(R.Order("Item 1", "Item 1 Item 1", md), html("<p>Item 1 Item 1 Item 1</p>"))[0]


_SEED_PROBE = ("from omni_parse_bench.scorers.unit_tests import runners as R; "
               "from omni_parse_bench import views; "
               "print(R.order(R.Order('bba', 'b abb', 2), views.html('<p>b ba baa bbb ba</p>'))[0])")


def test_order_verdict_does_not_depend_on_the_hash_seed():
    # fuzzysearch keeps one match per run of overlapping ones, the min of a set; on a tie that pick
    # followed the string hash, so this verdict passed under one PYTHONHASHSEED and failed under others.
    import os
    import subprocess
    import sys
    got = set()
    for seed in range(8):
        env = {**os.environ, "PYTHONHASHSEED": str(seed)}
        out = subprocess.run([sys.executable, "-c", _SEED_PROBE], env=env, capture_output=True, text=True,
                             check=True)
        got.add(out.stdout.strip())
    assert got == {"True"}, got


def test_near_keeps_every_match_tied_for_best_in_a_run():
    # 'b abb' with 2 edits: 'b ba b' at 0 and 'baa bb' at 5 overlap, both 2 edits, both 6 long.
    spans = {(m.start, m.end, m.dist) for m in R._near("b abb", "b ba baa bbb ba", 2)}
    assert {(0, 6, 2), (5, 11, 2)} <= spans


def test_order_that_passes_with_fewer_edits_passes_with_more():
    # 'aa' is in the squeezed text 'bbaabab' only, before 'aba'; with an edit to spend both are found in the
    # folded text, out of order there, which must not stop the squeezed text from passing.
    page = html("<p>b b a ab ab</p>")
    assert [R.order(R.Order("aa", "a ba", k), page)[0] for k in range(2)] == [True, True]


@pytest.mark.parametrize("gold, page, exact, passes", [
    ("iPhone", "<p>Buy an iphone today</p>", False, True),     # case is folded unless the arg asks
    ("iPhone", "<p>Buy an iphone today</p>", True, False),     # found, but not in its case
    ("iPhone", "<p>Buy an iPhone today</p>", True, True),
    ("NASA", "<p>Nasa launched</p>", True, False),
    ("Co", "<p>CO</p>", True, False),
    ("Straße", "<p>straße</p>", True, False),
    ("école", "<p>école</p>", True, True),               # NFC/NFKC and the other folds still apply
    ("“Hello”", '<p>"Hello"</p>', True, True),                 # quotes still fold
    ("Total due", "<p>Total   due:\n40</p>", True, True),      # spacing still folds
    ("Anglo-Saxon law", "<p>Anglo- saxon law</p>", True, False),   # a wrapped hyphen keeps case too
    ("Anglo-Saxon law", "<p>Anglo- Saxon law</p>", True, True),
    ("Anglo-Saxon law", "<p>Anglo- saxon law</p>", False, True),
    ("Xylophonic", "<p>Xylo- phonic</p>", True, True),
    ("Xylophonic", "<p>xylo- phonic</p>", True, False),
    ("Probiotic Bacteria", "<p>ProbioticBacteria</p>", True, True),          # the squeeze keeps case too
    ("Probiotic Bacteria", "<p>Probioticbacteria</p>", True, False),
    ("Probiotic Bacteria", "<p>Probioticbacteria</p>", False, True),
    ("Probiotic", "<p>Probiotic1</p>", True, True),
    ("Probiotic", "<p>probiotic1</p>", True, False),
    ("Smith and Jones", "<p>Smith[1] and Jones</p>", True, True),            # the bracket-marker retry
    ("Smith and Jones", "<p>smith[1] and Jones</p>", True, False),
    ("Smith and Jones", "<p>smith[1] and Jones</p>", False, True),
    ("Smith and Jones", "<p>smith<sup>1</sup> and Jones</p>", True, False),
])
def test_present_exact_case_keeps_case_and_every_other_fold(gold, page, exact, passes):
    got, why = R.present(R.Present(R.Text(gold, 0, (), exact)), html(page))
    assert got is passes
    assert passes or "not found" in why


def test_exact_case_is_an_arg_field_of_a_present_text_only():
    from omni_parse_bench.scorers.unit_tests import tests as T

    def parse(args, settings=None, test_type="present"):
        return T._params("t", test_type, args, settings or {})

    arg = {"text": "iPhone", "max_diffs": 0}
    assert parse({"content": arg | {"exact_case": True}}).content.exact_case is True
    assert parse({"content": arg}).content.exact_case is False
    for bad in ("yes", 1, None):
        with pytest.raises(ValueError, match="exact_case"):
            parse({"content": arg | {"exact_case": bad}})
    with pytest.raises(ValueError, match="compares text only, not a number"):
        parse({"content": {"number": "12", "exact_case": True}})
    with pytest.raises(ValueError, match="present"):
        parse({"before": arg | {"exact_case": True}, "after": arg}, test_type="order")
    with pytest.raises(ValueError, match="present"):
        parse({"content": arg | {"exact_case": True}}, {"expected_count": 1}, "repeat")
    with pytest.raises(ValueError, match="present"):
        parse({"cell": arg | {"exact_case": True}}, test_type="table_cell")


def test_exact_case_names_a_glued_number_not_a_case_when_both_apply():
    """Wrong case and a number glued on both fail; the reason says what the test's own fold sees."""
    got, why = R.present(R.Present(R.Text("Total: 40", 0, (), True)), html("<p>total: 400</p>"))
    assert not got and "not found" in why
    got, why = R.present(R.Present(R.Text("Total: 40", 0, (), True)), html("<p>Total: 400</p>"))
    assert not got and "longer number" in why


def test_format_reads_the_marks_of_the_span_and_the_words_around_it():
    p = R.Format("the ", "total", " due", 0, ("bold",), ())
    assert R.format_mark(p, html("<p>the <b>total</b> due</p>")) == (True, "")
    assert R.format_mark(p, html("<p>the total due</p>")) == (False, "the span lacks ['bold']")
    assert R.format_mark(p, html("<p><b>the total due</b></p>")) == (
        False, "['bold'] runs onto the text around the span")
    assert R.format_mark(p, html("<p>nothing</p>")) == (False, "the context is not in the output")
    no = p._replace(marks=(), absent=("bold",))
    assert R.format_mark(no, html("<p>the total due</p><p><b>x</b></p>")) == (True, "")
    assert R.format_mark(no, html("<p>the total due</p>"))[0] is False     # no mark anywhere: nothing shown
    assert R.format_mark(no, html("<p>the <b>total</b> due</p>")) == (False, "the span carries ['bold']")


def test_format_does_not_change_what_a_text_test_reads():
    page = html("<p>Total <b>due</b> <sup>1</sup></p>")
    assert R.found(R.Text("Total due", 0), page) == (True, "")
    assert R.format_mark(R.Format("Total ", "due", None, 0, ("bold",), ()), page)[0]
    assert not R.format_mark(R.Format("Total ", "due", None, 0, ("italic",), ()), page)[0]
