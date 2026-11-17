# ruff: noqa: E501
"""Cases for docs/scoring/table_cell.md. Most run on the fixtures below; `A[1,240 -> 1240]` is fixture A with that
text replaced."""
from cases import cell, table

FIXTURES = {
    "table-a": "<table><thead><tr><th>Year</th><th>Total</th></tr></thead>\n"
               "<tr><td>2024</td><td>1,240</td></tr><tr><td>2025</td><td>1,300</td></tr></table>",
    "table-b": "<table><tr><th colspan=2>Group</th></tr><tr><th>A</th><th>B</th></tr>\n"
               "<tr><td>5</td><td>6</td></tr></table>",
    "table-c": "<table><tr><th>A</th><th>B</th></tr><tr><td colspan=2>Cohort 1</td></tr>\n"
               "<tr><td rowspan=2>Male</td><td>5</td></tr><tr><td>6</td></tr></table>",
}
A, B, C = (FIXTURES[k].replace("\n", "") for k in ("table-a", "table-b", "table-c"))


def a(old: str, new: str) -> str:
    return A.replace(old, new)


def show(name: str, old: str = "", new: str = "") -> str:
    return f"{name}" + (f"[`{old}` → `{new}`]" if old else "")


TABLES = [
    table(
        "cell-ignored",
        cell("cell-match", "I", "the cell as printed", "1,240", A, show=show("A")),
        cell("cell-case", "I", "letter case", "TOTAL", A, show=show("A")),
        cell("cell-spacing", "I", "spacing", "1: 1", "<table><tr><td>1:1</td></tr></table>"),
        cell("cell-bold", "I", "bold tags", "1,240", a("1,240", "<b>1,240</b>"), show=show("A", "1,240", "<b>1,240</b>")),
        cell("cell-alt-beside", "I", "an image description beside the text", "1,240", a("1,240", "1,240<img alt='icon'>"), show=show("A", "1,240", "1,240<img alt='icon'>")),
        cell("cell-alt-only", "I", "an image alone reads as its description", "chart", a("1,240", "<img alt='chart'>"), show=show("A", "1,240", "<img alt='chart'>")),
        cell("cell-line", "I", "one line of a cell (`<br>`)", "2024-01", "<table><tr><td>2024-01<br>2024-02</td></tr></table>"),
        cell("cell-second-table", "I", "a later table holds it", "1,240", "<table><tr><td>x</td></tr></table>" + A, show="a one-cell table, then A"),
        cell("cell-line-hyphen", "I", "a word broken at a line end", "developers", "<table><tr><td>develop- ers</td></tr></table>"),
        cell("cell-up", "I", "the cell above", "1,300", A, up="1,240", show=show("A")),
        cell("cell-left", "I", "the cell to the left", "1,240", A, left="2024", show=show("A")),
        cell("cell-right-heading", "I", "the heading cell at the end of the row", "1,240", "<table><tr><td>1,240</td><th>Total</th></tr></table>", right_heading="Total"),
        cell("cell-right-heading-last", "I", "no heading cell: the last cell of the row", "1,240", "<table><tr><td>1,240</td><td>3</td></tr></table>", right_heading="3"),
        cell("cell-rtl-reading-order", "I", "a right-to-left row written in reading order: its first cell is at the right edge", "1,240", "<table><tr><th>المجموع</th><td>1,240</td><td>٣</td></tr></table>", left_heading="المجموع"),
        cell("cell-top-heading", "I", "the heading over the column", "1,240", A, top_heading="Total", show=show("A")),
        cell("cell-top-heading-outer", "I", "any heading cell above, not only the nearest", "5", "<table><tr><th>Outer</th></tr><tr><th>Inner</th></tr><tr><td>5</td></tr></table>", top_heading="Outer"),
        cell("cell-headings-merged", "I", "a merged heading over the column", "5", B, headings=["Group", "A"], show=show("B")),
        cell("cell-headings-beside", "I", "a heading written once beside an empty cell", "6", B.replace("<th colspan=2>Group</th>", "<th>Group</th><th></th>"), headings=["Group", "B"], show=show("B", "<th colspan=2>Group</th>", "<th>Group</th><th></th>")),
        cell("cell-section", "I", "the section row above", "6", C, section="Cohort 1", show=show("C")),
        cell("cell-row-group", "I", "a row-spanning cell to the left", "6", C, row_groups=["Male"], show=show("C")),
    ),
    table(
        "cell-blind",
        cell("cell-insertions", "B", "extra characters cost half", "abcdefghij", "<table><tr><td>abcdefghijkl</td></tr></table>", md=1),
        cell("cell-short", "B", "a short gold with an edit to spend", "ab", "<table><tr><td>abcd</td></tr></table>", md=1),
        cell("cell-dir-rtl", "B", "`dir=rtl` changes nothing: roles follow the html's order", "5", "<table dir='rtl'><tr><th>A</th><td>5</td></tr></table>", left_heading="A"),
        cell("cell-any-table", "B", "a gold with no relations: any cell of any table", "2024", A, show=show("A")),
        cell("cell-headings-td", "B", "`headings` read any cell above, `<td>` too", "1,240", "<table><tr><td>Year</td><td>Total</td></tr><tr><td>2024</td><td>1,240</td></tr></table>", headings=["Total"]),
    ),
    table(
        "cell-penalized",
        cell("cell-changed", "P", "a changed character", "1,240", a("1,240", "1,24"), show=show("A", "1,240", "1,24"), why=True),
        cell("cell-format", "P", "a dropped thousands separator", "1,240", a("1,240", "1240"), show=show("A", "1,240", "1240")),
        cell("cell-extra-text", "P", "extra text in the cell", "1,240", "<table><tr><td>1,240 (3.2)</td></tr></table>"),
        cell("cell-extra-decimal", "P", "an extra decimal", "5", "<table><tr><td>5.0</td></tr></table>"),
        cell("cell-sup", "P", "a footnote marker in the cell", "1,240", a("1,240", "1,240<sup>a</sup>"), show=show("A", "1,240", "1,240<sup>a</sup>")),
        cell("cell-bracket", "P", "a bracketed footnote marker", "1,240", a("1,240", "1,240 [1]"), show=show("A", "1,240", "1,240 [1]")),
        cell("cell-stars", "P", "markdown stars printed in html", "1,240", a("1,240", "**1,240**"), show=show("A", "1,240", "**1,240**")),
        cell("cell-paragraphs", "P", "lines as `<p>`, not `<br>`", "2024-01", "<table><tr><td><p>2024-01</p><p>2024-02</p></td></tr></table>"),
        cell("cell-right-heading-wrong", "P", "a wrong right heading", "1,240", "<table><tr><td>1,240</td><th>Sum</th></tr></table>", right_heading="Total", why=True),
        cell("cell-rtl-page-order", "P", "a right-to-left row copied in page order", "1,240", "<table><tr><td>٣</td><td>1,240</td><th>المجموع</th></tr></table>", left_heading="المجموع", why=True),
        cell("cell-heading-self", "I", "a heading cell with no other heading on its walk reads the cell at the edge", "Male", "<table><tr><th>Male</th><td>5</td></tr></table>", right_heading="5"),
        cell("cell-edge-self", "P", "the last cell of a row is not its own right heading", "5", "<table><tr><td>a</td><td>5</td></tr></table>", right_heading="5", why=True),
        cell("cell-heading-own-row", "I", "a walk stays in the rows of its cell, past a cell that spans rows", "5", "<table><tr><td>a</td><td rowspan=2>m</td><th>H</th></tr><tr><td>5</td><td>z</td></tr></table>", right_heading="z"),
        cell("cell-heading-other-row", "P", "a heading in another row is not the cell's heading", "5", "<table><tr><td>a</td><td rowspan=2>m</td><th>H</th></tr><tr><td>5</td><td>z</td></tr></table>", right_heading="H", why=True),
        cell("cell-up-wrong", "P", "a wrong neighbour", "1,300", A, up="9", show=show("A"), why=True),
        cell("cell-top-heading-wrong", "P", "a wrong heading", "1,240", A, top_heading="Year", show=show("A"), why=True),
        cell("cell-headings-swapped", "P", "headings in the wrong order", "5", B, headings=["A", "Group"], show=show("B"), why=True),
        cell("cell-section-wrong", "P", "a wrong section", "6", C, section="Cohort 2", show=show("C"), why=True),
        cell("cell-row-group-wrong", "P", "a wrong row group", "6", C, row_groups=["Female"], show=show("C"), why=True),
        cell("cell-no-table", "P", "pipes in a paragraph are not a table", "1,240", "<p>| 2024 | 1,240 |</p>", why=True),
        cell("cell-compound", "I", "hyphenated compound broken at a line end", "self-aware", "<table><tr><td>self- aware</td></tr></table>"),
    ),
]
