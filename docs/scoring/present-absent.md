# `present` with `{"absent": true}`

**Asks:** the output does not hold a reading the page does not print. A `present` test with the setting
`{"absent": true}` (default false); family text; reads `html`. It is the test for a known wrong reading: text
hidden under a redaction box, the first line of the next page. The gold states the wrong reading exactly, so
the test needs no list of what the page does print. The published dataset holds no tests with this setting
yet.

```json
{"test_type": "present", "output_type": "html", "derivation": "rendered_source", "tags": ["redaction"],
 "args": {"content": {"text": "Johnathan Quincy Smithers", "max_diffs": 3}},
 "settings": {"absent": true}}
```

- `content`: the reading the page must not get. A text arg with `text` and `max_diffs`, no `place` and no
  `exact_case`. No other setting (`blank_after`, `printed` and `stops` do not combine with it).
- The text has at least **20 characters** after fold, so that it names a specific reading (a name with its
  middle name, a whole line). The floor does not show that the page does not print it: that is the author's
  check (Building an absent test).
- `max_diffs` is at most **a quarter** of its folded length (rounded down), so that the budget reaches a near
  copy of the wrong reading, not the page's own text.

**The rule.** The test fails exactly where the same `present` test without the setting passes on the output
with its images left out, and passes everywhere else: it is `not present` on what the page shows. The same search
runs: the text view, after fold, within `max_diffs` edits, numbers exact at any budget, a page that glues its
words searched with its spaces removed, and a word broken at a line end read joined (docs/scoring/
present-text.md). So a near copy within the budget fails, in any case and spacing, in a table and in markdown
(cases ab-near, ab-case-spacing, ab-table, ab-markdown), and a copy that changes a digit does not (case
ab-number-changed).

- Image descriptions are not read, though `present` reads them: a figure's `alt` may describe the figure in
  any words, so the reading written there passes (case ab-alt).
- One copy anywhere in the visible text fails it, as one copy anywhere passes `present`.

## Rules

What the test ignores:

<!-- cases:absent-ignored -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| I | the page as printed: the box is left out | not `Johnathan Quincy Smithers` (md 3) | `<p>Patient name:</p><p>Date: 12 May 2021</p>` | pass | `ab-faithful` |
| I | the box written as a mark | not `Johnathan Quincy Smithers` (md 3) | `<p>Patient name: ████</p>` | pass | `ab-box` |
| I | the box named | not `Johnathan Quincy Smithers` (md 3) | `<p>Patient name: [REDACTED]</p>` | pass | `ab-redacted-word` |
| I | a reading further off than the budget | not `Johnathan Quincy Smithers` (md 3) | `<p>Patient name: John Smith</p>` | pass | `ab-over-budget` |
| I | part of the text, short of the budget | not `Chapter 4. The harbor at night` (md 2) | `<p>Chapter 4.</p>` | pass | `ab-part` |
| I | a digit changed: numbers are exact, as in `present` | not `Account number 4417 1234 5678 9113` (md 2) | `<p>Account number 4417 1234 5678 9112</p>` | pass | `ab-number-changed` |
| I | in an image description, which is not read (`present` reads it) | not `Johnathan Quincy Smithers` (md 3) | `<img alt='Patient name: Johnathan Quincy Smithers'>` | pass | `ab-alt` |
| I | a two-line notice in the order its text layer reads | not `North station opens Tuesday` (md 3) | `<p>Opens Tuesday</p><p>North station</p>` | pass | `ab-text-order` |
<!-- /cases -->

What it does not look at, so a wrong output passes:

<!-- cases:absent-blind -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| B | a paraphrase or a translation of it | not `Chapter 4. The harbor at night` (md 2) | `<p>Kapitel 4. Der Hafen bei Nacht</p>` | pass | `ab-paraphrase` |
| B | its words apart, with other text between | not `Johnathan Quincy Smithers` (md 3) | `<p>Patient name: Johnathan</p><p>Signed by Quincy Smithers</p>` | pass | `ab-split` |
<!-- /cases -->

What it penalizes:

<!-- cases:absent-penalized -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| P | the hidden text read through the box | not `Johnathan Quincy Smithers` (md 3) | `<p>Patient name: Johnathan Quincy Smithers</p>` | fail: `'Johnathan Quincy Smithers' found, a reading the page does not print` | `ab-read-through` |
| P | a near copy, within the budget | not `Johnathan Quincy Smithers` (md 3) | `<p>Patient name: Jonathan Quincy Smithers</p>` | fail | `ab-near` |
| P | another case and spacing | not `Johnathan Quincy Smithers` (md 3) | `<p>PATIENT NAME:JOHNATHAN QUINCY SMITHERS</p>` | fail | `ab-case-spacing` |
| P | in a table cell | not `Johnathan Quincy Smithers` (md 3) | `<table><tr><td>Patient name:</td><td>Johnathan Quincy Smithers</td></tr></table>` | fail | `ab-table` |
| P | in markdown | not `Johnathan Quincy Smithers` (md 3) | `**Patient name:** Johnathan Quincy Smithers` | fail | `ab-markdown` |
| P | the next page's first line | not `Chapter 4. The harbor at night` (md 2) | `<p>The end of the chapter.</p><p>Chapter 4. The harbor at night</p>` | fail | `ab-next-page` |
| P | a word broken at a line end | not `Chapter 4. The harbor at night` | `<p>Chapter 4. The har- bor at night</p>` | fail | `ab-line-hyphen` |
| P | the same notice, faithful, in its other reading order: why a test is authored only where no reading holds it | not `North station opens Tuesday` (md 3) | `<p>North station</p><p>Opens Tuesday</p>` | fail: `'North station opens Tuesday' found, a reading the page does not print` | `ab-other-order` |
<!-- /cases -->

## Building an absent test

- **The wrong reading must be known exactly**, from how the page was made: the text drawn under a synthetic
  redaction box, the first line of the next page of a book or a scan cut into pages. A guessed wrong reading
  tests nothing, and neither does one taken from an OCR of another page that nobody has checked.
- **No reading of the page may hold it.** A system may write the page's blocks in any order its layout admits
  (two columns, a sidebar, a two-line notice), and a reading that is no copy in one order can be one in
  another: `North station opens Tuesday` is not in the text layer's `Opens Tuesday` / `North station`, but a
  faithful output that writes the lines the other way holds it (cases ab-text-order, ab-other-order). Write
  out every order the page admits, as plain text with a line per block, and run
  `runners.absent_collisions(readings, text_arg)` with the test's own text arg: author the test only where it
  returns no reading. It runs the test's own search, so a match by fold, by glued words, by a line hyphen or
  within the budget counts.
- **Pick a reading long enough to be specific** (20 characters or more after fold, a name with its middle name,
  a whole line) and a budget no wider than the near copies a system writes (an initial dropped, a letter
  misread). The loader refuses a budget over a quarter of the folded length.

## Blind spots

- **A paraphrase or a translation passes** (case ab-paraphrase): the test finds the text, not its meaning.
- **The words written apart pass** (case ab-split): the search is for the whole text, within its budget.
- **A reading further off than the budget passes** (case ab-over-budget), and so does part of it (case ab-part).
- **A reading written into an image description passes** (case ab-alt): the test reads what the page shows.

The why reads `<text> found, a reading the page does not print`, the text cut at 60 characters.
