"""Relations of layout_kind tests (M8, M16, M18) and of table_cell tests (M9)."""
from __future__ import annotations

import string

import pytest
from hypothesis import HealthCheck, assume, example, find, given, settings
from hypothesis import strategies as st
from test_invariants import answer

from metamorphic.common import HOLDS, INTENDED, LAYOUT, deviation, more_evidence, passes, relation
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
            and all(abs(area(a) - area(b)) > 1e-9 or la == lb
                    for i, (la, a) in enumerate(blocks) for lb, b in blocks[i + 1:]))


@relation(HOLDS)
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
