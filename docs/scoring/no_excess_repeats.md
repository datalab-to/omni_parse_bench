# `no_excess_repeats`

**Asks:** the output repeats no passage more often than the page prints its words. Family text; reads `html`.
It is the test for a model that loops or writes a passage twice: it needs the page's full text, not a list of
the passages to watch. The published dataset holds no tests of this type yet.

```json
{"test_type": "no_excess_repeats", "output_type": "html", "derivation": "authored", "tags": [],
 "args": {"content": {"text": "<the page's complete text>", "max_diffs": 0}},
 "settings": {}}
```

- `content`: everything the page prints outside its figures, its tables' text included, in any order. Its words are counted,
  never matched, so the order of the text does not matter. A text arg with `max_diffs` 0, no `place`, no
  `exact_case`, at least one word, and no character of a script written without spaces between words (Thai,
  Lao, Khmer, Myanmar, Tibetan, Han, kana, Hangul): the loader refuses one, since a word count there needs a
  word segmenter the scorer does not have. No settings.

**The rule.** The output's words are read from the text view, a table's cells as text, without image
descriptions (as `repeat`), without figures (a `<figure>` is read for its `<figcaption>` only) and without math,
after fold. Figures and `<math>` are elements of the parsed html, so a tag written in a comment or an attribute
is text; a dollar span is math only where `mathspans` pairs it as math, so a price is text. A word is a run of
letters, digits and marks, and a hyphen between two letters joins them, so `self-aware`, `self-<br>aware` and
`selfaware` are one word on both sides (case rx-wrapped). The test fails when some run of **16 consecutive
words** appears two or more times in the output, **and** each word of that run appears more times in the output
than in `content`. Otherwise it passes.

- The first condition finds a repeat; the second says the page does not print it that often. A passage the page
  prints twice may be written twice (case rx-printed-twice), not three times (case rx-printed-twice-three).
- The gold's order never matters: only its words are counted. The output's order matters only through the
  first condition: a passage of 16 words or more written twice is found wherever the copies stand, but two
  shorter blocks each written twice are found only when a run of 16 repeats across them (written A B A B, not
  A A B B; case rx-short-blocks).
- Text left out costs nothing here; `present` and `order` tests see it (case rx-dropped). An output with no text at
  all is not text left out: it fails (case rx-empty), unless the page is blank (case rx-empty-blank), below.
- A table counts as text on both sides: the content holds its cells, and the output's cells are read however
  it writes them, in a `<table>`, as a markdown table or flattened to paragraphs (cases rx-table, rx-table-pipe,
  rx-table-flat). A row the page prints once, written twice, fails (case rx-table-row-twice).

**Which pages.** The gold must be the page's complete text, exact by construction: a page we rendered,
retypeset or wrote, from the text its build holds. A text layer is not such a gold. On the public pages,
with each PDF's text layer standing in for the gold, a hand audit of 100 failing outputs found 17 where the
page does print the repeat: a citation page whose text layer is garbled, tick labels repeated across the
panels of a chart, notes shared by two drawings of an engineering plan, and a page in Thai. Leave out figure
and chart text on both sides (the text view drops a `<figure>`; the gold leaves its text out), and pages in a
script written without spaces.

**Why 16.** Measured on the saved public runs of 27 systems against the text layers of the 1,830 public PDF
pages with 50 words or more (43,782 page outputs), tables read as text and math left out: runs of 12, 16, 20
and 24 words fail 3.06%, 2.41%, 1.99% and 1.69% of the outputs (1,341, 1,057, 873 and 742). Reading tables adds
333 failures to the 724 with tables left out: half repeat their run three or more times (loops inside a table),
and the rest write a passage twice (in a sample of 10: a caption written as a paragraph and again as the
table's caption, a note or a header row written twice, cells a page may print twice). In a hand-read sample from a first
pass of this measurement, 9 of 14 outputs that failed at 12 and passed at 16 were phrases the page prints twice
(a figure's ticks, a clause shared by two sentences, a phrase the text layer holds once), and all 8 sampled
failures whose run appears 3 or more times were loops; a longer run lets every duplicated sentence shorter than
it pass.

**Why every word.** The second condition asks that **each** word of the run be in excess, not most of them. It
is the narrowest form that is exact by construction: if the output writes some word of the run no more often
than the page prints it, the repeat may be one the page prints, and the test cannot tell. In a first pass of
the measurement above, asking that 75%, 50% or any one of the run's words be in excess failed 2.08%, 2.56% and
4.28% of the outputs, against 1.69% for every word. Counting runs instead (a run of 16 written more often than
the gold holds that run) fails 7.28%, mostly where the page prints the passage but the gold does not hold it as
one run. The cost of every word is the blind spot below: a duplicate made only of words the page prints often
elsewhere passes (case rx-common-words).

**What is not read.**

- **Figures** other than their caption, and **image descriptions** (case rx-alt).
- **Math** (`$..$`, `$$..$$`, `\(..\)`, `\[..\]`, `<math>`): `present` reads equations, and a page's own
  symbols repeat (case rx-math).

## Rules

What the test ignores:

<!-- cases:repeats-ignored -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| I | the page as printed | the page's two sentences | `<p>The committee met on Monday to review the budget and the plans for the new library downtown.</p><p>Members asked for a second estimate before the vote.</p>` | pass | `rx-faithful` |
| I | its blocks in another order | the page's two sentences | `<p>Members asked for a second estimate before the vote.</p><p>The committee met on Monday to review the budget and the plans for the new library downtown.</p>` | pass | `rx-reordered` |
| I | spacing, case and markup | the page's two sentences | `<p><b>THE COMMITTEE</b> met  on Monday to review the budget and the plans for the new library downtown.</p><p>Members asked for a second estimate before the vote.</p>` | pass | `rx-markup` |
| I | a passage the page prints twice, written twice | the first sentence, twice | `<p>The committee met on Monday to review the budget and the plans for the new library downtown.</p><p>The committee met on Monday to review the budget and the plans for the new library downtown.</p>` | pass | `rx-printed-twice` |
| I | a phrase shorter than 16 words written twice | `Total due on receipt of this invoice.` | `<p>Total due on receipt of this invoice.</p><p>Total due on receipt of this invoice.</p>` | pass | `rx-short-repeat` |
| I | text left out (other tests miss it) | the page's two sentences | `<p>The committee met on Monday to review the budget and the plans for the new library downtown.</p>` | pass | `rx-dropped` |
| I | nothing written, on a blank page (its gold holds a `page_near_empty` test) | the page's two sentences, on a page with a `page_near_empty` test | `""` | pass | `rx-empty-blank` |
| I | a table the page prints, as a table | the page's two sentences and its table's two rows | `<p>The committee met on Monday to review the budget and the plans for the new library downtown.</p><p>Members asked for a second estimate before the vote.</p><table><tr><td>Not applicable, see note one for the details of the lease terms and the fees listed in the annex</td></tr><tr><td>Not applicable, see note one for the details of the lease terms and the fees listed in the annex</td></tr></table>` | pass | `rx-table` |
| I | the same table as a markdown table left in a paragraph | the page's two sentences and its table's two rows | `<p>The committee met on Monday to review the budget and the plans for the new library downtown.</p><p>Members asked for a second estimate before the vote.</p><p>\| Not applicable, see note one for the details of the lease terms and the fees listed in the annex \|\n\| Not applicable, see note one for the details of the lease terms and the fees listed in the annex \|</p>` | pass | `rx-table-pipe` |
| I | the same table flattened to paragraphs | the page's two sentences and its table's two rows | `<p>The committee met on Monday to review the budget and the plans for the new library downtown.</p><p>Members asked for a second estimate before the vote.</p><p>Not applicable, see note one for the details of the lease terms and the fees listed in the annex</p><p>Not applicable, see note one for the details of the lease terms and the fees listed in the annex</p>` | pass | `rx-table-flat` |
| I | math is not read | the page's two sentences | `<p>The committee met on Monday to review the budget and the plans for the new library downtown.</p><p>Members asked for a second estimate before the vote.</p><p>$x x x x x x x x x x x x x x x x x x x x x x x x x x x x x x x x$</p>` | pass | `rx-math` |
| I | an image description is not read | the page's two sentences | `<p>The committee met on Monday to review the budget and the plans for the new library downtown.</p><p>Members asked for a second estimate before the vote.</p><img alt='The committee met on Monday to review the budget and the plans for the new library downtown. The committee met on Monday to review the budget and the plans for the new library downtown.'>` | pass | `rx-alt` |
| I | a figure's text is not read, its caption is | the page's two sentences | `<p>The committee met on Monday to review the budget and the plans for the new library downtown.</p><p>Members asked for a second estimate before the vote.</p><figure><p>The committee met on Monday to review the budget and the plans for the new library downtown.</p><figcaption>Figure 1.</figcaption></figure>` | pass | `rx-figure` |
| I | a compound broken at a line end, written twice where the page prints it twice | the sentence twice | `<p>The self-<br>aware system logs each request it serves and the reply it sends back to the client.</p><p>The self-aware system logs each request it serves and the reply it sends back to the client.</p>` | pass | `rx-wrapped` |
<!-- /cases -->

What it does not look at, so a wrong output passes:

<!-- cases:repeats-blind -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| B | an invented passage written once | the page's two sentences | `<p>The committee met on Monday to review the budget and the plans for the new library downtown.</p><p>Members asked for a second estimate before the vote.</p><p>The library will open in the spring of next year, and the city will pay for most of it.</p>` | pass | `rx-once-invented` |
| B | a copy with one word changed in every 16 | the page's two sentences | `<p>The committee met on Monday to review the budget and the plans for the new library downtown.</p><p>The committee met on Tuesday to review the budget and the plans for the new library downtown.</p><p>Members asked for a second estimate before the vote.</p>` | pass | `rx-near-copy` |
| B | a restart that repeats fewer than 16 words | the page's two sentences | `<p>The committee met on Monday to review the budget and the plans for the new library downtown. to review the budget and the plans for the new library downtown. Members asked for a second estimate before the vote.</p>` | pass | `rx-tail-restart` |
| B | a repeat of words the page prints often enough elsewhere | the first sentence twice, the second once | `<p>The committee met on Monday to review the budget and the plans for the new library downtown.</p><p>The committee met on Monday to review the budget and the plans for the new library downtown.</p><p>Members asked for a second estimate before the vote.</p><p>Members asked for a second estimate before the vote.</p>` | pass | `rx-common-words` |
| B | a loop of one word joined by hyphens: one word | the page's two sentences | `<p>The committee met on Monday to review the budget and the plans for the new library downtown.</p><p>Members asked for a second estimate before the vote.</p><p>budget-budget-budget-budget-budget-budget-budget-budget-budget-budget-budget-budget-budget-budget-budget-budget-budget-budget-budget-budget-budget-budget-budget-budget-budget-budget-budget-budget-budget-budget-budget-budget-budget-budget-budget-budget-budget-budget-budget-budget</p>` | pass | `rx-loop-hyphens` |
| B | a loop with a number that changes every 8 words | the page's two sentences | `<p>The committee met on Monday to review the budget and the plans for the new library downtown.</p><p>Members asked for a second estimate before the vote.</p><p>item 1 and the plans for the library item 2 and the plans for the library item 3 and the plans for the library item 4 and the plans for the library item 5 and the plans for the library item 6 and the plans for the library item 7 and the plans for the library item 8 and the plans for the library item 9 and the plans for the library item 10 and the plans for the library item 11 and the plans for the library item 12 and the plans for the library</p>` | pass | `rx-loop-counter` |
| B | two 8-word blocks each doubled in place (A A B B): no run of 16 repeats | two 8-word blocks | `<p>one two three four five six seven eight</p><p>one two three four five six seven eight</p><p>nine ten eleven twelve thirteen fourteen fifteen sixteen</p><p>nine ten eleven twelve thirteen fourteen fifteen sixteen</p>` | pass | `rx-short-blocks` |
<!-- /cases -->

What it penalizes:

<!-- cases:repeats-penalized -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| P | nothing written: no output to check | the page's two sentences | `""` | fail: `no output: a test of what the page does not hold passes only an output that writes something, unless the page is blank (a page_near_empty test)` | `rx-empty` |
| P | a sentence written twice | the page's two sentences | `<p>The committee met on Monday to review the budget and the plans for the new library downtown.</p><p>The committee met on Monday to review the budget and the plans for the new library downtown.</p><p>Members asked for a second estimate before the vote.</p>` | fail: `'the committee met on monday to review the budget and the plans for the new libra' appears 2x, and its words more often than the page prints them (e.g. 'the' 9x, the page 5x)` | `rx-duplicate` |
| P | a loop | the page's two sentences | `<p>The committee met on Monday to review the budget and the plans for the new library downtown.</p><p>Members asked for a second estimate before the vote.</p><p>and the plans and the plans and the plans and the plans and the plans and the plans and the plans and the plans and the plans and the plans and the plans and the plans </p>` | fail: `'the plans and the plans and the plans and the plans and the plans and the' appears 7x, and its words more often than the page prints them (e.g. 'the' 17x, the page 5x)` | `rx-loop` |
| P | one word repeated | the page's two sentences | `<p>budget budget budget budget budget budget budget budget budget budget budget budget budget budget budget budget budget budget budget budget budget budget budget budget budget budget budget budget budget budget budget budget budget budget budget budget budget budget budget budget </p>` | fail | `rx-loop-word` |
| P | the whole page written twice | the page's two sentences | `<p>The committee met on Monday to review the budget and the plans for the new library downtown.</p><p>Members asked for a second estimate before the vote.</p><p>The committee met on Monday to review the budget and the plans for the new library downtown.</p><p>Members asked for a second estimate before the vote.</p>` | fail | `rx-page-twice` |
| P | a passage the page prints twice, written three times | the first sentence, twice | `<p>The committee met on Monday to review the budget and the plans for the new library downtown.</p><p>The committee met on Monday to review the budget and the plans for the new library downtown.</p><p>The committee met on Monday to review the budget and the plans for the new library downtown.</p>` | fail: `'the committee met on monday to review the budget and the plans for the new libra' appears 3x, and its words more often than the page prints them (e.g. 'the' 12x, the page 8x)` | `rx-printed-twice-three` |
| P | a duplicate split over two blocks | the page's two sentences | `<p>The committee met on Monday to review the budget and the plans for the new library downtown.</p><p>The committee met on Monday to review the budget</p><p>and the plans for the new library downtown.</p><p>Members asked for a second estimate before the vote.</p>` | fail | `rx-paragraph-split` |
| P | a table row written twice in a table | the page's two sentences and its table's row | `<p>The committee met on Monday to review the budget and the plans for the new library downtown.</p><p>Members asked for a second estimate before the vote.</p><table><tr><td>Not applicable, see note one for the details of the lease terms and the fees listed in the annex</td></tr><tr><td>Not applicable, see note one for the details of the lease terms and the fees listed in the annex</td></tr></table>` | fail | `rx-table-row-twice` |
| P | the same two blocks written A B A B: a run of 16 repeats across them | two 8-word blocks | `<p>one two three four five six seven eight</p><p>nine ten eleven twelve thirteen fourteen fifteen sixteen</p><p>one two three four five six seven eight</p><p>nine ten eleven twelve thirteen fourteen fifteen sixteen</p>` | fail | `rx-short-blocks-across` |
<!-- /cases -->

## Empty output

The test passes only an output that writes something: html with no character a reader sees outside image
descriptions (nothing, white space, an image alone, as `page_near_empty` counts) fails with `no output: a test of
what the page does not hold passes only an output that writes something, unless the page is blank (a
page_near_empty test)` (case rx-empty). Without this, writing nothing earned a pass. When the page's gold holds a
`page_near_empty` test the page is blank, an empty output is the right answer, and it passes (case rx-empty-blank).

## Building a test

- **Author it only on pages whose complete text we produced**: rendered, retypeset or synthetic pages, with
  the content taken from the text the build drew, its tables' text included and its figures left out. A word the content lacks counts
  as printed zero times, so a gold that misses text the page prints (vector lettering, a scanned figure, a
  filled field) fails a faithful output that writes it twice where the page prints it twice. Text layers of
  born-digital pages are not used until they can be certified complete (Which pages, above).
- **Leave out pages in a script written without spaces** (the loader refuses one), and pages whose figures or
  charts hold text the output may write as paragraphs.

## Blind spots

- **A repeat shorter than 16 words passes** (case rx-tail-restart), and so does a near copy that changes a word in
  every 16 (case rx-near-copy). Two short blocks each doubled in place pass (case rx-short-blocks).
- **A loop that changes a word in every 16 passes**: a counter in each copy (case rx-loop-counter), or one word
  joined to itself by hyphens, which reads as one word (case rx-loop-hyphens).
- **Invented text written once passes** (case rx-once-invented): this test is about repeats; `verbatim` closes a
  stretch of the page.
- **A repeat of words the page prints often enough elsewhere passes** (case rx-common-words): the words, not the
  passage, are counted, so the second condition is a bound, not an exact count of passages.

The why reads `<run> appears <n>x, and its words more often than the page prints them (e.g. <word> <k>x, the page
<m>x)`, the run cut at 80 characters.
