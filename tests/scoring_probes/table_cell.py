# ruff: noqa: E501
"""Cases for docs/scoring/table_cell.md. Most run on the fixtures below; `A[1,240 -> 1240]` is fixture A with that
text replaced."""
from cases import cell, table

EMPTY, END = {"empty": True}, {"end": True}

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
        cell("cell-section-then-data", "I", "a data row that repeats a value does not hide the section above it", "6", C.replace("<td colspan=2>Cohort 1</td>", "<td colspan=2>Cohort 1</td></tr><tr><td>Yes</td><td>Yes</td>"), section="Cohort 1", show=show("C", "<td colspan=2>Cohort 1</td>", "<td colspan=2>Cohort 1</td></tr><tr><td>Yes</td><td>Yes</td>")),
        cell("cell-section-repeated", "I", "a section label written in each cell of its row, not merged", "6", C.replace("<td colspan=2>Cohort 1</td>", "<td>Cohort 1</td><td>Cohort 1</td>"), section="Cohort 1", show=show("C", "<td colspan=2>Cohort 1</td>", "<td>Cohort 1</td><td>Cohort 1</td>")),
        cell("cell-row-group", "I", "a row-spanning cell to the left", "6", C, row_groups=["Male"], show=show("C")),
    ),
    table(
        "cell-blind",
        cell("cell-insertions", "B", "extra characters cost half", "abcdefghij", "<table><tr><td>abcdefghijkl</td></tr></table>", md=1),
        cell("cell-short", "B", "a short gold with an edit to spend", "ab", "<table><tr><td>abcd</td></tr></table>", md=1),
        cell("cell-dir-rtl", "B", "`dir=rtl` changes nothing: roles follow the html's order", "5", "<table dir='rtl'><tr><th>A</th><td>5</td></tr></table>", left_heading="A"),
        cell("cell-any-table", "B", "a gold with no relations: any cell of any table", "2024", A, show=show("A")),
        cell("cell-section-repeated-value", "B", "a test naming the repeated value reads its row as the section: `Yes` passes", "6", C.replace("<td colspan=2>Cohort 1</td>", "<td>Yes</td><td>Yes</td>"), section="Yes", show=show("C", "<td colspan=2>Cohort 1</td>", "<td>Yes</td><td>Yes</td>")),
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
        cell("cell-section-data-row", "P", "a row that repeats a value is data for a test naming another section", "6", C.replace("<td colspan=2>Cohort 1</td>", "<td>Yes</td><td>Yes</td>"), section="Cohort 1", show=show("C", "<td colspan=2>Cohort 1</td>", "<td>Yes</td><td>Yes</td>"), why=True),
        cell("cell-row-group-wrong", "P", "a wrong row group", "6", C, row_groups=["Female"], show=show("C"), why=True),
        cell("cell-no-table", "P", "pipes in a paragraph are not a table", "1,240", "<p>| 2024 | 1,240 |</p>", why=True),
        cell("cell-compound", "I", "hyphenated compound broken at a line end", "self-aware", "<table><tr><td>self- aware</td></tr></table>"),
    ),
]

def t(*rows: str) -> str:
    """A table of body rows, each a string of cells."""
    return "<table>" + "".join(f"<tr>{r}</tr>" for r in rows) + "</table>"


TQ = t("<th>Item</th><th>Q1</th><th>Q2</th>", "<td>Rent</td><td>100</td><td></td>", "<td>Fuel</td><td>70</td><td>80</td>")
FIXTURES["table-t"] = TQ
TE = [
    table(
        "cell-empty-end",
        cell("cell-empty-blank", "I", "an empty cell beside the anchor", "100", TQ, right=EMPTY, show="T"),
        cell("cell-empty-space", "I", "a blank cell: spaces", "100", TQ.replace("<td></td>", "<td> </td>"), right=EMPTY, show="T[`<td></td>` → `<td> </td>`]"),
        cell("cell-empty-nbsp", "I", "a blank cell: `&nbsp;`", "100", TQ.replace("<td></td>", "<td>&nbsp;</td>"), right=EMPTY, show="T[`<td></td>` → `<td>&nbsp;</td>`]"),
        cell("cell-empty-br", "I", "a blank cell: `<br>`", "100", TQ.replace("<td></td>", "<td><br></td>"), right=EMPTY, show="T[`<td></td>` → `<td><br></td>`]"),
        cell("cell-empty-dropped", "I", "a trailing cell left out of a short row", "100", TQ.replace("<td></td>", ""), right=EMPTY, show="T[`<td></td>` → ``]"),
        cell("cell-empty-copy", "P", "a copy of the value beside it (a text arg would read the stand-in)", "100", TQ.replace("<td></td>", "<td>100</td>"), right=EMPTY, show="T[`<td></td>` → `<td>100</td>`]", why=True),
        cell("cell-empty-invented", "P", "an invented value", "100", TQ.replace("<td></td>", "<td>200</td>"), right=EMPTY, show="T[`<td></td>` → `<td>200</td>`]", why=True),
        cell("cell-empty-shifted", "P", "cells shifted: the value moved to the last column", "100", t("<th>Item</th><th>Q1</th><th>Q2</th>", "<td>Rent</td><td></td><td>100</td>", "<td>Fuel</td><td>70</td><td>80</td>"), right=EMPTY, why=True),
        cell("cell-empty-image", "P", "an image with no alt text is not blank", "100", TQ.replace("<td></td>", "<td><img src='a.png'></td>"), right=EMPTY, show="T[`<td></td>` → `<td><img src='a.png'></td>`]", why=True),
        cell("cell-end-image", "P", "an image in a row below is not blank", "70", TQ.replace("</table>", "<tr><td></td><td><img alt=''></td><td></td></tr></table>"), down=END, show="T + a row holding `<img alt=''>`", why=True),
        cell("cell-empty-left", "I", "the mirror: an empty cell to the left", "100", t("<th>Item</th><th>Q1</th><th>Q2</th>", "<td>Rent</td><td></td><td>100</td>"), left=EMPTY),
        cell("cell-empty-left-copy", "P", "the mirror, filled with a copy", "100", t("<th>Item</th><th>Q1</th><th>Q2</th>", "<td>Rent</td><td>100</td><td>100</td>"), left=EMPTY, why=True),
        cell("cell-empty-colspan", "P", "a colspan swallows the empty slot", "100", t("<th>Item</th><th>Q1</th><th>Q2</th>", "<td>Rent</td><td colspan=2>100</td>"), right=EMPTY, why=True),
        cell("cell-empty-edge", "P", "no cell at the table's edge", "80", TQ, right=EMPTY, why=True),
        cell("cell-empty-header", "P", "a merged heading is not a heading beside empty cells", "Group", "<table><tr><th colspan=2>Group</th></tr><tr><td>5</td><td>6</td></tr></table>", right=EMPTY, why=True),
        cell("cell-empty-header-flat", "I", "a heading beside an empty cell", "Group", "<table><tr><th>Group</th><th></th></tr><tr><td>5</td><td>6</td></tr></table>", right=EMPTY),
        cell("cell-end-down", "I", "the last row: nothing below", "70", TQ, down=END, show="T"),
        cell("cell-end-empty-row", "I", "an empty row added below", "70", TQ.replace("</table>", "<tr><td></td><td></td><td></td></tr></table>"), down=END, show="T + an empty row"),
        cell("cell-end-invented-row", "P", "an invented row", "70", TQ.replace("</table>", "<tr><td>Tax</td><td>9</td><td>8</td></tr></table>"), down=END, show="T + a row `Tax 9 8`", why=True),
        cell("cell-end-invented-row-far", "P", "an invented row after empty ones", "70", TQ.replace("</table>", "<tr><td></td><td></td><td></td></tr><tr><td></td><td>9</td><td></td></tr></table>"), down=END, show="T + an empty row + a row `9`", why=True),
        cell("cell-end-right", "I", "the last column: nothing to the right", "80", TQ, right=END, show="T"),
        cell("cell-end-invented-column", "P", "an invented column", "80", TQ.replace("<td>80</td>", "<td>80</td><td>x</td>"), right=END, show="T + a column holding `x`", why=True),
        cell("cell-end-empty-column", "I", "an empty column added", "80", TQ.replace("<td>80</td>", "<td>80</td><td></td>"), right=END, show="T + an empty column"),
        cell("cell-empty-twice", "P", "the table written twice, a value in one copy: every matching cell must be empty beside it", "100", TQ + TQ.replace("<td></td>", "<td>200</td>"), right=EMPTY, show="T + T[`<td></td>` → `<td>200</td>`]", why=True),
        cell("cell-empty-twice-blank", "I", "the table written twice, empty in both", "100", TQ + TQ, right=EMPTY, show="T + T"),
        cell("cell-empty-second-line", "P", "a second line in the anchor's cell", "100", TQ.replace("<td>100</td>", "<td>100<br>200</td>"), right=EMPTY, show="T[`<td>100</td>` → `<td>100<br>200</td>`]", why=True),
        cell("cell-end-next-table", "P", "a headerless table of the same width right after the table goes on from it", "70", TQ + "<table><tr><td>Tax</td><td>9</td><td>8</td></tr></table>", down=END, show="T + a table `Tax 9 8`", why=True),
        cell("cell-end-repeated-header", "P", "a table right after it that prints the header again goes on from it", "70", TQ + "<table><tr><th>Item</th><th>Q1</th><th>Q2</th></tr><tr><td>Tax</td><td>9</td><td>8</td></tr></table>", down=END, show="T + a table with T's header and a row `Tax 9 8`", why=True),
        cell("cell-end-other-header", "I", "a table with a header of its own is another table", "70", TQ + "<table><tr><th>Cost</th><th>Q3</th><th>Q4</th></tr><tr><td>Tax</td><td>9</td><td>8</td></tr></table>", down=END, show="T + a table with another header"),
        cell("cell-end-text-between", "I", "text between the tables: another table", "70", TQ + "<p>Note.</p><table><tr><td>Tax</td><td>9</td><td>8</td></tr></table>", down=END, show="T + a paragraph + a table `Tax 9 8`"),
        cell("cell-end-up", "P", "an invented header row above", "Item", t("<td>Report</td><td></td><td></td>", "<th>Item</th><th>Q1</th><th>Q2</th>"), up=END, why=True),
        cell("cell-end-anchor", "P", "the anchor is not at the end: a row below holds text", "Rent", TQ, down=END, why=True),
    ),
]

TABLES += TE
