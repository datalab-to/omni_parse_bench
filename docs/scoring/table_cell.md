# `table_cell`

**Asks:** some table in the output has a cell that reads like the gold cell, and that cell has the stated
neighbours (`up`, `down`, `left`, `right`), heading cells (`top_heading`, `left_heading`), column headings
(`headings`), section and row groups. 5,386 tests; family tables; reads `html`.

The test reads tables from the markup (`<table>`, `rowspan`, `colspan`, `<th>`), not from how the page looks:
aligned text or pipes in a paragraph are not a table. It compares whole cells after fold, with a ratio that
allows `max_diffs` edits, and also with spaces removed. A cell may match by one of its lines (lines are made by
`<br>`). The test passes when one matching cell satisfies every stated role.

- `up`, `down`, `left`, `right`: the neighbouring cell. An empty neighbour stands for the value written over it
  (above, for `left` and `right`; to the left, for `up` and `down`).
- `top_heading`, `left_heading`: a heading cell (`<th>` or in `<thead>`) reached walking up or left.
- `headings`: these texts, in order, among the cells above the cell's column (any cell, `<td>` too). A merged
  heading, a repeated one, or one written once beside empty cells all count.
- `section`: the nearest section row above (a row of one label), a row-spanning cell to the left, or the first
  cell of the row.
- `row_groups`: these texts, in order, among the cells to the left in the cell's rows.

Every arg of a test shares one `max_diffs`.

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
| I | the heading over the column | `1,240`, top_heading `Total` | A | pass | `cell-top-heading` |
| I | any heading cell above, not only the nearest | `5`, top_heading `Outer` | `<table><tr><th>Outer</th></tr><tr><th>Inner</th></tr><tr><td>5</td></tr></table>` | pass | `cell-top-heading-outer` |
| I | a merged heading over the column | `5`, headings `Group` > `A` | B | pass | `cell-headings-merged` |
| I | a heading written once beside an empty cell | `6`, headings `Group` > `B` | B[`<th colspan=2>Group</th>` → `<th>Group</th><th></th>`] | pass | `cell-headings-beside` |
| I | the section row above | `6`, section `Cohort 1` | C | pass | `cell-section` |
| I | a row-spanning cell to the left | `6`, row groups `Male` | C | pass | `cell-row-group` |
<!-- /cases -->

What it does not look at, so a wrong output passes:

<!-- cases:cell-blind -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| B | extra characters cost half | `abcdefghij` (md 1) | `<table><tr><td>abcdefghijkl</td></tr></table>` | pass | `cell-insertions` |
| B | a short gold with an edit to spend | `ab` (md 1) | `<table><tr><td>abcd</td></tr></table>` | pass | `cell-short` |
| B | a gold with no relations: any cell of any table | `2024` | A | pass | `cell-any-table` |
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
| P | a wrong neighbour | `1,300`, up `9` | A | fail: `cells matching '1,300' found, but: up '1,240' doesn't match '9' (0.00)` | `cell-up-wrong` |
| P | a wrong heading | `1,240`, top_heading `Year` | A | fail: `cells matching '1,240' found, but: top_heading 'total' doesn't match 'year' (0.22)` | `cell-top-heading-wrong` |
| P | headings in the wrong order | `5`, headings `A` > `Group` | B | fail: `cells matching '5' found, but: not under the headings 'A > Group'` | `cell-headings-swapped` |
| P | a wrong section | `6`, section `Cohort 2` | C | fail: `cells matching '6' found, but: not in the section 'Cohort 2' (nearest above: 'Cohort 1')` | `cell-section-wrong` |
| P | a wrong row group | `6`, row groups `Female` | C | fail: `cells matching '6' found, but: not in the row groups 'Female'` | `cell-row-group-wrong` |
| P | pipes in a paragraph are not a table | `1,240` | `<p>\| 2024 \| 1,240 \|</p>` | fail: `no tables found` | `cell-no-table` |
| P | hyphenated compound broken at a line end | `self-aware` | `<table><tr><td>self- aware</td></tr></table>` | fail | `cell-compound` |
<!-- /cases -->

## Blind spots

- **Whole cells, but a loose ratio.** With an edit to spend, insertions cost half an edit each:
  `abcdefghij` with one edit matches `abcdefghijkl` (case cell-insertions), and `ab` matches `abcd` (case
  cell-short).
- **A test with no relations is a cell-shaped `present`.** Any cell of any table will do (case cell-any-table).
- **`headings` read any cell above**, not only heading cells (case cell-headings-td).
- **Footnote markers cost here** and not in `present` (cases cell-sup, text-sup-marker).
- **No hyphen fallback**: a hyphenated compound broken at a line end is not found (case cell-compound).

The why reads `no tables found`, `no cell matching '..' in any table`, or `cells matching '..' found, but: ...`
followed by each role that failed.
