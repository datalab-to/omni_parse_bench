"""Relations of layout_kind tests (M8, M16, M18) and of table_cell tests (M9)."""
from __future__ import annotations

import json
import random
import re
import string
import subprocess
import sys
from pathlib import Path

import pytest
from hypothesis import HealthCheck, assume, example, find, given, settings
from hypothesis import strategies as st
from test_invariants import answer

from metamorphic.common import (CELL, HOLDS, INTENDED, LAYOUT, deviation, escaped, every_real_test,
                                more_evidence, passes, relation)
from omni_parse_bench import views
from omni_parse_bench.scorers.unit_tests import runners
from omni_parse_bench.scorers.unit_tests.runners import _area as area
from omni_parse_bench.scorers.unit_tests.runners import _intersection as intersection

LABELS = st.sampled_from(views.LABELS)
# Boxes on a 1/64 grid, and scales and shifts by powers of two, so the arithmetic is exact.
GRID_BOX = st.tuples(*[st.integers(0, 64).map(lambda k: k / 64)] * 4).map(
    lambda b: (min(b[0], b[2]), min(b[1], b[3]), max(b[0], b[2]), max(b[1], b[3])))
# Boxes at least 5% across, in any floats.
WIDE_BOX = st.tuples(*[st.floats(0, 0.5)] * 2, *[st.floats(0.05, 0.5)] * 2).map(
    lambda b: (b[0], b[1], b[0] + b[2], b[1] + b[3]))
BLOCKS = st.lists(st.tuples(LABELS, GRID_BOX), max_size=5)


def layout_passes(place, kind, blocks, scale=1.0, dx=0.0, dy=0.0) -> bool:
    """Whether a layout_kind test of `kind` at `place` passes on `blocks`, every box scaled then shifted."""
    move = lambda b: (b[0] * scale + dx, b[1] * scale + dy, b[2] * scale + dx, b[3] * scale + dy)  # noqa: E731
    test = runners.LayoutKind(runners.Text("x", 0, tuple(map(move, place))), kind)
    return runners.layout_kind(test, [views.Block(label, move(b), "") for label, b in blocks])[0]


@relation(HOLDS)
@given(st.lists(GRID_BOX, min_size=1, max_size=2), LABELS, BLOCKS, st.sampled_from([1 / 2, 1 / 4, 1 / 8, 1]),
       st.integers(0, 64), st.integers(0, 64))
def test_a_layout_verdict_survives_scaling_and_shifting_every_box(place, kind, blocks, scale, fx, fy):
    """A layout_kind verdict is the same after every box is scaled by 1/2, 1/4 or 1/8 and shifted within the
    page, boxes on a 1/64 grid so the arithmetic is exact. A second test does the same for the loaded tests'
    places in their own floats, with scales 1/2, 1/4 or 1. [M8a]
    Why it matters for a score: boxes are fractions of the page, so the page's size and margins do not
    matter."""
    # Given a place, a label and blocks on a 1/64 grid, and the verdict they give
    dx, dy = int(fx * (1 - scale)) / 64, int(fy * (1 - scale)) / 64
    verdict = layout_passes(place, kind, blocks)
    # When every box is scaled, scaled and shifted, or shifted; Then the verdict is the same
    assert layout_passes(place, kind, blocks, scale) == verdict
    assert layout_passes(place, kind, blocks, scale, dx, dy) == verdict
    assert layout_passes(place, kind, blocks, 1.0, dx, dy) == verdict


# place, kind, blocks, scale, and the fractions of the free page to shift by
INEXACT = (st.lists(WIDE_BOX, min_size=1, max_size=2), LABELS,
           st.lists(st.tuples(LABELS, WIDE_BOX), max_size=4),
           st.floats(0.05, 1), st.floats(0, 1), st.floats(0, 1))


def kept_for_m8b(place, blocks) -> bool:
    """No block within a millionth of covering half the place (M8c), and no tie of areas between blocks of
    different labels (M16)."""
    total = sum(area(b) for b in place)
    return (all(abs(sum(area(intersection(x, blk)) for x in place) / total - 0.5) > 1e-6 for _, blk in blocks)
            and all(abs(area(a) - area(b)) > 1e-7 * max(area(a), area(b)) or la == lb
                    for i, (la, a) in enumerate(blocks) for lb, b in blocks[i + 1:]))


@relation(HOLDS)
@example(place=[(0, 0, 0.1, 0.1)], kind="text", scale=0.05, fx=0.0, fy=0.0,   # areas 1e-8 apart, then 2.5e-11
         blocks=[("heading", (0, 0, 0.1000001, 0.1)), ("text", (0, 0, 0.1, 0.1))])
@given(*INEXACT)
def test_a_layout_verdict_survives_inexact_scaling_and_shifting(place, kind, blocks, scale, fx, fy):
    """A layout_kind verdict is unchanged when every box is scaled by 0.05 to 1 and shifted within the page,
    for float boxes at least 5% wide; draws with a block within 1e-6 of covering half the place (M8c) or two
    blocks of different labels with equal areas (M16) are left out. [M8b]
    Why it matters for a score: real boxes are not on a grid; float rounding must not flip a verdict."""
    # Given no block within a millionth of covering half the place (M8c) and no tie of areas (M16)
    assume(kept_for_m8b(place, blocks))
    # When every box is scaled and shifted; Then the verdict is the same
    dx, dy = fx * (1 - scale) * 0.5, fy * (1 - scale) * 0.5
    assert layout_passes(place, kind, blocks, scale, dx, dy) == layout_passes(place, kind, blocks)


@more_evidence()
def test_kept_inexact_draws_give_both_verdicts():
    """Among the draws M8b keeps, some pass and some fail, and a fixed float case passes when moved. [M8b]
    Why it matters for a score: a scorer whose layout verdicts never changed would keep M8b."""
    # Given the draws M8b keeps; Then one that passes and one that fails both exist (found by search)
    quick = settings(database=None, derandomize=True, suppress_health_check=list(HealthCheck))
    def kept_with(verdict):
        return lambda d: kept_for_m8b(d[0], d[2]) and layout_passes(d[0], d[1], d[2]) == verdict

    for verdict in (True, False):
        find(st.tuples(*INEXACT), kept_with(verdict), settings=quick)
    # And a text block over a float place passes before and after a scale of 0.37 and an odd shift
    place, block = (0.1, 0.2, 0.53, 0.31), ("text", (0.05, 0.15, 0.61, 0.37))
    assert layout_passes([place], "text", [block])
    assert layout_passes([place], "text", [block], 0.37, 0.13, 0.29)


@more_evidence(pool="layout")
@given(st.sampled_from(LAYOUT), st.lists(st.tuples(LABELS, GRID_BOX), max_size=4),
       st.sampled_from([1 / 2, 1 / 4, 1]), st.floats(0, 1), st.floats(0, 1))
def test_a_layout_verdict_survives_scaling_and_shifting_on_loaded_tests(t, extra, scale, fx, fy):
    """The same holds for a loaded test's place (its own floats), the block written for it and other blocks,
    with scales 1/2, 1/4 or 1 and shifts on a 1/64 grid. [M8a]
    Why it matters for a score: as for M8a, on places the tests really hold."""
    # Given a loaded test, the block written for it and other blocks; When all are scaled and shifted
    # Then the verdict is the same
    p = t.params
    blocks = [(p.kind, tuple(answer(t)["blocks"][0]["bbox"])), *extra]
    dx, dy = int(fx * (1 - scale) * 64) / 64, int(fy * (1 - scale) * 64) / 64
    place = p.content.place
    assert layout_passes(place, p.kind, blocks) == layout_passes(place, p.kind, blocks, scale, dx, dy)


@more_evidence()
@pytest.mark.parametrize("scale, dx, dy",
                         [(1.0, 0.0, 0.0), (0.5, 0.25, 0.0), (0.25, 0.5, 0.5), (1 / 8, 0.0, 0.75)])
def test_known_blocks_give_known_verdicts_at_every_scale_and_shift(scale, dx, dy):
    """A heading inside a table holds a place and decides its verdict, at every scale and shift. [M8a, M18]
    Why it matters for a score: M8a and M18 compare two verdicts; these fixed cases show the verdicts are not
    all the same (a scorer that passed nothing, or everything, would keep those relations)."""
    place, heading, table = (0.25, 0.25, 0.5, 0.375), (0.125, 0.125, 0.75, 0.5), (0, 0, 1, 1)
    elsewhere = (0.8, 0.8, 1, 1)
    # Given a place inside a heading block inside a table block: only a heading test passes
    both = [("table", table), ("heading", heading)]
    assert layout_passes([place], "heading", both, scale, dx, dy)
    assert not layout_passes([place], "text", both, scale, dx, dy)
    assert not layout_passes([place], "table", both, scale, dx, dy)
    # When only the table block is there, a table test passes; with no block over the place, none does
    assert layout_passes([place], "table", [("table", table)], scale, dx, dy)
    assert not layout_passes([place], "heading", [], scale, dx, dy)
    assert not layout_passes([place], "table", [("table", elsewhere)], scale, dx, dy)


@relation(HOLDS)
@example(place=(0.623881554931733, 0.0, 0.9572148882650664, 0.5), kind="text", scale=0.375)
@given(WIDE_BOX, st.sampled_from(["text", "table"]), st.floats(0.05, 1))
def test_a_block_covering_exactly_half_a_place_holds_it_at_every_scale(place, kind, scale):
    """A block covering exactly half of a place covers it, and one covering a millionth less does not, before
    and after both are scaled by 0.05 to 1 (scale only, no shift). [M8c]
    Why it matters for a score: the 50% threshold must not depend on float rounding of the areas."""
    # Given a block that is the left half of a place; When both are scaled; Then it still holds the place
    half = (place[0], place[1], (place[0] + place[2]) / 2, place[3])
    assert layout_passes([place], kind, [(kind, half)])
    assert layout_passes([place], kind, [(kind, half)], scale)
    # And a block just under half of the place does not hold it, so no block does
    under = (place[0], place[1], place[0] + (place[2] - place[0]) * (0.5 - 1e-6), place[3])
    assert not layout_passes([place], kind, [(kind, under)])
    assert not layout_passes([place], kind, [(kind, under)], scale)


@relation(INTENDED)
@deviation("M16")
@example(place=(0.25, 0.25, 0.5, 0.5), first="text", second="heading")
@given(WIDE_BOX, LABELS, LABELS)
def test_the_order_of_two_blocks_with_one_box_does_not_change_a_layout_verdict(place, first, second):
    """Two blocks with the same box over a place give the same verdict in either order. [M16]
    Why it matters for a score: the docs choose the first listed of two blocks of equal area, so for such an
    output the verdict follows the order the system lists its blocks in."""
    # Given two blocks of different labels with the place's own box; When listed in either order
    # Then a text test gets the same verdict
    assume(first != second)
    assert layout_passes([place], "text", [(first, place), (second, place)]) == \
        layout_passes([place], "text", [(second, place), (first, place)])


@relation(HOLDS, domain="boxes on a 1/10 grid")
@example(x=2, y=8, w=2, h=1)
@given(st.integers(0, 5), st.integers(0, 5), st.integers(1, 4), st.integers(1, 4))
def test_of_two_blocks_with_equal_areas_the_first_listed_holds_the_place(x, y, w, h):
    """Two blocks over a place whose areas are equal in exact arithmetic, a w x h box and an h x w box from
    one corner (in tenths of the page), hold the place in list order: the first listed decides the verdict.
    [M26]
    Why it matters for a score: the docs promise 'on equal areas, the first listed'; float rounding of the
    areas must not reverse it."""
    # Given a place, and two blocks from its corner, w x h and h x w tenths: equal areas, different boxes
    assume(w != h)
    x0, y0, s = x / 10, y / 10, min(w, h) / 10
    place = (x0, y0, x0 + s, y0 + s)
    wide, tall = (x0, y0, (x + w) / 10, (y + h) / 10), (x0, y0, (x + h) / 10, (y + w) / 10)
    # When either is listed first; Then a test of the first one's label passes
    assert layout_passes([place], "heading", [("heading", wide), ("text", tall)])
    assert layout_passes([place], "heading", [("heading", tall), ("text", wide)])


@relation(HOLDS)
@given(st.lists(GRID_BOX, min_size=1, max_size=2), LABELS, BLOCKS, GRID_BOX, LABELS)
def test_a_block_away_from_the_place_does_not_change_a_layout_verdict(place, kind, blocks, extra, label):
    """Adding a block that shares no area with a place leaves its layout_kind verdict the same. [M18]
    Why it matters for a score: a test grades its own line, not the rest of the page."""
    # Given a layout test, blocks, and one more block that shares no area with the place
    assume(all(area(intersection(x, extra)) == 0 for x in place))
    # When it is added last or first; Then the verdict is the same
    verdict = layout_passes(place, kind, blocks)
    assert layout_passes(place, kind, [*blocks, (label, extra)]) == verdict
    assert layout_passes(place, kind, [(label, extra), *blocks]) == verdict

# -------------------------------------------------------------------------------------------- tables

CELLS = st.lists(st.text(string.ascii_uppercase, min_size=3, max_size=4), min_size=12, max_size=12,
                 unique=True)


def table_html(rows) -> str:
    """A table whose first row is headings (<th>) and the rest cells (<td>)."""
    tag = lambda i: "th" if i == 0 else "td"  # noqa: E731
    return "<table>" + "".join("<tr>" + "".join(f"<{tag(i)}>{x}</{tag(i)}>" for x in r) + "</tr>"
                               for i, r in enumerate(rows)) + "</table>"


@relation(HOLDS, domain="4x3 tables of distinct cells (3-4 capital letters), 6 row orders")
@given(CELLS, st.permutations(range(3)))
def test_shuffling_body_rows_keeps_row_relations_and_changes_up(cells, order):
    """Shuffling a table's body rows keeps each cell's left, right and top_heading test passing, and its `up`
    test fails exactly where the cell above it changed. [M9a]
    Why it matters for a score: table_cell grades the relations a reordering broke, and only those."""
    # Given a 4 x 3 table of distinct cells under a heading row; When its body rows are permuted
    rows = [cells[i:i + 3] for i in range(0, 12, 3)]
    new = [rows[0], *(rows[1 + k] for k in order)]
    for i, row in enumerate(rows[1:], 1):
        for j, x in enumerate(row):
            # Then row relations pass, and `up` passes exactly when the cell above is still the old one
            near = {"top_heading": rows[0][j], **({"left": row[j - 1]} if j else {}),
                    **({"right": row[j + 1]} if j < 2 else {})}
            assert passes(runners.TableCell(x, near, 0), table_html(new)), (i, j)
            above_now = next(new[a - 1][j] for a, r in enumerate(new) if r[j] == x)
            up_passes = passes(runners.TableCell(x, {"up": rows[i - 1][j]}, 0), table_html(new))
            assert up_passes == (above_now == rows[i - 1][j])


@relation(HOLDS, domain="4x3 tables of distinct cells (3-4 capital letters), 3 column pairs")
@given(CELLS, st.sampled_from([(0, 1), (0, 2), (1, 2)]))
def test_swapping_two_columns_fails_their_headings_unless_the_headings_move_too(cells, cols):
    """Swapping two body columns under fixed headings fails their cells' `headings` tests, unless the headings
    swap too (M9a uses `top_heading`). [M9b]
    Why it matters for a score: a cell's heading test follows the column the cell is in."""
    # Given a 4 x 3 table of distinct cells under a heading row, and each body cell's heading test
    rows = [cells[i:i + 3] for i in range(0, 12, 3)]
    a, b = cols

    def swap(r):
        r = list(r)
        r[a], r[b] = r[b], r[a]
        return r

    # When two body columns swap under fixed headings, or swap with their headings
    # Then the test passes before, fails after the first swap, and passes after the second
    for row in rows[1:]:
        for j in (a, b):
            p = runners.TableCell(row[j], {}, 0, headings=(rows[0][j],))
            assert passes(p, table_html(rows))
            assert not passes(p, table_html([rows[0], *map(swap, rows[1:])]))
            assert passes(p, table_html([swap(r) for r in rows]))


@relation(HOLDS, domain="3x3 tables of distinct cells (3-4 capital letters), each cell a heading or not")
@given(CELLS, st.lists(st.booleans(), min_size=9, max_size=9))
def test_mirroring_every_row_swaps_left_heading_and_right_heading(cells, heads):
    """Writing every row of a table in the reverse order of its cells gives each cell the same
    `right_heading` verdict as its `left_heading` verdict had, and the reverse; any cell of its row may be
    named. [M27]
    Why it matters for a score: a right-to-left table written in reading order and its left-to-right mirror
    are graded alike, as the roles promise."""
    # Given a 3 x 3 table of distinct cells, some of them headings, and the same table with each row reversed
    grid = [[(cells[3 * r + c], heads[3 * r + c]) for c in range(3)] for r in range(3)]

    def cell_html(x, h):
        return f"<{'th' if h else 'td'}>{x}</{'th' if h else 'td'}>"

    def page(g):
        rows = ("<tr>" + "".join(cell_html(x, h) for x, h in row) + "</tr>" for row in g)
        return "<table>" + "".join(rows) + "</table>"

    mirror = [row[::-1] for row in grid]
    # When each cell is tested against each cell of its row as its left or right heading
    for row in grid:
        for x, _ in row:
            for want, _ in row:
                # Then the verdicts swap with the mirror
                for here, there in (("left_heading", "right_heading"), ("right_heading", "left_heading")):
                    one = passes(runners.TableCell(x, {here: want}, 0), page(grid))
                    other = passes(runners.TableCell(x, {there: want}, 0), page(mirror))
                    assert one == other, (x, want, here)

# ------------------------------------------------------------------------- empty cells and table ends

EMPTY, END = {"empty": True}, {"end": True}
BLANKS = ["<td></td>", "<td> </td>", "<td>&nbsp;</td>", "<td><br></td>", "<td>​</td>", "<td><p></p></td>",
          "<td>...</td>", "<th></th>"]
TOKENS = st.sampled_from(["x", "0", "-", "N/A", "100", "a b", "<img alt='icon'>"])
HOLE = st.tuples(st.integers(1, 3), st.integers(0, 2))     # a body cell of a 4 x 3 table, to blank


def shaped(cell: str, **sides) -> runners.TableCell:
    """A table_cell test of `cell` whose sides are text, or {"empty": true} / {"end": true}."""
    return runners.TableCell(cell, {k: v for k, v in sides.items() if isinstance(v, str)}, 0,
                             shapes={k: next(iter(v)) for k, v in sides.items() if isinstance(v, dict)})


def grid_html(rows, hole=None, blank="<td></td>", swallow=False, drop=False, tail=()) -> str:
    """The table of `rows` (first row <th>), with its `hole` cell written as `blank`: or left
    out (`drop`), or, with `swallow`, left out and the cell before it spanning two columns. `tail` are
    cells appended to the last row."""
    out = []
    for i, row in enumerate(rows):
        cells = []
        for j, x in enumerate(row):
            tag = "th" if i == 0 else "td"
            if (i, j) == hole:
                cells += [] if swallow or drop else [blank]
            else:
                span = " colspan=2" if swallow and hole == (i, j + 1) else ""
                cells.append(f"<{tag}{span}>{x}</{tag}>")
        out.append("<tr>" + "".join(cells) + "".join(tail if i == len(rows) - 1 else ()) + "</tr>")
    return "<table>" + "".join(out) + "</table>"


def beside(rows, i, j):
    """Each side of the hole at (i, j) that has a cell, with the cell that anchors it: (side, anchor, what the
    anchor's own test names as its column heading)."""
    found = [("right", rows[i][j - 1]) if j else None, ("left", rows[i][j + 1]) if j < 2 else None,
             ("down", rows[i - 1][j]) if i > 1 else None, ("up", rows[i + 1][j]) if i < 3 else None]
    return [x for x in found if x]


def side_test(rows, i, j, side, anchor):
    return shaped(anchor, **{side: EMPTY})


@relation(HOLDS, domain="4x3 tables of distinct cells, one body cell blank in 8 spellings (a dropped "
                        "trailing cell too), as html and as a markdown pipe table")
@given(CELLS, HOLE, st.sampled_from(BLANKS))
def test_every_spelling_of_a_blank_cell_is_empty(cells, hole, blank):
    """A body cell written as nothing, white space, `&nbsp;`, `<br>`, an invisible character, an empty
    element, a leader (`...`), a blank `<th>`, a trailing cell left out, or an empty markdown cell is
    `empty` for the cell beside it, on each side. [M93]
    Why it matters for a score: a system that draws an empty cell in any of these ways is graded as one that
    leaves it empty."""
    # Given a 4 x 3 table with one body cell blank, and each neighbour's `empty` test on that side
    rows = [cells[i:i + 3] for i in range(0, 12, 3)]
    i, j = hole
    # When the blank is written in any spelling (or left out at the end of a row, or in markdown)
    pages = [grid_html(rows, hole, blank)]
    if j == 2:
        pages.append(grid_html(rows, hole, drop=True))
    line = lambda r: "| " + " | ".join(r) + " |"  # noqa: E731

    def pipe(fill: str) -> str:
        md = [line(rows[0]), "|---|---|---|", *(line([fill if (a, b) == hole else x for b, x in enumerate(r)])
                                                  for a, r in enumerate(rows) if a)]
        return views.html(markdown_html("\n".join(md))).html

    pages.append(pipe(""))
    # And the same cell holding a token, in a td, a th or a markdown cell
    filled = [grid_html(rows, hole, "<td>x</td>"), grid_html(rows, hole, "<th>x</th>"), pipe("x")]
    # Then every blank one passes, and every filled one fails
    for side, anchor in beside(rows, i, j):
        for page in pages:
            assert passes(side_test(rows, i, j, side, anchor), page), (side, anchor, page)
        for page in filled:
            assert not passes(side_test(rows, i, j, side, anchor), page), (side, anchor, page)


def markdown_html(md: str) -> str:
    from omni_parse_bench import markdown
    return markdown.to_html(md)


@relation(HOLDS, domain="4x3 tables of distinct cells, one body cell blank; 7 tokens put in it, the value "
                        "beyond it shifted in, or a cell merged over it")
@given(CELLS, HOLE, TOKENS)
def test_any_content_in_a_blank_cell_or_a_shift_or_a_merge_fails_empty(cells, hole, token):
    """A token written in a blank cell (a copy of its neighbour, an invented value, an image), the values
    shifted one cell into it, or the cell beside it merged over it fails that neighbour's `empty` test, while
    the blank table passes. [M94]
    Why it matters for a score: an output that fills, shifts or merges an empty cell does not pass for
    leaving it empty."""
    rows = [cells[i:i + 3] for i in range(0, 12, 3)]
    i, j = hole
    # Given the blank table passes each neighbour's `empty` test
    for side, anchor in beside(rows, i, j):
        test = side_test(rows, i, j, side, anchor)
        assert passes(test, grid_html(rows, hole))
        # When a token fills the cell, or the anchor's own value is copied into it, Then the test fails
        assert not passes(test, grid_html(rows, hole, f"<td>{token}</td>"))
        assert not passes(test, grid_html(rows, hole, f"<td>{anchor}</td>"))
    # When the values on one side shift a cell into the hole (either way, along the row or down the column),
    # the blank moves to the end it left: Then every anchor's test that passed now fails (a shift that moves
    # nothing is skipped)
    held = [["" if (a, b) == hole else x for b, x in enumerate(r)] for a, r in enumerate(rows)]
    row, col = held[i], [r[j] for r in held]
    shifts = [(row[:j] + row[j + 1:] + [""], (i, 2), "row"), ([""] + row[:j] + row[j + 1:], (i, 0), "row"),
              (col[:i] + col[i + 1:] + [""], (3, j), "col"),
              ([col[0], ""] + col[1:i] + col[i + 1:], (1, j), "col")]
    for new, at, along in shifts:
        if new == (row if along == "row" else col):
            continue
        shifted = [list(r) for r in rows]
        for k, x in enumerate(new):
            shifted[i if along == "row" else k][k if along == "row" else j] = x
        for side, anchor in beside(rows, i, j):
            test = side_test(rows, i, j, side, anchor)
            assert passes(test, grid_html(rows, hole))
            assert not passes(test, grid_html(shifted, at)), (side, anchor, along, at)
    # When a cell is merged over the blank (colspan), Then `right: empty` fails on the merged cell
    if j:
        assert passes(shaped(rows[i][j - 1], right=EMPTY), grid_html(rows, hole))
        assert not passes(shaped(rows[i][j - 1], right=EMPTY), grid_html(rows, hole, swallow=True))


@relation(HOLDS, domain="4x3 tables of distinct cells with two blanks, every body cell, `empty` and `end`")
@given(CELLS, st.lists(st.tuples(st.integers(1, 3), st.integers(0, 2)), min_size=1, max_size=2, unique=True))
def test_reversing_every_row_swaps_left_and_right_for_empty_and_end(cells, holes):
    """Writing every row of a table in the reverse order of its cells gives each cell the same `right`
    verdict for `empty` and for `end` as its `left` verdict had, and the reverse. [M95]
    Why it matters for a score: a right-to-left table written in reading order and its left-to-right mirror
    are graded alike, as for M27."""
    # Given a table with blank cells and the table with each row reversed
    rows = [list(cells[i:i + 3]) for i in range(0, 12, 3)]
    shown = [["" if (a, b) in holes else x for b, x in enumerate(r)] for a, r in enumerate(rows)]
    page = lambda g: "<table>" + "".join("<tr>" + "".join(  # noqa: E731
        f"<{'th' if a == 0 else 'td'}>{x}</{'th' if a == 0 else 'td'}>" for x in r) + "</tr>"
        for a, r in enumerate(g)) + "</table>"
    # When each cell is tested for each flag on each side; Then the verdicts swap with the mirror
    for a, r in enumerate(rows):
        for b, x in enumerate(r):
            if (a, b) in holes: continue
            for flag in (EMPTY, END):
                for here, there in (("left", "right"), ("right", "left")):
                    one = passes(shaped(x, **{here: flag}), page(shown))
                    other = passes(shaped(x, **{there: flag}), page([r[::-1] for r in shown]))
                    assert one == other, (x, here, flag)


@relation(HOLDS, domain="4x3 tables of distinct cells; empty rows and columns, `<thead>`/`<tbody>`, a later "
                        "table, a markdown table; row and column tails of 7 tokens")
@given(CELLS, TOKENS, st.integers(0, 2))
def test_end_ignores_blank_rows_and_columns_and_fails_on_any_text(cells, token, extra):
    """The last body cell of a table passes `down: end` and `right: end` however many empty rows or columns
    follow it, with a `<thead>` and `<tbody>`, with another table after it, and as a markdown table; it fails
    with any token in a row below or a column beside it, in any cell of it; the first cell fails `up: end`
    under a row of text. [M96]
    Why it matters for a score: an invented row or column fails, and an empty one invents nothing."""
    rows = [cells[i:i + 3] for i in range(0, 12, 3)]
    last = rows[3][2]
    both = shaped(last, down=END, right=END)
    plain = grid_html(rows)
    # Given the last cell passes on the plain table
    assert passes(both, plain)
    # When blank rows or columns follow, or the table is wrapped, or another table follows, or it's markdown
    blank_row = "<tr>" + "<td></td>" * 3 + "</tr>"
    for page in (plain.replace("</table>", blank_row * (extra + 1) + "</table>"),
                 grid_html(rows, tail=["<td>&nbsp;</td>"] * (extra + 1)),
                 plain.replace("<tr>", "<thead><tr>", 1).replace("</tr>", "</tr></thead><tbody>", 1)
                      .replace("</table>", "</tbody></table>"),
                 plain + "<table><tr><td>zz</td></tr></table>",
                 views.html(markdown_html("\n".join(
                     ["| " + " | ".join(rows[0]) + " |", "|---|---|---|",
                      *("| " + " | ".join(r) + " |" for r in rows[1:])]))).html):
        assert passes(both, page), page
    # When any cell of a new row or column holds text; Then `end` fails on that side only
    for k in range(3):
        row = "<tr>" + "".join(f"<td>{token}</td>" if c == k else "<td></td>" for c in range(3)) + "</tr>"
        page = plain.replace("</table>", blank_row + row + "</table>")
        assert not passes(shaped(last, down=END), page) and passes(shaped(last, right=END), page)
    for k in range(1, 4):
        wide = [row + [token if n == k else ""] for n, row in enumerate(rows)]
        html = grid_html(wide)
        assert not passes(shaped(last, right=END), html) and passes(shaped(last, down=END), html)
    # When a row of text is put above; Then `up: end` fails for the heading cell
    assert passes(shaped(rows[0][0], up=END), plain)
    above = plain.replace("<table>", f"<table><tr><td>{token}</td></tr>")
    assert not passes(shaped(rows[0][0], up=END), above)


SIDES = ("up", "down", "left", "right")


def sided(t) -> list[str]:
    """The sides of a real table_cell test that name a neighbour's text."""
    return [k for k in SIDES if k in t.params.relations]


def distinct(t) -> bool:
    """Whether no neighbour's text reads like the cell (else the neighbour is a second place the cell matches,
    and the test may pass there)."""
    cell = runners._fold_cell(t.params.cell)
    return all(runners._cell_ratio(cell, runners._fold_cell(x)) < 0.5
               for k, x in t.params.relations.items() if k in SIDES)


SIDED = [t for t in CELL if sided(t) and distinct(t)]


def render(grid) -> str:
    return "<table>" + "".join("<tr>" + "".join(f"<td>{escaped(x)}</td>" for x in r) + "</tr>"
                               for r in grid) + "</table>"


@every_real_test("table sides", note="each on its own 3 x 3 table, passing first")
def test_turning_a_real_neighbour_into_empty_or_end_fails_it():
    """A real table_cell test with a neighbour (`up`, `down`, `left`, `right`) unlike its cell passes on a
    3 x 3 table holding its cell in the middle and each neighbour's text beside it, and fails there once
    any one side's text is replaced by `{"empty": true}` or `{"end": true}`; adding either flag on a side the
    test does not name never turns a fail into a pass, on that table or one with an invented row, column or
    blank. [M94]
    Why it matters for a score: as for M94, over the dataset's own strings: a real neighbour is content the
    page prints there, so a test that says it is empty or past the end fails on it."""
    # Given each real test with a neighbour unlike its cell, and the 3 x 3 table its strings fill
    bad = []
    for t in SIDED:
        # (its headings, section and row groups are not on the table, so they are left out)
        p = t.params._replace(relations={k: t.params.relations[k] for k in sided(t)}, headings=(),
                              section=None, row_groups=())
        grid = [["", p.relations.get("up", ""), ""],
                [p.relations.get("left", ""), p.cell, p.relations.get("right", "")],
                ["", p.relations.get("down", ""), ""]]
        page = render(grid)
        if not passes(p, page):
            bad.append((t.id, "base"))
            continue
        # When a side's text becomes a flag; Then the test fails on the table, which holds that text there
        for side in sided(t):
            for flag in ("empty", "end"):
                shape = p._replace(relations={k: v for k, v in p.relations.items() if k != side},
                                   shapes={**p.shapes, side: flag})
                if passes(shape, page):
                    bad.append((t.id, side, flag))
        # And adding `empty` or `end` on a side the test does not name only adds failures: on this table, with
        # an invented row or column, and with the up neighbour blanked, a pass with the flag is a pass without
        pages = [page, render([*grid, ["", "zz", ""]]), render([r + ["zz"] for r in grid]),
                 render([[("" if (a, b) == (0, 1) else x) for b, x in enumerate(r)]
                         for a, r in enumerate(grid)])]
        for side in set(SIDES) - set(sided(t)):
            for flag in ("empty", "end"):
                more = p._replace(shapes={side: flag})
                bad += [(t.id, side, flag, "adds a pass") for pg in pages
                        if passes(more, pg) and not passes(p, pg)]
    assert not bad, f"{len(bad)} cases, e.g. {bad[:5]}"


# ------------------------------------------------------------------ a test without the new args is unchanged

OLD_COMMIT = "416c17b"    # main before `empty` and `end`
ROOT = Path(__file__).resolve().parents[2]
RUNNER = """
import json, sys
sys.path.insert(0, sys.argv[1])
from omni_parse_bench import views
from omni_parse_bench.scorers.unit_tests import runners
out = []
for params, page in json.load(sys.stdin):
    cell, relations, max_diffs, headings, section, row_groups = params
    t = runners.TableCell(cell, relations, max_diffs, tuple(headings), section, tuple(row_groups))
    out.append(list(runners.table_cell(t, views.html(page))))
json.dump(out, sys.stdout)
"""


@pytest.fixture(scope="module")
def old_package(tmp_path_factory):
    """The package at OLD_COMMIT, checked out from git into a folder of its own and run in a subprocess, so it
    shares no code with the working tree. Skipped when the history does not hold that commit."""
    if subprocess.run(["git", "cat-file", "-e", OLD_COMMIT], cwd=ROOT, capture_output=True).returncode:
        pytest.skip(f"needs git history holding {OLD_COMMIT}")
    where = tmp_path_factory.mktemp("old")
    tar = subprocess.run(["git", "archive", OLD_COMMIT, "omni_parse_bench"], cwd=ROOT, check=True,
                         capture_output=True).stdout
    subprocess.run(["tar", "-x", "-C", str(where)], input=tar, check=True)
    return where


def old_verdicts(old_package, cases) -> list[tuple[bool, str]]:
    """The old package's `table_cell` verdict and why for each (params, page)."""
    jobs = [([c.cell, dict(c.relations), c.max_diffs, list(c.headings), c.section, list(c.row_groups)], page)
            for c, page in cases]
    done = subprocess.run([sys.executable, "-I", "-c", RUNNER, str(old_package)], input=json.dumps(jobs),
                          check=True, capture_output=True, text=True).stdout
    return [tuple(x) for x in json.loads(done)]


def page_for(p: runners.TableCell) -> str:
    """A table meant to satisfy the test: row groups, left heading and left, then the cell, right and right
    heading across; the headings, top heading, section label, `up`, the cell's row and `down` down."""
    rel = p.relations
    cols = [*p.row_groups, *([rel["left_heading"]] if "left_heading" in rel else []),
            *([rel["left"]] if "left" in rel else []), p.cell, *([rel["right"]] if "right" in rel else []),
            *([rel["right_heading"]] if "right_heading" in rel else [])]
    k = len(p.row_groups) + ("left_heading" in rel) + ("left" in rel)
    if p.section and len(cols) == 1:
        cols.append("")      # a section row needs a second cell to be a label row
    heads = {*([len(p.row_groups)] if "left_heading" in rel else []),
             *([len(cols) - 1] if "right_heading" in rel else [])}

    def row(vals: dict[int, str], th=()) -> str:
        return "<tr>" + "".join(
            f"<{'th' if i in th else 'td'}>{escaped(vals.get(i, ''))}</{'th' if i in th else 'td'}>"
            for i in range(len(cols))) + "</tr>"

    rows = [row({k: h}, {k}) for h in p.headings]
    rows += [row({k: rel["top_heading"]}, {k})] if "top_heading" in rel else []
    label = f"<tr><td>{escaped(p.section)}</td>{'<td></td>' * (len(cols) - 1)}</tr>" if p.section else ""
    rows += [label] if label else []
    rows += [row({k: rel["up"]})] if "up" in rel else []
    rows += [row(dict(enumerate(cols)), heads)]
    rows += [row({k: rel["down"]})] if "down" in rel else []
    return "<table>" + "".join(rows) + "</table>"


def pages_around(p: runners.TableCell) -> list[str]:
    """`page_for(p)` and altered pages: a row and a column appended, each cell blanked in turn, the cell's
    text changed."""
    base = page_for(p)
    soup = [m for m in re.finditer(r"<td>([^<]*)</td>", base)]
    blanked = [base[:m.start()] + "<td></td>" + base[m.end():] for m in soup[:12]]
    changed = [base[:m.start()] + f"<td>{m[1]}x</td>" + base[m.end():] for m in soup[:12]]
    return [base, base.replace("</table>", "<tr><td>zz</td></tr></table>"),
            base.replace("</tr>", "<td>zz</td></tr>"), *blanked, *changed]


def same_as_before(old_package, tests) -> tuple[int, int, list]:
    """(pages compared, pages the new code passes, the (id, page) pairs where old and new differ)."""
    cases = [(t.params, page) for t in tests for page in pages_around(t.params)]
    old = old_verdicts(old_package, cases)
    new = [runners.table_cell(c, views.html(page)) for c, page in cases]
    names = [t.id for t in tests for _ in pages_around(t.params)]
    return (len(cases), sum(n[0] for n in new),
            [(i, page[:80]) for i, (_, page), o, n in zip(names, cases, old, new, strict=True)
             if tuple(n) != o])


@relation(HOLDS, domain="20 random 4x3 tables with blanks, a figure or a span, 36 tests each (9 cells, 4 "
                        "kinds), 720 in all; needs git history holding 416c17b")
def test_a_table_cell_test_without_empty_or_end_gives_the_verdict_it_gave_before(old_package):
    """A table_cell test with no `empty` or `end` arg gets the verdict and the why that the package at
    416c17b gives (run from git in a subprocess, sharing no code), on 20 random tables of cells, blanks,
    spans and figures (720 tests): for each body cell its neighbours, headings, row groups and section, true
    or altered. [M97]
    Why it matters for a score: the new args, and the table reader's figure flag, change no existing
    test's score."""
    # Given random 4 x 3 tables with blanks, one figure or span, and tests drawn from each body cell
    rnd = random.Random(97)
    word = lambda: "".join(rnd.choices(string.ascii_uppercase, k=3))  # noqa: E731
    cases = []
    for _ in range(20):
        rows = [[word() for _ in range(3)] for _ in range(4)]
        held = [[x if rnd.random() > 0.25 else "" for x in r] for r in rows]
        first = rnd.choice(["<td><img src=a.png>", "<td colspan=2>", "<td rowspan=2>", "<td><img alt=''>"])
        page = grid_html(held).replace("<td>", first, 1)
        for a in range(1, 4):
            for b in range(3):
                near = {"up": rows[a - 1][b], "top_heading": rows[0][b],
                        **({"left": rows[a][b - 1]} if b else {}),
                        **({"right": rows[a][b + 1]} if b < 2 else {}),
                        **({"down": rows[a + 1][b]} if a < 3 else {})}
                for params in (runners.TableCell(rows[a][b], near, 0),
                               runners.TableCell(rows[a][b], {**near, "up": "ZZZ"}, 0),
                               runners.TableCell(rows[a][b], {}, 0, headings=(rows[0][b],),
                                                 row_groups=(rows[a][0],)),
                               runners.TableCell(rows[a][b], {}, 0, section="ZZZ")):
                    cases.append((params, page))
    # When the old package and this one grade them; Then the verdicts and the whys are equal
    old = old_verdicts(old_package, cases)
    new = [tuple(runners.table_cell(c, views.html(page))) for c, page in cases]
    differ = [(c, page) for (c, page), o, n in zip(cases, old, new, strict=True) if o != n]
    assert not differ, f"{len(differ)}/{len(cases)} differ, e.g. {differ[:2]}"
    assert {n[0] for n in new} == {True, False}, "the cases hold both verdicts"


@every_real_test("table tests", note="a page built for each, and altered pages, old package against new")
def test_every_real_table_cell_test_keeps_its_old_verdict(old_package):
    """Every real table_cell test (none has an `empty` or `end` arg) gets the verdict and the why that the
    package at 416c17b gives, on a page built to satisfy it (all of them pass there) and on altered pages: a
    row and a column appended, each cell blanked in turn, a cell's text changed. [M97]
    Why it matters for a score: as for M97, over the dataset's own tests."""
    # Given every real test, a table holding its strings, headings, row groups and section, and altered ones
    compared, passed, differ = same_as_before(old_package, CELL)
    # When the old package and this one grade them; Then they agree on every page, and each built page passes
    assert not differ, f"{len(differ)}/{compared} pages differ, e.g. {differ[:5]}"
    built = [runners.table_cell(t.params, views.html(page_for(t.params)))[0] for t in CELL]
    assert all(built), f"{built.count(False)}/{len(CELL)} built pages do not pass, so the check is thinner"
