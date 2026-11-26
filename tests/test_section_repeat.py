"""A section label written in each cell of its row is the section row a merged cell is (M120) for a test that
names it; another repeated row is data, and a reading that passed without it still passes."""
import pytest

from omni_parse_bench import views
from omni_parse_bench.scorers.unit_tests import runners


def section_passes(page: str, section: str, cell: str = "6", **kwargs) -> bool:
    test = runners.TableCell(cell, {}, kwargs.pop("max_diffs", 0), section=section, **kwargs)
    return runners.table_cell(test, views.html(page))[0]


def under(row: str, head: str = "<tr><th>A</th><th>B</th><th>C</th></tr>") -> str:
    return f"<table>{head}{row}<tr><td>5</td><td>6</td><td>7</td></tr></table>"


@pytest.mark.parametrize("row, label", [
    ("<tr><td colspan=3>Cohort 1</td></tr>", "Cohort 1"),                         # merged
    ("<tr><td>Cohort 1</td><td>Cohort 1</td><td>Cohort 1</td></tr>", "Cohort 1"),  # repeated in every cell
    ("<tr><td>Cohort 1</td><td></td><td></td></tr>", "Cohort 1"),                  # beside empty cells
    ("<tr><th>Cohort 1</th><th>Cohort 1</th><th>Cohort 1</th></tr>", "Cohort 1"),  # in heading cells
    ("<tr><td>COHORT  1</td><td>cohort 1</td><td>Cohort 1</td></tr>", "Cohort 1"),  # case and spacing differ
    ("<tr><td>Cohort 1</td><td>Cohort ​1</td><td>Cohort 1</td></tr>", "Cohort 1"),  # fold equal
    ("<tr><td colspan=3>1982</td></tr>", "1982"),                                  # a number, merged
    ("<tr><td>1982</td><td>1982</td><td>1982</td></tr>", "1982"),                  # a number, repeated
])
def test_a_section_label_reads_the_same_merged_or_repeated(row, label):
    assert section_passes(under(row), label)
    assert not section_passes(under(row), "Cohort 2")


@pytest.mark.parametrize("row", [
    "<tr><td>Cohort 1</td><td>Cohort 2</td><td>Cohort 1</td></tr>",        # different labels: data
    "<tr><td>Cohort 1</td><td>Cohort 1</td><td></td></tr>",                # a cell left empty
    "<tr><td></td><td>Cohort 1</td><td>Cohort 1</td></tr>",
    "<tr><td></td><td></td><td></td></tr>",
    "<tr><td>x</td><td>Cohort 1</td><td></td></tr>",                       # one label, a value before it
    "<tr><td></td><td>Cohort 1</td><td></td></tr>",                        # a heading beside empty cells
])
def test_a_row_that_is_not_one_label_in_every_cell_is_not_a_section(row):
    assert not section_passes(under(row), "Cohort 1")


@pytest.mark.parametrize("data", ["Yes", "1 (Reference)", "0", "\u2014", "N/A", "1,240"])
def test_a_row_of_repeated_data_is_never_a_section_for_a_test_naming_another(data):
    row = f"<tr><td>{data}</td><td>{data}</td><td>{data}</td></tr>"
    assert not section_passes(under(row), "Cohort 1")
    assert not section_passes(under(row), "Other")
    # And it does not hide a section above it, merged or repeated
    for first in ("<tr><td colspan=3>Cohort 1</td></tr>",
                  "<tr><td>Cohort 1</td><td>Cohort 1</td><td>Cohort 1</td></tr>"):
        page = under(first + row)
        assert section_passes(page, "Cohort 1")
        assert not section_passes(page, "Other")


def test_a_test_naming_the_repeated_value_reads_its_row_as_the_section():
    # The documented price (docs/scoring/table_cell.md, case cell-section-repeated-value): tests name section
    # labels, and a page that writes the named label in every cell of a row has written that section row.
    page = under("<tr><td>Yes</td><td>Yes</td><td>Yes</td></tr>")
    assert section_passes(page, "Yes")
    assert not section_passes(page, "No")


def test_cells_that_span_rows_are_not_a_repeated_label():
    page = ("<table><tr><th>A</th><th>B</th></tr><tr><td rowspan=2>Male</td><td>Male</td></tr>"
            "<tr><td>5</td></tr><tr><td>7</td><td>6</td></tr></table>")
    assert not section_passes(page, "Male", cell="6")


def test_a_repeated_section_beside_headings_and_row_groups_keeps_both():
    page = ("<table><tr><th>Group</th><th>A</th><th>B</th></tr>"
            "<tr><td>Cohort 1</td><td>Cohort 1</td><td>Cohort 1</td></tr>"
            "<tr><td rowspan=2>Male</td><td>5</td><td>6</td></tr><tr><td>7</td><td>8</td></tr></table>")
    assert section_passes(page, "Cohort 1", cell="8", headings=("B",), row_groups=("Male",))
    assert not section_passes(page, "Cohort 1", cell="8", headings=("A",), row_groups=("Male",))
    assert not section_passes(page, "Cohort 1", cell="8", headings=("B",), row_groups=("Female",))


@pytest.mark.parametrize("first", ["<td colspan=2>Cohort 1</td>", "<td>Cohort 1</td><td>Cohort 1</td>"])
def test_a_repeated_section_matches_within_the_edits_a_merged_one_does(first):
    page = f"<table><tr><th>A</th><th>B</th></tr><tr>{first}</tr><tr><td>5</td><td>6</td></tr></table>"
    assert section_passes(page, "Cohort 2", max_diffs=1)
    assert not section_passes(page, "Cohort 2")
    assert not section_passes(page, "Other", max_diffs=1)


def test_cells_that_each_match_within_the_edits_but_differ_are_not_a_repeated_section():
    page = under("<tr><td>Cohort 1</td><td>Cohort 3</td><td>Cohort 1</td></tr>")
    assert not section_passes(page, "Cohort 2", max_diffs=1)
    assert not section_passes(page, "Cohort 1")
