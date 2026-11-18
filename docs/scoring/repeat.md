# `repeat`

**Asks:** this line, or this number, appears exactly N times on the page, no fewer and no more. 35 tests with
text and none with a number yet; family text; reads `html`. It is the test for loops, duplicated headers,
dropped repeats and a figure merged or invented in a table.

The test folds the gold and the page text, drops the gold's spaces and allows any spacing between its characters.
It counts matches that are whole words: no letter or digit may be glued to either end. It allows no edits
(`max_diffs` must be 0) and reads the text **without** image descriptions. When the count is not N, it counts
again with each hyphen a line broke after (on the page or in the gold) read kept or dropped, each copy once, and N
copies there pass too, so a hyphenated compound broken at a line end counts (case rep-compound; detail in
[internals.md](internals.md#the-hyphen-rule)).

A repeat test with a **number** arg (`{"number": "1,240"}`) counts the copies the way `present` finds one
([present-number.md](present-number.md)): digit for digit, separators as the gold writes them, sign and percent
as in that page, and it takes the same gold (a number that reads as two numbers, `12,5`, is refused when the
test loads). It differs from `present` in what it reads: **line by line** (a block, a table cell and a `<br>`
each end a line, so a space-grouped number is never counted across two cells), **without image descriptions**
(`present` reads them), and without the digits a footnote mark (`<sup>2</sup>`, `[2]`) or the numbers a browser
draws for an ordered list would add (but a footnote mark between the groups of a number written with spaces is
kept, so `12 500` is no copy in `12<sup>2</sup> 500`, which `present` reads as two numbers too: case
repn-footnote-between-groups). A gold of plain or space-grouped digits is no copy where it continues a
group of digits across a space (`500` in `12 500`, `12` in `12 500`); `present` finds a number there. Each
match counts once and matches never overlap; the hyphen reading below does not apply to it. `1,240` and `1240`
are two numbers, so a page that writes a figure both ways holds one copy of each. A copy that `repeat` counts
is always one `present` finds.

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

### Rules for a number

<!-- cases:repeat-number-rules -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| I | two copies, two expected | `1,240` ×2 | `<p>1,240</p><p>1,240</p>` | pass | `repn-pass` |
| I | a copy in a table cell | `1,240` ×1 | `<table><tr><td>1,240</td></tr></table>` | pass | `repn-cell` |
| I | a no-break space for the gold's space | `12 500` ×1 | `12&nbsp;500` | pass | `repn-space` |
| I | a currency sign | `1,240.00` ×1 | `$1,240.00` | pass | `repn-currency` |
| I | parentheses around a copy | `4.8` ×1 | `(4.8)` | pass | `repn-parens` |
| I | a full stop after a copy | `5` ×1 | `5.` | pass | `repn-stop` |
| I | an en dash for the minus sign | `-4.8%` ×1 | `–4.8%` | pass | `repn-minus` |
| I | an image description is not a copy | `1,240` ×1 | `<p>1,240</p><img alt='1,240'>` | pass | `repn-alt-ignored` |
| B | a percent sign the gold lacks | `4.8` ×1 | `4.8%` | pass | `repn-percent-extra` |
| B | any place on the page, a page number too | `42` ×1 | `Page 42 of 100` | pass | `repn-context` |
| I | two copies in two cells | `1,240` ×2 | `<table><tr><td>1,240</td><td>1,240</td></tr></table>` | pass | `repn-lines` |
| I | two copies on one line | `1,240` ×2 | `<p>1,240 1,240</p>` | pass | `repn-same-line` |
| I | a footnote mark is not a copy | `2` ×1 | `<p>Revenue<sup>2</sup> was 2</p>` | pass | `repn-footnote-mark` |
| P | a footnote mark between the groups of a number written with spaces is not dropped: the two groups are two numbers, as `present` reads them | `12 500` ×1 | `<p>12<sup>2</sup> 500</p>` | fail | `repn-footnote-between-groups` |
| I | a list's numbers are not copies | `2` ×1 | `<ol><li>a</li><li>b 2</li></ol>` | pass | `repn-list-numbers` |
| P | a space-grouped number in two cells | `12 500` ×1 | `<table><tr><td>12</td><td>500</td></tr></table>` | fail | `repn-cells-glue` |
| P | three digits that continue a group | `500` ×1 | `Total 12 500` | fail | `repn-group-continued` |
| P | digits followed by another group | `12` ×1 | `12 500` | fail | `repn-group-before` |
| P | a missing copy | `1,240` ×2 | `1,240` | fail: `'1,240' appears 1x, not 2x` | `repn-missing` |
| P | an extra copy | `1,240` ×2 | `<p>1,240</p><p>1,240</p><p>1,240</p>` | fail: `'1,240' appears 3x, not 2x` | `repn-extra` |
| P | another separator | `1,240` ×1 | `1240` | fail | `repn-separator` |
| P | a thousands comma dropped | `1,000` ×1 | `1000` | fail | `repn-comma-dropped` |
| P | a thousands comma added | `1000` ×1 | `1,000` | fail | `repn-comma-added` |
| P | a point for the comma | `1,000` ×1 | `1.000` | fail | `repn-point-for-comma` |
| P | a trailing zero added | `8.455` ×1 | `8.4550` | fail | `repn-zero-added` |
| P | a trailing zero dropped | `0.50` ×1 | `0.5` | fail | `repn-zero-dropped` |
| P | a digit glued on | `1,240` ×1 | `11,240` | fail | `repn-digit-glued` |
| P | a changed digit | `1,240` ×1 | `1,241` | fail | `repn-digit-changed` |
| P | cut out of a longer decimal | `12.5` ×1 | `12.5.7` | fail | `repn-longer-decimal` |
| P | the sign lost | `-4.8%` ×1 | `4.8%` | fail | `repn-sign-lost` |
| P | a sign the gold lacks | `4.8` ×1 | `-4.8` | fail | `repn-sign-added` |
| P | the percent sign lost | `4.8%` ×1 | `4.8` | fail | `repn-percent-lost` |
| P | only in an image description | `1,240` ×1 | `<img alt='1,240'>` | fail | `repn-alt-only` |
<!-- /cases -->

## Blind spots

- **Any copy counts**, in a heading, a cell or a running header. The test cannot tell a printed repeat from a loop.
- **Blocks join.** A heading followed by a paragraph that starts with the next word is a copy of the two-word line
  (case rep-blocks-glue).
- **An underscore, hyphen or full stop is an edge**, so `Total_x` holds a `Total` (case rep-underscore), and a
  sign before a number is not seen (case rep-sign).
- **Image descriptions never count**, in either direction (cases rep-alt-ignored, rep-alt-only).
- **Digits that are not a number count**: a time (`12:30` holds a 12), a range (`10-12`), an ordinal (`2nd`), a
  unit, the digits of LaTeX source (`$10^{3}$` holds no 10, `$x_2$` holds a 2) and a version (`1.2.3` holds no
  `1.2`, but a 3). Choose a number the page does not repeat by chance.
- **A number counts anywhere on the page**, as `present` finds it: a page number or a year is a copy
  (case repn-context), and a percent sign the gold lacks does not stop one (case repn-percent-extra). Choose a
  number of three digits or more, or a decimal, that the page does not repeat by chance.

The why reads `'gold' appears Nx, not Mx`.
