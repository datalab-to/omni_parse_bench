# `region`

**Asks:** the page prints exactly this between two anchors, and the output writes nothing else there. Family
text; reads `html`. It is a closed-world test: the gold states everything that belongs in the region, so any
word, number or filler the system adds there fails it, without a list of the inventions to look for. It covers a
blank form field (the region holds nothing), the end of a table (nothing between its last cell and the next
paragraph), a caption, a header band and a short page. The published dataset holds no tests of this type yet.

```json
{"test_type": "region", "output_type": "html", "derivation": "authored", "tags": ["form"],
 "args": {"start": {"text": "Date of birth:", "max_diffs": 0},
          "end": {"text": "Place of birth:", "max_diffs": 0}},
 "settings": {}}
```

- `start`: the text the region follows. Without it, the region opens at the page start.
- `end`: the text that ends it. Without it, the region runs to the page end.
- `content`: everything the page prints between them. Without it, the region must hold nothing.
- The anchors have `max_diffs` 0 (a fuzzy match has no exact boundary); `content` may have edits to spend, fewer
  than its folded length, as any text arg. Every arg is text, with no `place` and no `exact_case`; there are no
  settings. The loader refuses a `start` equal to the `end`, and a `content` that holds either anchor (the region
  would be cut there).

**How the page is read.** The page is the text view without image descriptions and without the marks the text
view writes for an element that holds nothing (as `page_near_empty`), folded, in the html's order. Two things
fold would lose are kept: where fold joins a hyphen a line broke after (`self-` then `aware` on the next line), a
region marks the join, so that it can be read either way (below); and a run of underscores that touches a
letter or a digit on either side (`foo___bar`, `token____`, `____init`) stays, where fold would read it as a
leader. A table is read cell by cell, row by row,
and a region runs on across it, so a value written in a second `<table>` or a row written as a paragraph after
`</table>` is inside the region (cases rg-split-table, rg-row-after).

**Anchors.** An anchor is a whole copy of its text at a word edge (not inside a longer word, not cut out of a
longer number), under fold: a hyphen a line broke after is joined as fold joins it, on both sides. That is one
equivalence, with no second search: a page that glues the anchor's words does not hold the anchor. A copy
inside a longer label is a copy (`Date of birth:` in `Mother's Date of birth:`, case rg-longer-label). A copy
of `start` inside a copy of a longer `end` (`Table 3` in `Table 3 (continued)`) belongs to the end. An anchor
may not hold a hyphen after a letter: where a page breaks the line there, fold joins the word
(`<h1>Self-<br>aware systems</h1>` reads `selfaware systems`), so the anchor `Self-aware systems` would not be
found on a faithful page. The loader refuses one; a hyphen after a digit or a space (`3-D`, `Name -`) is
kept.

**Every copy.** Each copy of `start` opens a region that runs to the first copy of `end` after it, or to the page
end when the test has no `end`. The test passes only when **every** region is right, so writing the field twice,
once blank and once filled, fails (case rg-second-copy). A copy of `start` with no `end` after it fails (case
rg-end-first). Without a `start`, one region opens at the page start and ends at the first copy of `end`.

**The comparison.** The region and the content are compared as whole strings, never by searching one in the
other. With no edits to spend, nothing that changes the text passes:

- a run of white space is one space, and a space is text: `in to` is not `into`, `Total Due` is not `TotalDue`
  (cases rg-glued, rg-split-word);
- a hyphen or an underscore that touches a letter or a digit is text: `re-sign` is not `resign`, `max_rows` is
  not `maxrows`, `_token` and `token____` are not `token` (cases rg-hyphen-dropped, rg-underscore,
  rg-underscore-run);
- not compared: a run of underscores that touches no letter or digit (a line printed to write on, which fold
  keeps when shorter than 3 and markdown may read as emphasis: `__/__/____` is written `//`; cases
  rg-blank-line, rg-mask-markdown, rg-mask-lost), and a bullet glyph before a space (a list's mark);
- a hyphen a line broke after, where fold joins it, is one unit, free to read as a hyphen or as nothing, on
  either side: `self-` `aware` matches `self-aware` and `selfaware`, never `self aware` (cases rg-hyphen,
  rg-hyphen-joined, rg-hyphen-space); a hyphen fold keeps (`Anglo- Saxon`) is text;
- the two may differ by at most `max_diffs` edits (a character substituted, inserted or deleted, or two adjacent
  characters swapped), counted over the whole region;
- their numbers must be equal, in order, at any budget: a number is its sign, its digits, the `.` and `,`
  between them or before them, and a `%` after them, so `-12.5` is not `+12.5`, `1.25` is not `1,25`, `.5` is
  not `5` and `12 500` is not `12500` (cases rg-number-in-budget, rg-sign, rg-decimal, rg-number-split).
  A sign is the number's wherever it stands before the digits: after a space, a letter or a symbol, so an
  exponent's sign counts (`1e-3` reads 1 and -3, and is not `1e+3`, case rg-exponent), and so does a code's
  (`Δ-12` is not `Δ+12`, and `COVID-19` is not `COVID 19`, case rg-code-hyphen). A `-` or `+` right after a
  digit is not a sign: it joins two numbers, a range or a date (`10-12`, `12-05-2021`, case rg-range). These
  are the only numeric forms a region reads; it does not change how `present` or `absent` read numbers.

The text view writes a superscript as a word of its own (`parsing.<sup>1</sup>` reads `parsing. 1`); content
that holds a superscript writes it so. A NUL character on the page is read as U+FFFD, as an HTML parser reads it;
the loader refuses one in a region's text.

## Rules

What the test ignores:

<!-- cases:region-ignored -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| I | a blank field | `Date of birth:` … `Place of birth:`: nothing | `<p>Name: Ann Lee</p><p>Date of birth: </p><p>Place of birth: Paris</p>` | pass | `rg-blank` |
| I | a line to write on (three or more underscores or dots, which fold removes) | `Date of birth:` … `Place of birth:`: nothing | `<p>Name: Ann Lee</p><p>Date of birth: ______</p><p>Place of birth: Paris</p>` | pass | `rg-blank-line` |
| I | a run of dots | `Date of birth:` … `Place of birth:`: nothing | `<p>Name: Ann Lee</p><p>Date of birth: .........</p><p>Place of birth: Paris</p>` | pass | `rg-blank-leader` |
| I | an empty element, a line break, a zero-width space | `Date of birth:` … `Place of birth:`: nothing | `<p>Name: Ann Lee</p><p>Date of birth: <span></span><br>​</p><p>Place of birth: Paris</p>` | pass | `rg-blank-markup` |
| I | the printed mask, as html | `Date of birth:` … `Place of birth:`: `__/__/____` | `<p>Name: Ann Lee</p><p>Date of birth: __/__/____</p><p>Place of birth: Paris</p>` | pass | `rg-mask` |
| I | the mask's underscores left out: a printed line is not compared | `Date of birth:` … `Place of birth:`: `__/__/____` | `<p>Name: Ann Lee</p><p>Date of birth: //</p><p>Place of birth: Paris</p>` | pass | `rg-mask-lost` |
| I | the printed mask written as markdown, which reads its underscores as emphasis | `Date of birth:` … `Place of birth:`: `__/__/____` | `Name: Ann Lee\n\nDate of birth: __/__/____\n\nPlace of birth: Paris` | pass | `rg-mask-markdown` |
| I | spacing, case and markup inside the region | `Abstract` … `Introduction`: `We study parsing. It is hard.` | `<h2>ABSTRACT</h2><p>We  study <b>parsing</b>.<br>It is hard.</p><h2>Introduction</h2>` | pass | `rg-spacing` |
| I | a compound broken at a line end | page start … page end: `A self-aware system` | `A self-<br>aware system` | pass | `rg-hyphen` |
| I | a word broken at a line end, joined in the gold | page start … page end: `Our developers` | `Our develop-<br>ers` | pass | `rg-hyphen-joined` |
| I | a date's hyphens written as slashes, within the budget: a hyphen after a digit joins two numbers | page start … page end: `Issued 12-05-2021` (md 2) | `Issued 12/05/2021` | pass | `rg-range` |
| I | the region runs across a table, cell by cell | `Table 2. Costs` … `The costs fell`: `Rent 100 Fuel 70` | `<p>Table 2. Costs</p><table><tr><td>Rent</td><td>100</td></tr><tr><td>Fuel</td><td>70</td></tr></table><p>The costs fell.</p>` | pass | `rg-across-table` |
| I | nothing after a table's last cell | `Fuel 70` … `The costs fell`: nothing | `<table><tr><td>Rent</td><td>100</td></tr><tr><td>Fuel</td><td>70</td></tr></table><p>The costs fell.</p>` | pass | `rg-table-end` |
| I | the page written twice, both copies right | `Date of birth:` … `Place of birth:`: nothing | `<p>Name: Ann Lee</p><p>Date of birth: </p><p>Place of birth: Paris</p><p>Name: Ann Lee</p><p>Date of birth: </p><p>Place of birth: Paris</p>` | pass | `rg-two-copies-clean` |
| I | a misread letter within the budget | `Table 3` … `Mean`: `Results of the trial` (md 2) | `<p>Table 3 Results of the trail</p><p>Mean</p>` | pass | `rg-within-budget` |
| I | no anchors: the whole page | page start … page end: `Page intentionally left blank` | `<p>Page intentionally<br>left blank</p>` | pass | `rg-whole-page` |
<!-- /cases -->

What it does not look at, so a wrong output passes:

<!-- cases:region-blind -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| B | an image description in the region is not read | `Date of birth:` … `Place of birth:`: nothing | `<p>Name: Ann Lee</p><p>Date of birth: <img alt='12/03/1985'></p><p>Place of birth: Paris</p>` | pass | `rg-alt` |
| B | text before the start is outside the region | `Date of birth:` … `Place of birth:`: nothing | `<p>12/03/1985 Date of birth:</p><p>Place of birth: Paris</p>` | pass | `rg-before-start` |
| B | a header-row table reads its labels first, then its values | `Date of birth:` … `Place of birth:`: nothing | `<table><tr><td>Date of birth:</td><td>Place of birth:</td></tr><tr><td>12/03/1985</td><td>Paris</td></tr></table>` | pass | `rg-header-row` |
| B | letters added within the budget | `Table 3` … `Mean`: `Results of the trial` (md 2) | `<p>Table 3 Results of the trial a</p><p>Mean</p>` | pass | `rg-budget-letters` |
<!-- /cases -->

An image description, read by `present`, not by `region`:

<!-- cases:region-alt -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| I | `present` reads an image description | `a bar chart of rates by year` | `<p>Figure 2</p><img alt='A bar chart of rates by year'><p>Source: WHO</p>` | pass | `rg-alt-present` |
| P | `region` does not: author regions only where no figure is | `Figure 2` … `Source: WHO`: `A bar chart of rates by year` | `<p>Figure 2</p><img alt='A bar chart of rates by year'><p>Source: WHO</p>` | fail | `rg-alt-region` |
<!-- /cases -->

What it penalizes:

<!-- cases:region-penalized -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| P | a value in a blank field | `Date of birth:` … `Place of birth:`: nothing | `<p>Name: Ann Lee</p><p>Date of birth: 12/03/1985</p><p>Place of birth: Paris</p>` | fail: `between 'Date of birth:' and 'Place of birth:' holds '12/03/1985' where the gold has nothing (10 edits, max_diffs 0)` | `rg-filled` |
| P | a filler for a blank | `Date of birth:` … `Place of birth:`: nothing | `<p>Name: Ann Lee</p><p>Date of birth: N/A</p><p>Place of birth: Paris</p>` | fail: `between 'Date of birth:' and 'Place of birth:' holds 'n/a' where the gold has nothing (3 edits, max_diffs 0)` | `rg-filler` |
| P | a dash for a blank | `Date of birth:` … `Place of birth:`: nothing | `<p>Name: Ann Lee</p><p>Date of birth: —</p><p>Place of birth: Paris</p>` | fail | `rg-dash` |
| P | the mask filled in | `Date of birth:` … `Place of birth:`: `__/__/____` | `<p>Name: Ann Lee</p><p>Date of birth: 12/03/1985</p><p>Place of birth: Paris</p>` | fail | `rg-mask-filled` |
| P | the page written twice, one copy filled | `Date of birth:` … `Place of birth:`: nothing | `<p>Name: Ann Lee</p><p>Date of birth: </p><p>Place of birth: Paris</p><p>Name: Ann Lee</p><p>Date of birth: 1985</p><p>Place of birth: Paris</p>` | fail: `copy 2 of 2: between 'Date of birth:' and 'Place of birth:' holds '1985' where the gold has nothing (4 edits, max_diffs 0)` | `rg-second-copy` |
| P | a value two cells right of the label | `Date of birth:` … `Place of birth:`: nothing | `<table><tr><td>Date of birth:</td><td></td><td>1985</td></tr><tr><td>Place of birth:</td><td>Paris</td></tr></table>` | fail | `rg-second-cell` |
| P | a value in a second table | `Date of birth:` … `Place of birth:`: nothing | `<table><tr><td>Date of birth:</td></tr></table><table><tr><td>1985</td></tr></table><p>Place of birth: Paris</p>` | fail | `rg-split-table` |
| P | a row added after a table, as a paragraph or a second table | `Fuel 70` … `The costs fell`: nothing | `<table><tr><td>Rent</td><td>100</td></tr><tr><td>Fuel</td><td>70</td></tr></table><p>Total 170</p><p>The costs fell.</p>` | fail: `between 'Fuel 70' and 'The costs fell' holds 'total 170' where the gold has nothing (9 edits, max_diffs 0)` | `rg-row-after` |
| P | a sentence written twice (a loop) | `Abstract` … `Introduction`: `We study parsing. It is hard.` | `<p>Abstract</p><p>We study parsing. It is hard. It is hard.</p><p>Introduction</p>` | fail: `between 'Abstract' and 'Introduction' holds 'we study parsing. it is hard. it is hard.' where the gold has 'we study parsing. it is hard.' (12 edits, max_diffs 0)` | `rg-duplicate-sentence` |
| P | a sentence added to a caption | `Table 3` … `Mean`: `Results of the trial` (md 2) | `<p>Table 3 Results of the trial. Source: WHO</p><p>Mean</p>` | fail | `rg-caption-added` |
| P | a number changed, within the budget | `Table 3` … `Mean`: `Results of 2019` (md 2) | `<p>Table 3 Results of 2018</p><p>Mean</p>` | fail: `between 'Table 3' and 'Mean' holds 'results of 2018' where the gold has 'results of 2019' (a number differs)` | `rg-number-in-budget` |
| P | a number split by a space | page start … page end: `Total 12500` | `Total 12 500` | fail: `the page holds 'total 12 500' where the gold has 'total 12500' (1 edit, max_diffs 0)` | `rg-number-split` |
| P | text of the region left out | `Abstract` … `Introduction`: `We study parsing. It is hard.` | `<p>Abstract</p><p>We study parsing.</p><p>Introduction</p>` | fail | `rg-missing-text` |
| P | the start not on the page | `Date of birth:` … `Place of birth:`: nothing | `<p>Place of birth: Paris</p>` | fail: `start 'Date of birth:' not found whole, at a word edge` | `rg-no-start` |
| P | the end not on the page | `Date of birth:` … `Place of birth:`: nothing | `<p>Date of birth:</p>` | fail: `end 'Place of birth:' not found whole, at a word edge` | `rg-no-end` |
| P | the end only before the start | `Date of birth:` … `Place of birth:`: nothing | `<p>Place of birth: Paris</p><p>Date of birth:</p>` | fail: `no end 'Place of birth:' after start 'Date of birth:'` | `rg-end-first` |
| P | words glued together: a space is text | `Abstract` … `Introduction`: `We study parsing.` | `<p>Abstract WeStudyParsing. Introduction</p>` | fail | `rg-glued` |
| P | a word split in two | page start … page end: `Please sign into the portal` | `Please sign in to the portal` | fail: `the page holds 'please sign in to the portal' where the gold has 'please sign into the portal' (1 edit, max_diffs 0)` | `rg-split-word` |
| P | a hyphen inside a word dropped (`re-sign` is not `resign`) | page start … page end: `re-sign the lease` | `resign the lease` | fail: `the page holds 'resign the lease' where the gold has 're-sign the lease' (1 edit, max_diffs 0)` | `rg-hyphen-dropped` |
| P | an underscore inside a name dropped | page start … page end: `set max_rows` | `set maxrows` | fail | `rg-underscore` |
| P | a hyphen a line broke after, read as a space | page start … page end: `A self aware system` | `A self-<br>aware system` | fail: `the page holds 'a self-aware system' where the gold has 'a self aware system' (1 edit, max_diffs 0)` | `rg-hyphen-space` |
| P | a sign changed, within the budget | page start … page end: `Net -12.5` (md 2) | `Net +12.5` | fail: `the page holds 'net +12.5' where the gold has 'net -12.5' (a number differs)` | `rg-sign` |
| P | an exponent's sign changed, within the budget | page start … page end: `Concentration 1e-3 M` (md 1) | `Concentration 1e+3 M` | fail: `the page holds 'concentration 1e+3 m' where the gold has 'concentration 1e-3 m' (a number differs)` | `rg-exponent` |
| P | a code's hyphen before a digit, its minus sign, written as a space | page start … page end: `Strain COVID-19` (md 2) | `Strain COVID 19` | fail: `the page holds 'strain covid 19' where the gold has 'strain covid-19' (a number differs)` | `rg-code-hyphen` |
| P | an underscore run at the end of a name dropped | page start … page end: `set token____` | `set token` | fail: `the page holds 'set token' where the gold has 'set token____' (4 edits, max_diffs 0)` | `rg-underscore-run` |
| P | a decimal point written as a comma, within the budget | page start … page end: `Rate 1.25` (md 2) | `Rate 1,25` | fail | `rg-decimal` |
| P | the start inside a longer label opens a region too: a start must be unique on the page | `Date of birth:` … `Place of birth:`: nothing | `<p>Date of birth:</p><p>Place of birth: Paris</p><p>Mother's Date of birth: 1960</p><p>Mother's Place of birth: Rome</p>` | fail: `copy 2 of 2: between 'Date of birth:' and 'Place of birth:' holds "1960 mother's" where the gold has nothing (13 edits, max_diffs 0)` | `rg-longer-label` |
| P | a footnote marker the content does not hold | `Abstract` … `Introduction`: `We study parsing.` | `<p>Abstract</p><p>We study parsing.<sup>1</sup></p><p>Introduction</p>` | fail | `rg-footnote` |
| P | no anchors: a line added to the page | page start … page end: `Page intentionally left blank` | `<p>Page intentionally left blank</p><p>This page is empty.</p>` | fail: `the page holds 'page intentionally left blank this page is empty.' where the gold has 'page intentionally left blank' (20 edits, max_diffs 0)` | `rg-whole-page-extra` |
<!-- /cases -->

## Building a region test

- **The gold must be exact by construction.** The content is everything a reader sees between the anchors: a
  born-digital text layer, a JATS table and the paragraph after it, an authored or rendered page, or a human
  review of the region. A guessed region fails faithful outputs.
- **Each anchor must have exactly one copy in the page's text**, found as the scorer finds it: at a word edge,
  inside longer labels too (`Date of birth:` has a copy in `Mother's Date of birth:`, case rg-longer-label), and
  in page furniture (a running header, a footer). `runners.region_anchor_copies(page_text, anchor)` counts them on
  the page's full text; author a region only where it returns 1 for each anchor. An anchor holds no hyphen
  after a letter (the loader refuses one, see Anchors): pick `Self` … or the line before. Pick anchors inside one column
  or block, so that reading order cannot put other text between them.
- **Author regions only where no figure is.** An image's description is not read (as in `page_near_empty`), so
  text a system writes as an `alt` is lost to the region, though `present` credits it (cases rg-alt-present,
  rg-alt-region). A region whose page prints a figure, a chart or a stamp between its anchors is not authored.
- **Keep page furniture out of the region**, or include its text in the content: a running header or a page
  number between the anchors is content.
- **A footnote marker in the region is content.** A system that writes it as `<sup>1</sup>` writes a `1`; one
  that drops it loses a number (case rg-footnote). Choose a region without markers, or put the markers in the
  content.
- **A header-row table** (labels in one row, values in the next) reads every label before any value, so a field
  there is not a region; use `table_cell` with `{"empty": true}` (case rg-header-row).
- **A value written before its label** is outside the label's region (case rg-before-start). To guard it, open
  the region at the field before: `start` the previous field's label, `content` its value and this label.

## Blind spots

- **Image descriptions are not read**, as in `page_near_empty` and `blank_after`: invented text in an `alt` inside
  the region passes (case rg-alt).
- **Text outside the region is not read**, before its start or after its end (cases rg-before-start,
  rg-header-row).
- **A budget is spent on anything.** With `max_diffs` 2, two invented letters pass, though never a changed or
  added number (cases rg-budget-letters, rg-number-in-budget). With `max_diffs` 0, nothing passes that changes
  the text.

The why reads `<where> holds <output> where the gold has <content> (<n> edit(s), max_diffs <k>)`, or
`(a number differs)`; `<where>` is `between <start> and <end>`, `after <start> to the page end`, `from the page
start to <end>` or `the page`, and `copy <i> of <n>: ` comes first when `start` has several copies. A missing
anchor reads `start <text> not found whole, at a word edge`, `end <text> not found whole, at a word edge` or
`no end <end> after start <start>`.
