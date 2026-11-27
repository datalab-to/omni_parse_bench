# ruff: noqa: E501
"""Relations of the absence guards that read every occurrence (M146 to M149): `blank_after` for every copy of the
label and the places around it, `table_cell` `{empty}` and `{end}` for every cell that matches the anchor and
every table that goes on from it."""
from __future__ import annotations

import pytest

from metamorphic.common import HOLDS, more_evidence, passes, relation
from omni_parse_bench import markdown
from omni_parse_bench.scorers.unit_tests import runners

DOB, MASK, VALUE = "Date of birth:", "__/__/____", "12/03/1985"
STOPS = ("Name:", "Place of birth:", "Phone:")


def blank(printed: str | None = MASK, stops=STOPS) -> runners.Present:
    return runners.Present(runners.Text(DOB, 0), True, runners.Text(printed, 0) if printed else None,
                           tuple(runners.Text(x, 0) for x in stops))


def paragraphs(dob: str) -> str:
    return f"<p>Name: Ann Lee</p><p>{DOB} {dob}</p><p>Place of birth: Paris</p><p>Phone: 555 0101</p>"


def two_columns(dob: str) -> str:
    return ("<table><tr><td>Name:</td><td>Ann Lee</td></tr>" f"<tr><td>{DOB}</td><td>{dob}</td></tr>"
            "<tr><td>Place of birth:</td><td>Paris</td></tr><tr><td>Phone:</td><td>555 0101</td></tr></table>")


def header_row(dob: str) -> str:
    return ("<table><tr><td>Name:</td><td>" + DOB + "</td><td>Place of birth:</td><td>Phone:</td></tr>"
            f"<tr><td>Ann Lee</td><td>{dob}</td><td>Paris</td><td>555 0101</td></tr></table>")


FORMS = {"paragraphs": paragraphs, "two columns": two_columns, "header row": header_row}
BLANKS = ["", MASK, "____", " "]


@relation(HOLDS, domain="3 layouts x 3 layouts x 4 spellings of a blank x 2 copies that can hold the value, and the "
                        "label printed twice in one paragraph or one table row")
@pytest.mark.parametrize("first", FORMS)
@pytest.mark.parametrize("second", FORMS)
@pytest.mark.parametrize("blank_form", BLANKS)
@pytest.mark.parametrize("filled", [0, 1])
def test_a_form_written_twice_passes_blank_after_only_when_every_copy_is_blank(first, second, blank_form, filled):
    """A page that holds the form twice (a duplicated block, in the same layout or another) passes a
    `blank_after` test only when the field is blank in both copies; with a value in the first copy, or in the
    second, it fails. A label printed twice in one paragraph or one table row, blank both times, passes, and
    fails when either copy holds a value. [M146]
    Why it matters for a score: an output that writes one clean copy of a field and one filled copy is not
    graded as leaving the field blank, and a form that prints a label twice is not failed for it."""
    # Given the form twice, with the field blank in both copies
    copies = (FORMS[first], FORMS[second])
    values = [blank_form, blank_form]
    assert passes(blank(), copies[0](values[0]) + copies[1](values[1]))
    # When one copy holds a value (the first or the second); Then the test fails
    values[filled] = f"{blank_form} {VALUE}".strip()
    page = copies[0](values[0]) + copies[1](values[1])
    assert not passes(blank(), page), page


@more_evidence()
@pytest.mark.parametrize("blank_form", ["", MASK, "____"])
@pytest.mark.parametrize("filled", [0, 1])
def test_a_label_printed_twice_in_one_line_or_row_needs_both_copies_blank(blank_form, filled):
    """The label written twice in one paragraph, or twice in one table row (with or without a blank cell
    between), passes `blank_after` when both copies are blank, and fails when either holds a value. [M146]
    Why it matters for a score: a form that prints a label twice is graded on both fields."""
    values = [blank_form, blank_form]
    pages = {
        "paragraph": lambda v: f"<p>{DOB} {v[0]} {DOB} {v[1]} Place of birth: Paris</p>",
        "row": lambda v: f"<table><tr><td>{DOB}</td><td>{v[0]}</td><td></td><td>{DOB}</td><td>{v[1]}</td></tr></table>",
    }
    for name, page in pages.items():
        assert passes(blank(), page(values)), (name, page(values))
        filled_values = list(values)
        filled_values[filled] = f"{blank_form} {VALUE}"
        assert not passes(blank(), page(filled_values)), (name, page(filled_values))


@relation(HOLDS, domain="11 places a value can hide around a field; taken out the field passes, and the value in the "
                        "next field's own place keeps the verdict")
@pytest.mark.parametrize("name, page", [
    ("before the label in its paragraph", f"<p>Name: Ann Lee</p><p>{VALUE} {DOB} {MASK}</p><p>Place of birth: Paris</p>"),
    ("before the label in its cell", f"<table><tr><td>Name:</td><td>Ann Lee</td></tr><tr><td>{VALUE} {DOB}</td><td>{MASK}</td></tr></table>"),
    ("in the cell left of the label", f"<table><tr><td></td><td>Name:</td><td>Ann Lee</td></tr><tr><td>{VALUE}</td><td>{DOB}</td><td></td></tr></table>"),
    ("two cells right of the label", f"<table><tr><td>{DOB}</td><td></td><td>{VALUE}</td></tr></table>"),
    ("below a blank right cell", f"<table><tr><td>{DOB}</td><td></td></tr><tr><td>{VALUE}</td><td></td></tr><tr><td>Name:</td><td>Ann Lee</td></tr></table>"),
    ("two rows below the label of a header-row table", f"<table><tr><td>Name:</td><td>{DOB}</td></tr><tr><td>Ann Lee</td><td></td></tr><tr><td></td><td>{VALUE}</td></tr></table>"),
    ("in a table after the label's table", f"<table><tr><td>Name:</td><td>Ann Lee</td></tr><tr><td>{DOB}</td><td></td></tr></table><table><tr><td>{VALUE}</td></tr></table><p>Place of birth: Paris</p>"),
    ("in a paragraph after the label's table", f"<table><tr><td>{DOB}</td><td></td></tr></table><p>{VALUE}</p>"),
    ("in the blank right cell's column, below", f"<table><tr><td>{DOB}</td><td></td></tr><tr><td></td><td>{VALUE}</td></tr><tr><td>Name:</td><td>Ann Lee</td></tr></table>"),
    ("in a paragraph after a one-column table", f"<table><tr><td>{DOB}</td></tr></table><p>{VALUE}</p>"),
    ("in the label's cell on a second line", f"<table><tr><td>{DOB}<br>{VALUE}</td><td></td></tr></table>"),
])
def test_a_value_written_around_a_blank_field_fails_blank_after_and_elsewhere_it_does_not(name, page):
    """A value written beside a blank field's label, outside the first cell right of it (before the label, in
    the cell to its left, two cells right, below a blank right cell, two rows down a header-row column, below a blank right cell in its column,
    in a table or paragraph after the label's table, or on a second line of the label's cell) fails its
    `blank_after` test; the same value written in another field's place (after that field's label) keeps the
    verdict. [M147]
    Why it matters for a score: invented content is caught wherever it is put near the field, not only in the
    first slot after the label."""
    # Given the page with the value near the field
    assert not passes(blank(), page), (name, page)
    # When the value is taken out, or moved to the next field; Then the field passes
    emptied = page.replace(VALUE, "")
    assert passes(blank(), emptied), (name, emptied)
    moved = emptied.replace("Place of birth:", f"Place of birth: {VALUE}", 1)
    assert passes(blank(), moved) or "Place of birth:" not in emptied, (name, moved)


EMPTY = runners.TableCell("100", {}, 0, shapes={"right": "empty"})
DOWN_END = runners.TableCell("70", {}, 0, shapes={"down": "end"})
RIGHT_END = runners.TableCell("80", {}, 0, shapes={"right": "end"})
HEAD = "<tr><th>Item</th><th>Q1</th><th>Q2</th></tr>"
FUEL = "<tr><td>Fuel</td><td>70</td><td>80</td></tr>"


def table(rent: str = "<td>Rent</td><td>100</td><td></td>", head: str = HEAD, fuel: str = FUEL) -> str:
    return f"<table>{head}<tr>{rent}</tr>{fuel}</table>"


FAITHFUL = table()
FILLED = table(rent="<td>Rent</td><td>100</td><td>200</td>")


@relation(HOLDS, domain="2 orders of a faithful and a filled copy of the table; the anchor text in a second cell, "
                        "with and without a value beside it; a second line in the anchor's cell")
@pytest.mark.parametrize("order", ["faithful first", "faithful last"])
def test_a_table_shape_guard_holds_for_every_cell_that_matches_the_anchor(order):
    """A `table_cell` test with `{"empty": true}` fails when any table or cell that matches the anchor (and its
    relations) has something beside it: a table written twice with the value in one copy, the anchor text in
    a second cell with a value beside it, or a second line in the anchor's own cell; a faithful table written
    twice passes. [M148]
    Why it matters for a score: one clean copy of a table next to an invented one is not a pass."""
    pair = (FAITHFUL, FILLED) if order == "faithful first" else (FILLED, FAITHFUL)
    # Given the faithful table, alone and twice
    assert passes(EMPTY, FAITHFUL) and passes(EMPTY, FAITHFUL + FAITHFUL)
    # When one copy holds a value; Then the test fails
    assert not passes(EMPTY, "".join(pair))
    assert not passes(EMPTY, table(fuel="<tr><td>Fuel</td><td>100</td><td>200</td></tr>"))
    assert passes(EMPTY, table(fuel="<tr><td>Fuel</td><td>70</td><td>80</td></tr>"))
    assert not passes(EMPTY, table(rent="<td>Rent</td><td>100<br>200</td><td></td>"))


CONT = "<tr><td>Tax</td><td>9</td><td>8</td></tr>"


@relation(HOLDS, domain="4 ways to write a headerless table right after the anchor's table (adjacent, a newline, a "
                        "wrapper div, a comment) x 2 sides; a table with a header, text between, another width, "
                        "or the anchor again is another table")
@pytest.mark.parametrize("glue", ["", "\n", "<!-- x -->", "<p></p>"])
@pytest.mark.parametrize("wrap", [False, True])
def test_end_reads_a_headerless_table_that_goes_on_from_the_anchors_table(glue, wrap):
    """`{"end": true}` fails when a table written right after the anchor's table, with nothing visible between
    (white space, a comment, an empty element, wrapper `<div>`s), has the same columns (same rows, to the
    right) and no heading, and holds a row there; a table with a heading of its own, a paragraph before it,
    another number of columns, or the anchor again (a copy, judged as the first is) is another table and
    keeps the verdict, as does a faithful table written twice. The price: a second table that prints its
    header again is not told from a second table of the same shape (its rows are not read), and a paragraph,
    a caption or a column table with a header written after the table is not read. [M149]
    Why it matters for a score: an invented row written as a second headerless `<table>` after the last row is
    caught, and a page with two complete tables is not failed."""
    put = (lambda x: f"<div>{x}</div>") if wrap else (lambda x: x)
    # Given the table with nothing after its last row
    assert passes(DOWN_END, put(FAITHFUL))
    # When a headerless table with a row follows, nothing visible between; Then it fails
    assert not passes(DOWN_END, put(FAITHFUL) + glue + put(f"<table>{CONT}</table>")), (glue, wrap)
    # When the next table has a header, text before it, another width, or the anchor again; Then it is another table
    other = "<table><tr><th>Cost</th><th>Q3</th><th>Q4</th></tr>" + CONT + "</table>"
    assert passes(DOWN_END, put(FAITHFUL) + glue + put(other))
    assert passes(DOWN_END, put(FAITHFUL) + glue + "<p>Note.</p>" + put(f"<table>{CONT}</table>"))
    assert passes(DOWN_END, put(FAITHFUL) + glue + put("<table><tr><td>Tax</td><td>9</td></tr></table>"))
    assert passes(DOWN_END, put(FAITHFUL) + glue + put(FAITHFUL)), "a faithful table written twice"
    assert passes(DOWN_END, put(FAITHFUL) + glue + put(f"<table>{HEAD}{CONT}</table>")), "the limit"
    # When the table is written twice, one copy with a row added; Then it fails
    assert not passes(DOWN_END, put(FAITHFUL) + glue + put(table(fuel=FUEL + CONT)))
    # And to the right: a headerless table of the same height
    column = "<table><tr><td>a</td></tr><tr><td>b</td></tr><tr><td>c</td></tr></table>"
    assert not passes(RIGHT_END, put(FAITHFUL) + glue + put(column))
    assert passes(RIGHT_END, put(FAITHFUL) + glue + put(column.replace("<td>a", "<th>Q3")))


@more_evidence()
@pytest.mark.parametrize("mask", [MASK, "__/__", "DD__MM__YYYY"])
def test_a_printed_mask_of_underscores_passes_in_markdown_as_in_html(mask):
    """A mask of underscores (`__/__/____`) the page prints in a blank field passes the field's `blank_after`
    test written once in markdown, as it does in html, though the markdown converter reads the pairs of
    underscores as bold; a value written beside it fails in both. [M98]
    Why it matters for a score: a system that answers in markdown is not failed for copying a blank field's
    printed mask."""
    test = blank(printed=mask)
    for write in (lambda s: s, markdown.to_html):
        assert passes(test, write(f"Name: Ann\n\n{DOB} {mask}\n\nPlace of birth: Paris" if write is markdown.to_html
                                  else f"<p>Name: Ann</p><p>{DOB} {mask}</p><p>Place of birth: Paris</p>"))
    assert not passes(test, markdown.to_html(f"Name: Ann\n\n{DOB} {mask} {VALUE}\n\nPlace of birth: Paris"))
    assert not passes(test, f"<p>{DOB} //</p>") or "_" not in mask
