"""HTML tables as grids of cells, for the table test types.

`parse(html)` reads every <table> into a `Table`: each cell's text keyed by its top-left grid
position, which cells are headings, and each cell's neighbours in the four directions:

    <table><tr><th>Year</th><th>Total</th></tr>
           <tr><td>2024</td><td>1,240</td></tr></table>

    text      {(0, 0): "Year", (0, 1): "Total", (1, 0): "2024", (1, 1): "1,240"}
    headings  {(0, 0), (0, 1)}
    up        {(1, 1): {(0, 1)}, ...}

A cell spanning several rows or columns occupies each grid slot it covers but is stored once, so
it can have several neighbours in one direction. `heading(table, cell, "up")` walks up from a cell
to the heading cells above it, or, when there are none, to the cells at the edge of the table.

`above`, `beside` and `section` read a cell's place off the grid: the cells over its columns (top
to bottom), the cells to its left in its rows (left to right), and the run of section rows nearest
above it. A section row is a row of one label, in its first column followed by empty cells
(`label_rows`) or merged across the table; an empty slot in one reads as its label.

A rewrite of olmOCR-bench's table parser (https://github.com/allenai/olmocr, Apache-2.0; see NOTICE).
"""
from __future__ import annotations

import functools
from collections.abc import Iterator
from typing import Literal, NamedTuple

from omni_parse_bench import views

Cell = tuple[int, int]
Direction = Literal["up", "down", "left", "right"]

MAX_SPAN = 1000   # a colspan or rowspan past this is read as this: no page's table is wider or longer


class Table(NamedTuple):
    text: dict[Cell, str]
    headings: frozenset[Cell]
    up: dict[Cell, frozenset[Cell]]
    down: dict[Cell, frozenset[Cell]]
    left: dict[Cell, frozenset[Cell]]
    right: dict[Cell, frozenset[Cell]]
    grid: tuple[tuple[Cell | None, ...], ...]   # which cell covers each slot, row by row
    covers: dict[Cell, tuple[tuple[int, ...], tuple[int, ...]]]   # the rows and the columns each cell covers
    labels: dict[int, Cell]   # the section rows (`label_rows`), by row


@functools.lru_cache(maxsize=16)
def parse(html: str) -> tuple[Table, ...]:
    """Every table in `html` with at least one cell."""
    out = []
    # Note: a soup of its own, because <br> tags are rewritten in place below.
    for tag in _fresh_soup(html).find_all("table"):
        rows = tag.find_all("tr")
        specs = []
        for r, tr in enumerate(rows):
            in_thead = tr.find_parent("thead") is not None
            row = []
            for td in tr.find_all(["th", "td"], recursive=False):
                for br in td.find_all("br"):
                    br.replace_with("\n")
                raw_rowspan = td.get("rowspan")
                # Note: rowspan="0" means "to the end of the table section".
                to_end = isinstance(raw_rowspan, str) and raw_rowspan.strip() == "0"
                rowspan = max(1, len(rows) - r) if to_end else _span(raw_rowspan)
                row.append((_text(td), rowspan, _span(td.get("colspan")), td.name == "th" or in_thead))
            specs.append(row)
        if specs and (table := _grid(specs)):
            out.append(table)
    return tuple(out)


def _text(td) -> str:
    """A cell's text, read the way the page's text is (`views.text`): inputs, alt text and math."""
    return views.text(td.decode_contents()).strip()


def heading(table: Table, cell: Cell, direction: Direction) -> frozenset[Cell]:
    """The heading cells reached walking from `cell` in `direction`, else the cells at the edge.
    An empty heading cell (a blank corner, a header row's gap) isn't a heading: the walk goes on."""
    step = getattr(table, direction)
    seen, todo, headings, ends = set(), {cell}, set(), set()
    while todo:
        c = todo.pop()
        seen.add(c)
        if c in table.headings and table.text.get(c, "").strip(): headings.add(c)
        if nxt := step.get(c): todo |= nxt - seen
        else: ends.add(c)
    return frozenset((headings or ends) - {cell})


def above(table: Table, cell: Cell) -> list[Cell]:
    """The cells over `cell`'s columns, top to bottom. An empty slot in a section row (`label_rows`)
    reads as the row's label: a section header written as its label and empty cells. Any other empty
    slot reads as the nearest non-empty cell to its left in its row: a heading over several columns
    written once, beside empty cells, as a printed table shows a merged heading."""
    labels = label_rows(table)
    rows, cols = _covered(table, cell)
    out: list[Cell] = []
    for r in range(min(rows)):
        for c in cols:
            x = table.grid[r][c]
            if _empty(table, x):
                x = labels[r] if r in labels else _filled(table, ((r, j) for j in range(c - 1, -1, -1)))
            if x is not None and x != cell and x not in out: out.append(x)
    return out


def beside(table: Table, cell: Cell) -> list[Cell]:
    """The cells to the left of `cell` in its rows, left to right. An empty slot reads as the nearest
    non-empty cell above it in its column, up to the header: a row label over several rows written
    once, above empty cells, as a printed table shows a merged label."""
    rows, cols = _covered(table, cell)
    out: list[Cell] = []
    for c in range(min(cols)):
        for r in rows:
            x = table.grid[r][c]
            if _empty(table, x):
                x = _filled(table, ((i, c) for i in range(r - 1, -1, -1)), stop=table.headings)
            if x is not None and x not in out: out.append(x)
    return out


def _empty(table: Table, x: Cell | None) -> bool:
    return x is None or not table.text[x].strip()


def _filled(table: Table, slots, stop: frozenset[Cell] = frozenset()) -> Cell | None:
    """The first non-empty cell along `slots`; None at a cell in `stop` or when there is none."""
    for r, c in slots:
        x = table.grid[r][c] if c < len(table.grid[r]) else None
        if x in stop: return None
        if not _empty(table, x): return x
    return None


def section(table: Table, cell: Cell) -> list[str]:
    """The labels of the section rows nearest above `cell`, top to bottom: the consecutive run of
    them closest to it ("1982" then "Age"), or [] when no section row is above it."""
    labels = label_rows(table)
    width = len(table.grid[0]) if table.grid else 0
    run: list[str] = []
    for r in range(min(_covered(table, cell)[0]) - 1, -1, -1):
        label = labels.get(r)
        if label is None:
            across = {x for x in table.grid[r] if x is not None}
            if len(across) == 1 and (x := next(iter(across)))[0] == r and table.text[x].strip() and width > 1:
                label = x
        if label is None:
            # Note: a blank spacer row between two section rows doesn't end their run.
            if run and any(x is not None and table.text[x].strip() for x in table.grid[r]): break
            continue
        run.insert(0, table.text[label])
    return run


def label_rows(table: Table) -> dict[int, Cell]:
    """Each row whose only text is one cell in its first column, among two or more cells starting
    in it: a section header written as its label followed by empty cells."""
    return table.labels


def _labels(text: dict[Cell, str]) -> dict[int, Cell]:
    # Note: a label further right is a heading flattened beside empty cells ("| | Univariable | |"),
    # which covers only its own column; one after a row group's label is a gap in a data row.
    starts: dict[int, list[Cell]] = {}
    for c in text: starts.setdefault(c[0], []).append(c)
    out = {}
    for r, cs in starts.items():
        full = [c for c in cs if text[c].strip()]
        if len(cs) > 1 and len(full) == 1 and full[0][1] == 0: out[r] = full[0]
    return out


def spanning_rows(table: Table, cell: Cell) -> bool:
    """Whether `cell` covers more than one row."""
    return len(_covered(table, cell)[0]) > 1


def _covered(table: Table, cell: Cell) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """The rows and the columns `cell` covers."""
    return table.covers[cell]


def _grid(specs: list[list[tuple[str, int, int, bool]]]) -> Table | None:
    """Places cells on a grid, carrying rowspans down, then links each cell to its neighbours."""
    text: dict[Cell, str] = {}
    headings: set[Cell] = set()
    extent: dict[Cell, tuple[int, int]] = {}
    grid: list[list[Cell | None]] = []
    carried: list[tuple[Cell, int] | None] = []   # per column: a rowspan still running down

    def carry(col: int) -> Cell:
        cell, left = carried[col]
        carried[col] = (cell, left - 1) if left > 1 else None
        return cell

    for r, row in enumerate(specs):
        slots: list[Cell | None] = []
        col = i = 0
        while i < len(row) or col < len(carried):
            if col < len(carried) and carried[col] is not None:
                slots.append(carry(col))
                col += 1
                continue
            if i >= len(row):
                slots.append(None)
                col += 1
                continue
            t, rowspan, colspan, is_heading = row[i]
            i += 1
            cell = (r, col)
            text[cell] = t
            if is_heading: headings.add(cell)
            extent[cell] = (rowspan, colspan)
            carried.extend([None] * max(0, col + colspan - len(carried)))
            for c in range(col, col + colspan):
                slots.append(cell)
                carried[c] = (cell, rowspan - 1) if rowspan > 1 else None
            col += colspan
        grid.append(slots)
    while any(carried):
        grid.append([carry(c) if carried[c] is not None else None for c in range(len(carried))])

    used = [c for row in grid for c, x in enumerate(row) if x is not None]
    if not text or not used:
        return None
    width, height = max(used) + 1, len(grid)
    grid = [(row + [None] * width)[:width] for row in grid]

    def first(cell: Cell, cells: Iterator[tuple[int, int]]) -> Cell | None:
        for r, c in cells:
            if (x := grid[r][c]) is not None and x != cell:
                return x
        return None

    directions = ("up", "down", "left", "right")
    rel: dict[str, dict[Cell, set[Cell]]] = {d: {c: set() for c in text} for d in directions}
    for cell, (rowspan, colspan) in extent.items():
        r0, c0 = cell
        r1, c1 = r0 + rowspan - 1, c0 + colspan - 1
        for r in range(r0, r1 + 1):
            if x := first(cell, ((r, c) for c in range(c1 + 1, width))): rel["right"][cell].add(x)
            if x := first(cell, ((r, c) for c in range(c0 - 1, -1, -1))): rel["left"][cell].add(x)
        for c in range(c0, c1 + 1):
            if x := first(cell, ((r, c) for r in range(r1 + 1, height))): rel["down"][cell].add(x)
            if x := first(cell, ((r, c) for r in range(r0 - 1, -1, -1))): rel["up"][cell].add(x)
    rows_of: dict[Cell, set[int]] = {}
    cols_of: dict[Cell, set[int]] = {}
    for r, row in enumerate(grid):
        for c, x in enumerate(row):
            if x is None: continue
            rows_of.setdefault(x, set()).add(r)
            cols_of.setdefault(x, set()).add(c)
    covers = {x: (tuple(sorted(rows_of[x])), tuple(sorted(cols_of[x]))) for x in rows_of}
    return Table(text, frozenset(headings), *({c: frozenset(v) for c, v in rel[d].items()}
                                              for d in ("up", "down", "left", "right")),
                 tuple(tuple(row) for row in grid), covers, _labels(text))


def _span(value: str | int | None) -> int:
    """A span attribute as a positive int up to MAX_SPAN: 1 when missing or malformed."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 1
    return min(n, MAX_SPAN) if n > 0 else 1


def _fresh_soup(html: str):
    from bs4 import BeautifulSoup

    return BeautifulSoup(html, "html.parser")

