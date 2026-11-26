# `table_cell`

**Asks:** some table in the output has a cell that reads like the gold cell, and that cell has the stated
neighbours (`up`, `down`, `left`, `right`), heading cells (`top_heading`, `left_heading`, `right_heading`), column headings
(`headings`), section and row groups. 5,386 tests; family tables; reads `html`.

The test reads tables from the markup (`<table>`, `rowspan`, `colspan`, `<th>`), not from how the page looks:
aligned text or pipes in a paragraph are not a table. It compares whole cells after fold, with a ratio that
allows `max_diffs` edits, and also with spaces removed. A cell may match by one of its lines (lines are made by
`<br>`). A cell that does not match is tried once more, exactly, as the whole cell or one of its lines, with each hyphen a line broke after (in
the gold or the cell) read kept or dropped, so a hyphenated compound broken at a line end matches, as in `present`
(case cell-compound). The test passes when one matching cell satisfies every stated role.

- `up`, `down`, `left`, `right`: the neighbouring cell. An empty neighbour stands for the value written over it
  (above, for `left` and `right`; to the left, for `up` and `down`). Instead of a text, one of these four may
  be `{"empty": true}` or `{"end": true}`, which catch invented table content (see "Empty cells and the end of a
  table").
- `top_heading`, `left_heading`, `right_heading`: a heading cell (`<th>` or in `<thead>`) reached walking up, left or
  right; when the walk meets none, the cell at the end of the walk (the first cell of the row for `left_heading`,
  the last for `right_heading`). The walk stays in the columns of the cell for `top_heading` and in its rows for
  `left_heading` and `right_heading`, past a cell that spans rows (case cell-heading-own-row). A cell is never its
  own heading: the last cell of a row has no `right_heading` (case cell-edge-self), and a `<th>` with no other
  heading on its walk reads the cell at the edge (case cell-heading-self).
- `left`, `right`, `left_heading` and `right_heading` follow the order of the cells in the html, not their place on
  the page, and `dir="rtl"` is not read. A right-to-left row written in reading order has its first cell at the
  right edge, so its `left_heading` is the label at the right edge (cases cell-rtl-reading-order, cell-dir-rtl).
- `headings`: these texts, in order, among the cells above the cell's column (any cell, `<td>` too). A merged
  heading, a repeated one, or one written once beside empty cells all count.
- `section`: the nearest section row above (a row of one label; one written in every cell counts when the gold names it, a row repeating another value is data), a row-spanning cell to the left, or the first
  cell of the row.
- `row_groups`: these texts, in order, among the cells to the left in the cell's rows.

Every arg of a test shares one `max_diffs`. A cell never matches below a ratio of 0.5, whatever the edit budget, so
a budget over half the cell's length does not widen the match.

## Rules

The fixtures the cases use:

<!-- cases:table-a -->
```html
<table><thead><tr><th>Year</th><th>Total</th></tr></thead>
<tr><td>2024</td><td>1,240</td></tr><tr><td>2025</td><td>1,300</td></tr></table>
```
<!-- /cases -->

<!-- cases:table-b -->
```html
<table><tr><th colspan=2>Group</th></tr><tr><th>A</th><th>B</th></tr>
<tr><td>5</td><td>6</td></tr></table>
```
<!-- /cases -->

<!-- cases:table-c -->
```html
<table><tr><th>A</th><th>B</th></tr><tr><td colspan=2>Cohort 1</td></tr>
<tr><td rowspan=2>Male</td><td>5</td></tr><tr><td>6</td></tr></table>
```
<!-- /cases -->

`A[x → y]` is table A with `x` replaced by `y`.

What the test ignores:

<!-- cases:cell-ignored -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| I | the cell as printed | `1,240` | A | pass | `cell-match` |
| I | letter case | `TOTAL` | A | pass | `cell-case` |
| I | spacing | `1: 1` | `<table><tr><td>1:1</td></tr></table>` | pass | `cell-spacing` |
| I | bold tags | `1,240` | A[`1,240` → `<b>1,240</b>`] | pass | `cell-bold` |
| I | an image description beside the text | `1,240` | A[`1,240` → `1,240<img alt='icon'>`] | pass | `cell-alt-beside` |
| I | an image alone reads as its description | `chart` | A[`1,240` → `<img alt='chart'>`] | pass | `cell-alt-only` |
| I | one line of a cell (`<br>`) | `2024-01` | `<table><tr><td>2024-01<br>2024-02</td></tr></table>` | pass | `cell-line` |
| I | a later table holds it | `1,240` | a one-cell table, then A | pass | `cell-second-table` |
| I | a word broken at a line end | `developers` | `<table><tr><td>develop- ers</td></tr></table>` | pass | `cell-line-hyphen` |
| I | the cell above | `1,300`, up `1,240` | A | pass | `cell-up` |
| I | the cell to the left | `1,240`, left `2024` | A | pass | `cell-left` |
| I | the heading cell at the end of the row | `1,240`, right_heading `Total` | `<table><tr><td>1,240</td><th>Total</th></tr></table>` | pass | `cell-right-heading` |
| I | no heading cell: the last cell of the row | `1,240`, right_heading `3` | `<table><tr><td>1,240</td><td>3</td></tr></table>` | pass | `cell-right-heading-last` |
| I | a right-to-left row written in reading order: its first cell is at the right edge | `1,240`, left_heading `المجموع` | `<table><tr><th>المجموع</th><td>1,240</td><td>٣</td></tr></table>` | pass | `cell-rtl-reading-order` |
| I | the heading over the column | `1,240`, top_heading `Total` | A | pass | `cell-top-heading` |
| I | any heading cell above, not only the nearest | `5`, top_heading `Outer` | `<table><tr><th>Outer</th></tr><tr><th>Inner</th></tr><tr><td>5</td></tr></table>` | pass | `cell-top-heading-outer` |
| I | a merged heading over the column | `5`, headings `Group` > `A` | B | pass | `cell-headings-merged` |
| I | a heading written once beside an empty cell | `6`, headings `Group` > `B` | B[`<th colspan=2>Group</th>` → `<th>Group</th><th></th>`] | pass | `cell-headings-beside` |
| I | the section row above | `6`, section `Cohort 1` | C | pass | `cell-section` |
| I | a data row that repeats a value does not hide the section above it | `6`, section `Cohort 1` | C[`<td colspan=2>Cohort 1</td>` → `<td colspan=2>Cohort 1</td></tr><tr><td>Yes</td><td>Yes</td>`] | pass | `cell-section-then-data` |
| I | a section label written in each cell of its row, not merged | `6`, section `Cohort 1` | C[`<td colspan=2>Cohort 1</td>` → `<td>Cohort 1</td><td>Cohort 1</td>`] | pass | `cell-section-repeated` |
| I | a row-spanning cell to the left | `6`, row groups `Male` | C | pass | `cell-row-group` |
<!-- /cases -->

What it does not look at, so a wrong output passes:

<!-- cases:cell-blind -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| B | extra characters cost half | `abcdefghij` (md 1) | `<table><tr><td>abcdefghijkl</td></tr></table>` | pass | `cell-insertions` |
| B | a short gold with an edit to spend | `ab` (md 1) | `<table><tr><td>abcd</td></tr></table>` | pass | `cell-short` |
| B | `dir=rtl` changes nothing: roles follow the html's order | `5`, left_heading `A` | `<table dir='rtl'><tr><th>A</th><td>5</td></tr></table>` | pass | `cell-dir-rtl` |
| B | a gold with no relations: any cell of any table | `2024` | A | pass | `cell-any-table` |
| B | a test naming the repeated value reads its row as the section: `Yes` passes | `6`, section `Yes` | C[`<td colspan=2>Cohort 1</td>` → `<td>Yes</td><td>Yes</td>`] | pass | `cell-section-repeated-value` |
| B | `headings` read any cell above, `<td>` too | `1,240`, headings `Total` | `<table><tr><td>Year</td><td>Total</td></tr><tr><td>2024</td><td>1,240</td></tr></table>` | pass | `cell-headings-td` |
<!-- /cases -->

What it penalizes:

<!-- cases:cell-penalized -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| P | a changed character | `1,240` | A[`1,240` → `1,24`] | fail: `no cell matching '1,240' in any table` | `cell-changed` |
| P | a dropped thousands separator | `1,240` | A[`1,240` → `1240`] | fail | `cell-format` |
| P | extra text in the cell | `1,240` | `<table><tr><td>1,240 (3.2)</td></tr></table>` | fail | `cell-extra-text` |
| P | an extra decimal | `5` | `<table><tr><td>5.0</td></tr></table>` | fail | `cell-extra-decimal` |
| P | a footnote marker in the cell | `1,240` | A[`1,240` → `1,240<sup>a</sup>`] | fail | `cell-sup` |
| P | a bracketed footnote marker | `1,240` | A[`1,240` → `1,240 [1]`] | fail | `cell-bracket` |
| P | markdown stars printed in html | `1,240` | A[`1,240` → `**1,240**`] | fail | `cell-stars` |
| P | lines as `<p>`, not `<br>` | `2024-01` | `<table><tr><td><p>2024-01</p><p>2024-02</p></td></tr></table>` | fail | `cell-paragraphs` |
| P | a wrong right heading | `1,240`, right_heading `Total` | `<table><tr><td>1,240</td><th>Sum</th></tr></table>` | fail: `cells matching '1,240' found, but: right_heading 'sum' doesn't match 'total' (0.00)` | `cell-right-heading-wrong` |
| P | a right-to-left row copied in page order | `1,240`, left_heading `المجموع` | `<table><tr><td>٣</td><td>1,240</td><th>المجموع</th></tr></table>` | fail: `cells matching '1,240' found, but: left_heading '٣' doesn't match 'المجموع' (0.00)` | `cell-rtl-page-order` |
| I | a heading cell with no other heading on its walk reads the cell at the edge | `Male`, right_heading `5` | `<table><tr><th>Male</th><td>5</td></tr></table>` | pass | `cell-heading-self` |
| P | the last cell of a row is not its own right heading | `5`, right_heading `5` | `<table><tr><td>a</td><td>5</td></tr></table>` | fail: `cells matching '5' found, but: no right_heading cell` | `cell-edge-self` |
| I | a walk stays in the rows of its cell, past a cell that spans rows | `5`, right_heading `z` | `<table><tr><td>a</td><td rowspan=2>m</td><th>H</th></tr><tr><td>5</td><td>z</td></tr></table>` | pass | `cell-heading-own-row` |
| P | a heading in another row is not the cell's heading | `5`, right_heading `H` | `<table><tr><td>a</td><td rowspan=2>m</td><th>H</th></tr><tr><td>5</td><td>z</td></tr></table>` | fail: `cells matching '5' found, but: right_heading 'z' doesn't match 'h' (0.00)` | `cell-heading-other-row` |
| P | a wrong neighbour | `1,300`, up `9` | A | fail: `cells matching '1,300' found, but: up '1,240' doesn't match '9' (0.00)` | `cell-up-wrong` |
| P | a wrong heading | `1,240`, top_heading `Year` | A | fail: `cells matching '1,240' found, but: top_heading 'total' doesn't match 'year' (0.22)` | `cell-top-heading-wrong` |
| P | headings in the wrong order | `5`, headings `A` > `Group` | B | fail: `cells matching '5' found, but: not under the headings 'A > Group'` | `cell-headings-swapped` |
| P | a wrong section | `6`, section `Cohort 2` | C | fail: `cells matching '6' found, but: not in the section 'Cohort 2' (nearest above: 'Cohort 1')` | `cell-section-wrong` |
| P | a row that repeats a value is data for a test naming another section | `6`, section `Cohort 1` | C[`<td colspan=2>Cohort 1</td>` → `<td>Yes</td><td>Yes</td>`] | fail: `cells matching '6' found, but: not in the section 'Cohort 1' (nearest above: 'none')` | `cell-section-data-row` |
| P | a wrong row group | `6`, row groups `Female` | C | fail: `cells matching '6' found, but: not in the row groups 'Female'` | `cell-row-group-wrong` |
| P | pipes in a paragraph are not a table | `1,240` | `<p>\| 2024 \| 1,240 \|</p>` | fail: `no tables found` | `cell-no-table` |
| I | hyphenated compound broken at a line end | `self-aware` | `<table><tr><td>self- aware</td></tr></table>` | pass | `cell-compound` |
<!-- /cases -->

## Empty cells and the end of a table

A text arg cannot say that a cell is blank, nor that a table stops: an empty neighbour reads as the value over or
beside it, so a copy of that value passes. Two args say it, on `up`, `down`, `left` and `right` only
(refused elsewhere):

- `{"empty": true}`: every slot touching that side of the cell is blank, read raw with no stand-in. A cell is
  blank when its folded text is empty (spaces, `&nbsp;`, `<br>`, invisible characters, leaders such as `...`);
  a short row's missing trailing cell is blank too. An image-only cell is not, with an alt text or without (cases cell-empty-image, cell-end-image). A cell that spans rows is checked
  at each row (`left`, `right`) or column (`up`, `down`) it covers. The edge of the table is not a blank cell:
  the why is `no right cell`. A `colspan` that covers the slot fails.
- `{"end": true}`: no cell in any row below (`down`), column to the right (`right`), row above (`up`) or column
  to the left (`left`) of the cell has text. Empty rows and columns pass: they invent nothing. The why names the
  first row or column that holds text (`down: row 3 holds '9', '8'`). A table written right after the anchor's table
  (nothing but white space between) that goes on from it counts too: below, one with as many columns and no heading,
  or one that prints the same first row again (the header of a table split over pages; that row is left out); to the
  right, one with as many rows and no heading. For `up` and `left` it is the table written right before. A table with a
  heading of its own, another width, or text between is another table (cases cell-end-next-table,
  cell-end-repeated-header, cell-end-other-header, cell-end-text-between).

**Every cell that matches.** With `empty` or `end`, every cell that matches `cell` and holds the test's other relations,
headings, section and row groups, in every table, must have the shape, and must hold nothing but `cell`: a second line in
its cell (`100<br>200`) fails. A table written twice with a value in one copy, or the anchor text in a second cell with
a value beside it, fails (cases cell-empty-twice, cell-empty-second-line). The price: a gold uses an anchor that is
unique on the page, or adds a relation that tells the cell from its twin (`left`, `top_heading`); a faithful output that
repeats the anchor with something beside it in another cell fails.

They check structure the page prints, so a gold should use them only where the page shows it: a body cell
printed empty; the last row or column of a table with nothing printed below it. Not in a header or section row:
a heading beside empty cells is written either as a merged cell or as a label with empty cells, and `empty` tells
the two apart (cases cell-empty-header, cell-empty-header-flat). Roles combine with every other arg. A text arg
keeps the stand-in, so no existing test changes.

Fixture T, used by the cases below:

<!-- cases:table-t -->
```html
<table><tr><th>Item</th><th>Q1</th><th>Q2</th></tr><tr><td>Rent</td><td>100</td><td></td></tr><tr><td>Fuel</td><td>70</td><td>80</td></tr></table>
```
<!-- /cases -->

<!-- cases:cell-empty-end -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| I | an empty cell beside the anchor | `100`, right `empty` | T | pass | `cell-empty-blank` |
| I | a blank cell: spaces | `100`, right `empty` | T[`<td></td>` → `<td> </td>`] | pass | `cell-empty-space` |
| I | a blank cell: `&nbsp;` | `100`, right `empty` | T[`<td></td>` → `<td>&nbsp;</td>`] | pass | `cell-empty-nbsp` |
| I | a blank cell: `<br>` | `100`, right `empty` | T[`<td></td>` → `<td><br></td>`] | pass | `cell-empty-br` |
| I | a trailing cell left out of a short row | `100`, right `empty` | T[`<td></td>` → ``] | pass | `cell-empty-dropped` |
| P | a copy of the value beside it (a text arg would read the stand-in) | `100`, right `empty` | T[`<td></td>` → `<td>100</td>`] | fail: `cells matching '100' found, but: right '100' isn't empty; no right cell` | `cell-empty-copy` |
| P | an invented value | `100`, right `empty` | T[`<td></td>` → `<td>200</td>`] | fail: `cells matching '100' found, but: right '200' isn't empty` | `cell-empty-invented` |
| P | cells shifted: the value moved to the last column | `100`, right `empty` | `<table><tr><th>Item</th><th>Q1</th><th>Q2</th></tr><tr><td>Rent</td><td></td><td>100</td></tr><tr><td>Fuel</td><td>70</td><td>80</td></tr></table>` | fail: `cells matching '100' found, but: no right cell` | `cell-empty-shifted` |
| P | an image with no alt text is not blank | `100`, right `empty` | T[`<td></td>` → `<td><img src='a.png'></td>`] | fail: `cells matching '100' found, but: right 'an image' isn't empty` | `cell-empty-image` |
| P | an image in a row below is not blank | `70`, down `end` | T + a row holding `<img alt=''>` | fail: `cells matching '70' found, but: down: row 4 holds 'an image'` | `cell-end-image` |
| I | the mirror: an empty cell to the left | `100`, left `empty` | `<table><tr><th>Item</th><th>Q1</th><th>Q2</th></tr><tr><td>Rent</td><td></td><td>100</td></tr></table>` | pass | `cell-empty-left` |
| P | the mirror, filled with a copy | `100`, left `empty` | `<table><tr><th>Item</th><th>Q1</th><th>Q2</th></tr><tr><td>Rent</td><td>100</td><td>100</td></tr></table>` | fail: `cells matching '100' found, but: left 'rent' isn't empty; left '100' isn't empty` | `cell-empty-left-copy` |
| P | a colspan swallows the empty slot | `100`, right `empty` | `<table><tr><th>Item</th><th>Q1</th><th>Q2</th></tr><tr><td>Rent</td><td colspan=2>100</td></tr></table>` | fail: `cells matching '100' found, but: no right cell` | `cell-empty-colspan` |
| P | no cell at the table's edge | `80`, right `empty` | `<table><tr><th>Item</th><th>Q1</th><th>Q2</th></tr><tr><td>Rent</td><td>100</td><td></td></tr><tr><td>Fuel</td><td>70</td><td>80</td></tr></table>` | fail: `cells matching '80' found, but: no right cell` | `cell-empty-edge` |
| P | a merged heading is not a heading beside empty cells | `Group`, right `empty` | `<table><tr><th colspan=2>Group</th></tr><tr><td>5</td><td>6</td></tr></table>` | fail: `cells matching 'Group' found, but: no right cell` | `cell-empty-header` |
| I | a heading beside an empty cell | `Group`, right `empty` | `<table><tr><th>Group</th><th></th></tr><tr><td>5</td><td>6</td></tr></table>` | pass | `cell-empty-header-flat` |
| I | the last row: nothing below | `70`, down `end` | T | pass | `cell-end-down` |
| I | an empty row added below | `70`, down `end` | T + an empty row | pass | `cell-end-empty-row` |
| P | an invented row | `70`, down `end` | T + a row `Tax 9 8` | fail: `cells matching '70' found, but: down: row 4 holds 'tax', '9', '8'` | `cell-end-invented-row` |
| P | an invented row after empty ones | `70`, down `end` | T + an empty row + a row `9` | fail: `cells matching '70' found, but: down: row 5 holds '9'` | `cell-end-invented-row-far` |
| I | the last column: nothing to the right | `80`, right `end` | T | pass | `cell-end-right` |
| P | an invented column | `80`, right `end` | T + a column holding `x` | fail: `cells matching '80' found, but: right: column 4 holds 'x'` | `cell-end-invented-column` |
| I | an empty column added | `80`, right `end` | T + an empty column | pass | `cell-end-empty-column` |
| P | the table written twice, a value in one copy: every matching cell must be empty beside it | `100`, right `empty` | T + T[`<td></td>` → `<td>200</td>`] | fail: `cells matching '100' found, but: right '200' isn't empty` | `cell-empty-twice` |
| I | the table written twice, empty in both | `100`, right `empty` | T + T | pass | `cell-empty-twice-blank` |
| P | a second line in the anchor's cell | `100`, right `empty` | T[`<td>100</td>` → `<td>100<br>200</td>`] | fail: `cells matching '100' found, but: the cell holds more than '100': '100 200'` | `cell-empty-second-line` |
| P | a headerless table of the same width right after the table goes on from it | `70`, down `end` | T + a table `Tax 9 8` | fail: `cells matching '70' found, but: down: a table continuing this one holds 'tax', '9', '8'` | `cell-end-next-table` |
| P | a table right after it that prints the header again goes on from it | `70`, down `end` | T + a table with T's header and a row `Tax 9 8` | fail: `cells matching '70' found, but: down: a table continuing this one holds 'tax', '9', '8'` | `cell-end-repeated-header` |
| I | a table with a header of its own is another table | `70`, down `end` | T + a table with another header | pass | `cell-end-other-header` |
| I | text between the tables: another table | `70`, down `end` | T + a paragraph + a table `Tax 9 8` | pass | `cell-end-text-between` |
| P | an invented header row above | `Item`, up `end` | `<table><tr><td>Report</td><td></td><td></td></tr><tr><th>Item</th><th>Q1</th><th>Q2</th></tr></table>` | fail: `cells matching 'Item' found, but: up: row 1 holds 'report'` | `cell-end-up` |
| P | the anchor is not at the end: a row below holds text | `Rent`, down `end` | `<table><tr><th>Item</th><th>Q1</th><th>Q2</th></tr><tr><td>Rent</td><td>100</td><td></td></tr><tr><td>Fuel</td><td>70</td><td>80</td></tr></table>` | fail: `cells matching 'Rent' found, but: down: row 3 holds 'fuel', '70', '80'` | `cell-end-anchor` |
<!-- /cases -->

## Blind spots

- **A named section may be a repeated value.** A test that names `Yes` as its section passes on a `Yes | Yes` row,
  because a row that writes the named label in every cell is read as that section row (case
  cell-section-repeated-value). The match is the section's own, so a repeated value within the test's `max_diffs`
  of the section passes too (`Cohort 1 | Cohort 1` for `Cohort 2` with one edit, as a merged `Cohort 1` does). The
  cells must fold to one string: `Cohort 1 | Cohort 3` is data. A repeated row that does not match the named
  section is data (case cell-section-data-row).
- **Whole cells, but a loose ratio.** With an edit to spend, insertions cost half an edit each:
  `abcdefghij` with one edit matches `abcdefghijkl` (case cell-insertions), and `ab` matches `abcd` (case
  cell-short).
- **A test with no relations is a cell-shaped `present`.** Any cell of any table will do (case cell-any-table).
- **`headings` read any cell above**, not only heading cells (case cell-headings-td).
- **Footnote markers cost here** and not in `present` (cases cell-sup, text-sup-marker).
- **`empty` and `end` read the markup.** A note printed under a table but moved into its last row fails `down: end`
  without any invention, so the gold must not use `end` on a table with something printed below. A table the output
  splits in two, a second table right after the first, goes on from it only as described above: a paragraph written
  after the table, a caption, or a column table with a header beside it is not read. In a right-to-left
  table `right` is the html's last cell, the visual left. `...` and other leaders fold to blank, so a cell holding
  only dots reads as empty.
- **A cell is not its own edge heading**: the last cell of a row fails a `right_heading` test for itself (case
  cell-edge-self).
- **A right-to-left table copied in page order fails**: the roles are written in the html's order, so a row copied
  left to right puts its label at the other end (case cell-rtl-page-order).

The why reads `no tables found`, `no cell matching '..' in any table`, or `cells matching '..' found, but: ...`
followed by each role that failed.
