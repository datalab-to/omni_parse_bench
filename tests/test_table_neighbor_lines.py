"""table_cell neighbours (`up`, `down`, `left`, `right`) match by one of their lines (`<br>`), as the cell
does."""
from __future__ import annotations

import pytest

from omni_parse_bench import score
from omni_parse_bench.scorers.unit_tests import tests as gold

EMPTY, END = {"empty": True}, {"end": True}


def verdict(cell: str, html: str, **sides) -> bool:
    args = {"cell": {"text": cell, "max_diffs": 0},
            **{k: ({"text": v, "max_diffs": 0} if isinstance(v, str) else v) for k, v in sides.items()}}
    tests = gold.parse("p", {"tests": [{"id": "a", "test_type": "table_cell", "output_type": "html",
                                        "derivation": "authored", "tags": [], "args": args, "settings": {}}]})
    return score({"html": html}, tests)[0].result == "pass"


def table(*rows: str) -> str:
    return "<table>" + "".join(f"<tr>{r}</tr>" for r in rows) + "</table>"


# sop_00056's IR: values 5 (25 °C) and 50 (125 °C), written as two rows or as one stacked cell
SPLIT = table("<td>TA=25°C</td><td rowspan=2>IR</td><td>5</td><td>µA</td>",
              "<td>TA=125°C</td><td>50</td><td>µA</td>")
STACKED = table("<td>TA=25°C<br>TA=125°C</td><td>IR</td><td>5<br>50</td><td>µA</td>")
SPACED = table("<td>TA=25°C TA=125°C</td><td>IR</td><td>5 50</td><td>µA</td>")

PROBES = [
    ("IR", {"left": "TA=125°C", "right": "5"}),
    ("µA", {"left": "5"}),
    ("1.8", {"up": "50", "down": "6"}),
]
# the third probe reads up and down: the same values in a column
SPLIT_COL = table("<td>5</td>", "<td>50</td>", "<td>1.8</td>", "<td>6</td>", "<td>7</td>")
STACKED_COL = table("<td>5<br>50</td>", "<td>1.8</td>", "<td>6<br>7</td>")
SPACED_COL = table("<td>5 50</td>", "<td>1.8</td>", "<td>6 7</td>")


@pytest.mark.parametrize("cell,sides", PROBES[:2])
def test_a_neighbour_matches_by_one_of_its_lines(cell, sides):
    assert verdict(cell, SPLIT, **sides)
    assert verdict(cell, STACKED, **sides)


def test_up_and_down_match_the_line_that_touches_the_cell():
    assert verdict("1.8", SPLIT_COL, up="50", down="6")
    assert verdict("1.8", STACKED_COL, up="50", down="6")      # the last line above, the first line below
    assert not verdict("1.8", STACKED_COL, up="5")             # a line two rows away
    assert not verdict("1.8", STACKED_COL, down="7")


@pytest.mark.parametrize("cell,sides", PROBES[:2])
def test_a_line_break_lost_still_fails(cell, sides):
    assert not verdict(cell, SPACED, **sides)


def test_a_line_break_lost_still_fails_up_and_down():
    assert not verdict("1.8", SPACED_COL, up="50", down="6")


def test_a_line_that_only_partly_matches_fails():
    page = table("<td>5 mA<br>50 mA</td><td>x</td>")
    assert not verdict("x", page, left="5")
    assert verdict("x", page, left="5 mA")


def test_the_numbers_of_a_line_are_exact():
    page = table("<td>50<br>5</td><td>x</td>")
    assert verdict("x", page, left="5")
    assert verdict("x", page, left="50")
    assert not verdict("x", page, left="55")
    assert not verdict("x", table("<td>50<br>5.0</td><td>x</td>"), left="5")
    assert not verdict("x", table("<td>50<br>500</td><td>x</td>"), left="5")


def test_the_whole_cell_still_matches():
    assert verdict("x", table("<td>5<br>50</td><td>x</td>"), left="5 50")


def test_a_heading_is_still_read_whole():
    page = table("<th>Value<br>(mg)</th>", "<td>7</td>")
    assert not verdict("7", page, top_heading="Value")
    assert verdict("7", page, top_heading="Value (mg)")


def test_empty_and_end_are_unchanged():
    # a neighbour with a line is not empty, and a cell below with a line is not the end
    assert not verdict("x", table("<td>5<br>50</td><td>x</td>"), left=EMPTY)
    assert not verdict("x", table("<td>x</td>", "<td>5<br>50</td>"), down=END)
    assert verdict("x", table("<td></td><td>x</td>"), left=EMPTY)
    assert verdict("x", table("<td>x</td><td></td>"), right=EMPTY)
    assert verdict("x", table("<td>x</td>"), down=END)


# a cell of several lines: the line it matched by aligns with the line of its neighbour
MERGED = table("<td>A<br>B</td><td>5<br>50</td>")


@pytest.mark.parametrize("cell,right,ok", [("A", "5", True), ("B", "50", True), ("A", "50", False),
                                           ("B", "5", False)])
def test_a_multi_line_cell_reads_its_neighbours_line_beside_it(cell, right, ok):
    assert verdict(cell, MERGED, right=right) is ok


def test_a_neighbour_of_another_length_fails_for_a_later_line_of_the_cell():
    page = table("<td>A<br>B</td><td>5<br>50<br>7</td>")
    assert not verdict("B", page, right="50")
    assert not verdict("B", page, right="5")
    assert verdict("A", page, right="5")      # the first line still sits beside the first line
    assert not verdict("A", page, right="50")


def test_a_single_line_neighbour_beside_a_multi_line_cell_is_read_whole_as_before():
    page = table("<td>A<br>B</td><td>5</td>")
    assert verdict("A", page, right="5")
    assert verdict("B", page, right="5")


def test_a_whole_cell_match_reads_any_line_of_the_neighbour():
    page = table("<td>A B</td><td>5<br>50</td>")     # the cell is one line (a lost break): any line
    assert verdict("A B", page, right="50")
    assert verdict("A B", page, right="5")


def test_a_multi_line_cell_reads_the_line_that_touches_its_neighbour_above_or_below():
    above = table("<td>5<br>50</td>", "<td>A<br>B</td>")      # A is the line under 50
    assert verdict("A", above, up="50")
    assert not verdict("A", above, up="5")
    assert not verdict("B", above, up="50")                   # B is two lines from 50
    below = table("<td>A<br>B</td>", "<td>5<br>50</td>")      # B is the line over 5
    assert verdict("B", below, down="5")
    assert not verdict("B", below, down="50")
    assert not verdict("A", below, down="5")


def test_blank_lines_are_left_out_before_lines_are_counted():
    assert verdict("B", table("<td>A<br>B</td><td>5<br><br>50</td>"), right="50")
    assert verdict("A", table("<td>A<br><br>B</td><td>5<br>50</td>"), right="5")
