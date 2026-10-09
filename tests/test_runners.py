"""Each runner on a hand-written output: the cases each runner's docstring describes."""
from __future__ import annotations

import pytest

from omni_parse_bench import runners as R
from omni_parse_bench import views


def html(s: str) -> views.Html:
    return views.html(s)


def test_present_allows_exactly_the_edits_it_says():
    assert R.present(R.Present(R.Text("a" * 39, 2)), html("<p>" + "a" * 37 + "bb</p>"))[0]
    assert not R.present(R.Present(R.Text("a" * 39, 1)), html("<p>" + "a" * 37 + "bb</p>"))[0]


def test_a_number_is_strict_on_digits_lenient_on_separators():
    v = html("<p>total 1 234 567,89 EUR</p>")
    assert R.found(R.Number("1,234,567.89"), v)[0]
    assert not R.found(R.Number("1,234,567.80"), v)[0]


def test_a_number_keeps_sign_and_percent():
    v = html("<p>change 4.8% and 12.5</p>")
    assert R.found(R.Number("4.8%"), v)[0]
    assert not R.found(R.Number("-4.8%"), v)[0]
    assert not R.found(R.Number("12.5%"), v)[0]


def test_a_number_sees_through_latex():
    v = html(r"<p>mass <math>m_{\text{r}}\,2.8 \times 10^6</math></p>")
    assert R.found(R.Number("2.8"), v)[0]


@pytest.mark.parametrize("token, core", [
    ("1,240.00", "1240.00"), ("(39%)", "39"), ("12,345", "12345"), ("4.500", None), ("16,17", None)])
def test_number_reads_separators(token, core):
    n = R.number(token)
    assert (n.core if n else None) == core


def test_order_reads_folded_text():
    v = html("<p>Alpha section</p><p>Beta section</p>")
    assert R.order(R.Order("ALPHA section", "beta SECTION", 1), v)[0]


def test_repeat_does_not_count_a_longer_word():
    v = html("<p>Passive Income and Loss</p><p>Nonpassive Income and Loss</p><p>Passive Income and Loss</p>")
    assert R.repeat(R.Repeat("Passive Income and Loss", 2), v)[0]


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


def test_layout_kind_reads_the_smallest_block_holding_the_place():
    place = ((0.1, 0.1, 0.4, 0.15),)
    page = R.Block("table", (0.0, 0.0, 1.0, 1.0), "")
    line = R.Block("heading", (0.09, 0.09, 0.5, 0.16), "Results")
    t = R.LayoutKind(R.Text("Results", 0, place), "heading")
    assert R.layout_kind(t, (page, line))[0]
    assert not R.layout_kind(t, (page,))[0]
    assert not R.layout_kind(t, (R.Block("heading", (0.5, 0.5, 0.9, 0.9), ""),))[0]


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


def test_a_text_test_still_finds_a_superscript_written_inline():
    assert R.present(R.Present(R.Text("m2 area", 0)), html("<p>m<sup>2</sup> area</p>"))[0]
    assert R.order(R.Order("x2", "y", 0), html("<p>x<sup>2</sup> then y</p>"))[0]
