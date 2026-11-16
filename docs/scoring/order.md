# `order`

**Asks:** somewhere in the page's text, `before` starts earlier than `after`. 1,189 tests; family text; reads
`html`.

Both strings are folded and searched in the folded page text, allowing up to `max_diffs` edits (both share one
budget). If either is not written exactly in the folded text, both are searched again in the squeezed text. The
test passes when any match of `before` starts before any match of `after`. A larger budget keeps every match a
smaller one found, so it never fails a page that passes with fewer edits. The page text follows the html's source
order: a table reads row by row, and a two-column page is only as ordered as the system wrote it.

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
| P | a digit continues a number | `Total: 40` before `ZZZ` | `<p>Total: 400</p><p>ZZZ</p>` | fail: `'before' text 'Total: 40' found only inside a longer number` | `ord-digit-edge` |
| P | a footnote marker inside the phrase | `Smith and Jones` before `ZZZ` | `<p>Smith[1] and Jones</p><p>ZZZ</p>` | fail | `ord-footnote` |
| P | hyphenated compound broken at a line end | `self-aware` before `ZZZ` | `<p>self- aware</p><p>ZZZ</p>` | fail | `ord-compound` |
| P | a capital before a line-end hyphen | `R- M` before `ZZZ` | `<p>r- m</p><p>ZZZ</p>` | fail | `ord-case-hyphen` |
<!-- /cases -->

## How it differs from `present`

- **Edits are true edit distance.** Two swapped letters cost 2 here and 1 in `present` (cases ord-transposition,
  text-transposition).
- **No footnote retry.** `present` retries with a footnote marker dropped where it falls inside the phrase;
  here the marker stays, so `Smith and Jones` is not found in `Smith[1] and Jones` (case ord-footnote).
- **No hyphen fallback.** A hyphenated compound broken at a line end fails here and passes `present` (case
  ord-compound). A plain word broken at a line end passes both (case ord-line-hyphen).
- **A capital before a line-end hyphen** keeps the hyphen, and case then matters: `R- M` is not found in `r- m`
  (case ord-case-hyphen).
- Like `present`, it has a digit edge on each string and no word edge (cases ord-digit-edge, ord-glued).

## Blind spots

- **Any pair decides.** A repeated header or a copy in a footer can supply the order (case ord-any-pair).
- **Overlap is allowed**: a `before` that contains `after` passes on itself (case ord-overlap).
- **Image descriptions have a place in the text**, so a description can supply or reorder a string (case
  ord-alt).

The why reads `'before' text '..' not found` (or `'after'`), `'before' text '..' found only inside a longer
number` when the digit edge rejected every exact match, or `'..' does not appear before '..'`.
