# `order`

**Asks:** somewhere in the page's text, `before` starts earlier than `after`. 1,189 tests; family text; reads
`html`.

Both strings are folded and searched in the folded page text, allowing up to `max_diffs` edits (both share one
budget). If either is not written exactly in the folded text, both are searched again in the squeezed text. The
test passes when any match of `before` starts before any match of `after`. A larger budget keeps every match a
smaller one found, so it never fails a page that passes with fewer edits. When the pair is not found in order,
both are tried once more, exactly, with each hyphen a line broke after (on the page or in a string) read kept or
dropped, as `present` does: a hyphenated compound broken at a line end passes (case ord-compound). The page
text follows the html's source order: a table reads row by row, and a two-column page is only as ordered as the
system wrote it.

## Rules

<!-- cases:order-rules -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| I | in order, in two blocks | `Alpha` before `Beta` | `<p>Alpha</p><p>Beta</p>` | pass | `ord-pass` |
| I | case and spacing | `Alpha` before `Beta` | `<p>ALPHA</p><p>b e t a</p>` | pass | `ord-fold` |
| I | leaders | `Alpha` before `Beta` | `<p>Alpha ......</p><p>Beta</p>` | pass | `ord-leaders` |
| I | a word broken at a line end | `developers` before `Beta` | `<p>develop- ers</p><p>Beta</p>` | pass | `ord-line-hyphen` |
| B | any pair in order decides | `Alpha` before `Beta` | `<p>Beta</p><p>Alpha</p><p>Beta</p>` | pass | `ord-any-pair` |
| B | no word edge | `Alpha` before `Beta` | `AlphaBeta` | pass | `ord-glued` |
| B | the two may overlap | `Alpha Beta` before `Beta` | `Alpha Beta` | pass | `ord-overlap` |
| B | an image description has a place in the order | `Alpha` before `Beta` | `<img alt='Alpha'><p>Beta</p>` | pass | `ord-alt` |
| P | reversed | `Alpha` before `Beta` | `<p>Beta</p><p>Alpha</p>` | fail: `'Alpha' does not appear before 'Beta'` | `ord-reversed` |
| P | one string missing | `Alpha` before `Beta` | `<p>Beta</p>` | fail: `'before' text 'Alpha' not found` | `ord-missing` |
| P | both start at the same place | `Alpha` before `Alpha Beta` | `Alpha Beta` | fail | `ord-same-start` |
| P | table cells in the other order | `Alpha` before `Beta` | `<table><tr><td>Beta</td><td>Alpha</td></tr></table>` | fail | `ord-table` |
| P | two letters swapped is 2 edits here | `Alpha` before `Beta` (md 1) | `<p>Alhpa</p><p>Beta</p>` | fail | `ord-transposition` |
| I | the same with 2 edits | `Alpha` before `Beta` (md 2) | `<p>Alhpa</p><p>Beta</p>` | pass | `ord-transposition-2` |
| B | a larger budget passes what a smaller one did (md 0 passes too) | `aa` before `a ba` (md 1) | `<p>b b a ab ab</p>` | pass | `ord-more-edits` |
| P | with an edit to spend, a changed digit | `Total: 41` before `ZZZ` (md 1) | `<p>Total: 40</p><p>ZZZ</p>` | fail | `ord-digit-exact` |
| P | with an edit to spend, a decimal point inserted | `Total 12` before `ZZZ` (md 2) | `<p>Total 1.2</p><p>ZZZ</p>` | fail | `ord-digit-point` |
| P | a lost minus sign | `Net -5 total` before `ZZZ` (md 2) | `<p>Net 5 total</p><p>ZZZ</p>` | fail | `ord-sign-lost` |
| P | a minus sign added | `Net 5 total` before `ZZZ` (md 2) | `<p>Net -5 total</p><p>ZZZ</p>` | fail | `ord-sign-added` |
| I | a letter edit beside a number | `Total: 41` before `ZZZ` (md 1) | `<p>Totel: 41</p><p>ZZZ</p>` | pass | `ord-digit-letter` |
| P | a digit continues a number | `Total: 40` before `ZZZ` | `<p>Total: 400</p><p>ZZZ</p>` | fail: `'before' text 'Total: 40' found only inside a longer number` | `ord-digit-edge` |
| P | a footnote marker inside the phrase | `Smith and Jones` before `ZZZ` | `<p>Smith[1] and Jones</p><p>ZZZ</p>` | fail | `ord-footnote` |
| I | hyphenated compound broken at a line end | `self-aware` before `ZZZ` | `<p>self- aware</p><p>ZZZ</p>` | pass | `ord-compound` |
| I | a line-end hyphen in capitals reads as in lower case | `RE- M` before `ZZZ` | `<p>re- m</p><p>ZZZ</p>` | pass | `ord-case-hyphen` |
<!-- /cases -->

## How it differs from `present`

- **Edits are true edit distance.** Two swapped letters cost 2 here and 1 in `present` (cases ord-transposition,
  text-transposition).
- **No footnote retry.** `present` retries with a footnote marker dropped where it falls inside the phrase;
  here the marker stays, so `Smith and Jones` is not found in `Smith[1] and Jones` (case ord-footnote).
- **Numbers are exact.** As in `present`, a string with a digit keeps each of its numbers whole at any
  `max_diffs`, and a minus sign directly before a number must be written and cannot be added (the sign rule is in
  [present-text.md](present-text.md#numbers-are-exact)); the edit budget is spent on the other characters (cases
  ord-digit-exact, ord-digit-point, ord-sign-lost, ord-sign-added, ord-digit-letter). A string without a digit is
  not guarded.
- Like `present`, it has a digit edge on each string and no word edge (cases ord-digit-edge, ord-glued).

## Blind spots

- **Any pair decides.** A repeated header or a copy in a footer can supply the order (case ord-any-pair).
- **Overlap is allowed**: a `before` that contains `after` passes on itself (case ord-overlap).
- **Image descriptions have a place in the text**, so a description can supply or reorder a string (case
  ord-alt).

The why reads `'before' text '..' not found` (or `'after'`), `'before' text '..' found only inside a longer
number` when the digit edge rejected every exact match, or `'..' does not appear before '..'`.
