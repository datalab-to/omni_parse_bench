# `repeat`

**Asks:** this line appears exactly N times on the page, no fewer and no more. 35 tests; family text; reads
`html`. It is the test for loops, duplicated headers and dropped repeats.

The test folds the gold and the page text, drops the gold's spaces and allows any spacing between its characters.
It counts matches that are whole words: no letter or digit may be glued to either end. It allows no edits
(`max_diffs` must be 0) and reads the text **without** image descriptions. When the count is not N, it counts
again with each hyphen a line broke after (on the page or in the gold) read kept or dropped, each copy once, and N
copies there pass too, so a hyphenated compound broken at a line end counts (case rep-compound; detail in
[internals.md](internals.md#the-hyphen-rule)).

## Rules

<!-- cases:repeat-rules -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| I | two copies, two expected | `Total` ×2 | `<p>Total</p><p>Total</p>` | pass | `rep-pass` |
| I | letter case | `Total` ×1 | `TOTAL` | pass | `rep-case` |
| I | spacing inside the line | `Total Due` ×1 | `To tal Due` | pass | `rep-spacing` |
| I | a copy in a table cell | `Total` ×1 | `<table><tr><td>Total</td></tr></table>` | pass | `rep-cell` |
| I | an image description is not a copy | `Total` ×1 | `<p>Total</p><img alt='Total'>` | pass | `rep-alt-ignored` |
| I | a word broken at a line end | `developers` ×1 | `develop- ers` | pass | `rep-line-hyphen` |
| B | two blocks read as one line | `Total Due` ×1 | `<p>Total</p><p>Due</p>` | pass | `rep-blocks-glue` |
| B | an underscore, hyphen or full stop is an edge | `Total` ×1 | `Total_x` | pass | `rep-underscore` |
| B | an added sign | `4.8` ×1 | `-4.8` | pass | `rep-sign` |
| P | a missing copy | `Total` ×2 | `Total` | fail: `'Total' appears 1x, not 2x` | `rep-missing` |
| P | an extra copy | `Total` ×2 | `<p>Total</p><p>Total</p><p>Total</p>` | fail: `'Total' appears 3x, not 2x` | `rep-extra` |
| P | only inside a longer word | `Total` ×1 | `Totals` | fail | `rep-longer-word` |
| P | a digit glued on | `Total` ×1 | `Total1` | fail | `rep-digit` |
| P | a changed character | `Total` ×1 | `Tota1` | fail | `rep-typo` |
| P | only in an image description | `Total` ×1 | `<img alt='Total'>` | fail | `rep-alt-only` |
| P | copies that overlap | `aa` ×1 | `aaaa` | fail | `rep-overlap` |
| I | hyphenated compound broken at a line end | `self-aware` ×1 | `self- aware` | pass | `rep-compound` |
<!-- /cases -->

## Blind spots

- **Any copy counts**, in a heading, a cell or a running header. The test cannot tell a printed repeat from a loop.
- **Blocks join.** A heading followed by a paragraph that starts with the next word is a copy of the two-word line
  (case rep-blocks-glue).
- **An underscore, hyphen or full stop is an edge**, so `Total_x` holds a `Total` (case rep-underscore), and a
  sign before a number is not seen (case rep-sign).
- **Image descriptions never count**, in either direction (cases rep-alt-ignored, rep-alt-only).

The why reads `'gold' appears Nx, not Mx`.
