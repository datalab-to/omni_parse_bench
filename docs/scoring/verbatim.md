# `verbatim`

**Asks:** between two anchors, the output writes what the page prints there, verbatim within the test's edit
budget, and nothing else. Family text; reads `html`. It is a closed-world test: the gold states everything that belongs in the region, so any
word, number or filler the system adds there fails it, without a list of the inventions to look for. It covers a
blank form field (the region holds nothing), the end of a table (nothing between its last cell and the next
paragraph), a caption, a header band and a short page. The published dataset holds no tests of this type yet.

```json
{"test_type": "verbatim", "output_type": "html", "derivation": "authored", "tags": ["form"],
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
`</table>` is inside the region (cases vb-split-table, vb-row-after).

**Anchors.** An anchor is a whole copy of its text at a word edge (not inside a longer word, not cut out of a
longer number), under fold: a hyphen a line broke after is joined as fold joins it, on both sides. That is one
equivalence, with no second search: a page that glues the anchor's words does not hold the anchor. A copy
inside a longer label is a copy (`Date of birth:` in `Mother's Date of birth:`, case vb-longer-label). A copy
of `start` inside a copy of a longer `end` (`Table 3` in `Table 3 (continued)`) belongs to the end. An anchor
may not hold a hyphen after a letter: where a page breaks the line there, fold joins the word
(`<h1>Self-<br>aware systems</h1>` reads `selfaware systems`), so the anchor `Self-aware systems` would not be
found on a faithful page. The loader refuses one; a hyphen after a digit or a space (`3-D`, `Name -`) is
kept.

**Every copy.** Each copy of `start` opens a region that runs to the first copy of `end` after it, or to the page
end when the test has no `end`. The test passes only when **every** region is right, so writing the field twice,
once blank and once filled, fails (case vb-second-copy). A copy of `start` with no `end` after it fails (case
vb-end-first). Without a `start`, one region opens at the page start and ends at the first copy of `end`.

**The comparison.** The region and the content are compared as whole strings, never by searching one in the
other: the region must be the content verbatim within the test's edit budget. With no edits to spend, nothing
that changes the text passes:

- a run of white space is one space, and a space is text: `in to` is not `into`, `Total Due` is not `TotalDue`
  (cases vb-glued, vb-split-word);
- a hyphen or an underscore that touches a letter or a digit is text: `re-sign` is not `resign`, `max_rows` is
  not `maxrows`, `_token` and `token____` are not `token` (cases vb-hyphen-dropped, vb-underscore,
  vb-underscore-run);
- not compared: a run of underscores that touches no letter or digit (a line printed to write on, which fold
  keeps when shorter than 3 and markdown may read as emphasis: `__/__/____` is written `//`; cases
  vb-blank-line, vb-mask-markdown, vb-mask-lost), and a bullet glyph before a space (a list's mark);
- a hyphen a line broke after, where fold joins it, is one unit, free to read as a hyphen or as nothing, on
  either side: `self-` `aware` matches `self-aware` and `selfaware`, never `self aware` (cases vb-hyphen,
  vb-hyphen-joined, vb-hyphen-space); a hyphen fold keeps (`Anglo- Saxon`) is text;
- the two may differ by at most `max_diffs` edits (a character substituted, inserted or deleted, or two adjacent
  characters swapped), counted over the whole region;
- their numbers must be the same, in order, at any budget, read as every test reads them
  ([present-text.md](present-text.md#numbers-are-exact)): a number is its digits, the `.` between them, a `,`
  before exactly three digits, a leading `.` and its sign, so `-12.5` is not `+12.5`, `1.25` is not `1,25`,
  `.5` is not `5` and `12 500` is not `12500` (cases vb-number-in-budget, vb-sign, vb-decimal,
  vb-number-split). A number in scientific notation is one number with its exponent: `1e-3` is not `1e+3`,
  `1e3` or `1 -3` (cases vb-exponent, vb-exponent-split). A sign is a `-`, `+` or `±` directly before a
  number or its currency symbol (`-$1,234` is not `$1,234`, case vb-sign-currency), also after a Chinese,
  Japanese or Korean character (`温度-3` is not `温度 3`, case vb-cjk-sign); after a Latin letter or a digit
  a `-` is a hyphen (`COVID-19` written `COVID 19` costs one edit, case vb-code-hyphen) or joins a range or
  a date (`12-05-2021`, case vb-range), and a `+` or `±` after a value is an operator (`6% ± 2%`). A unit
  exponent or a sign written with a space (`kg -1` for `kg-1`, `- 5` for `-5`) costs one edit (cases
  vb-unit-exponent, vb-spaced-sign).

The text view writes a superscript as a word of its own (`parsing.<sup>1</sup>` reads `parsing. 1`); content
that holds a superscript writes it so. A NUL character on the page is read as U+FFFD, as an HTML parser reads it;
the loader refuses one in a verbatim test's text.

## Rules

What the test ignores:

<!-- cases:verbatim-ignored -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| I | a blank field | `Date of birth:` … `Place of birth:`: nothing | `<p>Name: Ann Lee</p><p>Date of birth: </p><p>Place of birth: Paris</p>` | pass | `vb-blank` |
| I | a line to write on (three or more underscores or dots, which fold removes) | `Date of birth:` … `Place of birth:`: nothing | `<p>Name: Ann Lee</p><p>Date of birth: ______</p><p>Place of birth: Paris</p>` | pass | `vb-blank-line` |
| I | a run of dots | `Date of birth:` … `Place of birth:`: nothing | `<p>Name: Ann Lee</p><p>Date of birth: .........</p><p>Place of birth: Paris</p>` | pass | `vb-blank-leader` |
| I | an empty element, a line break, a zero-width space | `Date of birth:` … `Place of birth:`: nothing | `<p>Name: Ann Lee</p><p>Date of birth: <span></span><br>​</p><p>Place of birth: Paris</p>` | pass | `vb-blank-markup` |
| I | the printed mask, as html | `Date of birth:` … `Place of birth:`: `__/__/____` | `<p>Name: Ann Lee</p><p>Date of birth: __/__/____</p><p>Place of birth: Paris</p>` | pass | `vb-mask` |
| I | the mask's underscores left out: a printed line is not compared | `Date of birth:` … `Place of birth:`: `__/__/____` | `<p>Name: Ann Lee</p><p>Date of birth: //</p><p>Place of birth: Paris</p>` | pass | `vb-mask-lost` |
| I | the printed mask written as markdown, which reads its underscores as emphasis | `Date of birth:` … `Place of birth:`: `__/__/____` | `Name: Ann Lee\n\nDate of birth: __/__/____\n\nPlace of birth: Paris` | pass | `vb-mask-markdown` |
| I | spacing, case and markup inside the region | `Abstract` … `Introduction`: `We study parsing. It is hard.` | `<h2>ABSTRACT</h2><p>We  study <b>parsing</b>.<br>It is hard.</p><h2>Introduction</h2>` | pass | `vb-spacing` |
| I | a compound broken at a line end | page start … page end: `A self-aware system` | `A self-<br>aware system` | pass | `vb-hyphen` |
| I | a word broken at a line end, joined in the gold | page start … page end: `Our developers` | `Our develop-<br>ers` | pass | `vb-hyphen-joined` |
| I | a date's hyphens written as slashes, within the budget: a hyphen after a digit joins two numbers | page start … page end: `Issued 12-05-2021` (md 2) | `Issued 12/05/2021` | pass | `vb-range` |
| I | a sign written with a space, within the budget | page start … page end: `x = -5` (md 1) | `x = - 5` | pass | `vb-spaced-sign` |
| I | a unit exponent written with a space, within the budget | page start … page end: `Unit kg-1` (md 1) | `Unit kg -1` | pass | `vb-unit-exponent` |
| I | a code's hyphen after a letter written as a space, within the budget: no sign | page start … page end: `Strain COVID-19` (md 1) | `Strain COVID 19` | pass | `vb-code-hyphen` |
| I | the region runs across a table, cell by cell | `Table 2. Costs` … `The costs fell`: `Rent 100 Fuel 70` | `<p>Table 2. Costs</p><table><tr><td>Rent</td><td>100</td></tr><tr><td>Fuel</td><td>70</td></tr></table><p>The costs fell.</p>` | pass | `vb-across-table` |
| I | nothing after a table's last cell | `Fuel 70` … `The costs fell`: nothing | `<table><tr><td>Rent</td><td>100</td></tr><tr><td>Fuel</td><td>70</td></tr></table><p>The costs fell.</p>` | pass | `vb-table-end` |
| I | the page written twice, both copies right | `Date of birth:` … `Place of birth:`: nothing | `<p>Name: Ann Lee</p><p>Date of birth: </p><p>Place of birth: Paris</p><p>Name: Ann Lee</p><p>Date of birth: </p><p>Place of birth: Paris</p>` | pass | `vb-two-copies-clean` |
| I | a misread letter within the budget | `Table 3` … `Mean`: `Results of the trial` (md 2) | `<p>Table 3 Results of the trail</p><p>Mean</p>` | pass | `vb-within-budget` |
| I | no anchors: the whole page | page start … page end: `Page intentionally left blank` | `<p>Page intentionally<br>left blank</p>` | pass | `vb-whole-page` |
<!-- /cases -->

What it does not look at, so a wrong output passes:

<!-- cases:verbatim-blind -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| B | an image description in the region is not read | `Date of birth:` … `Place of birth:`: nothing | `<p>Name: Ann Lee</p><p>Date of birth: <img alt='12/03/1985'></p><p>Place of birth: Paris</p>` | pass | `vb-alt` |
| B | text before the start is outside the region | `Date of birth:` … `Place of birth:`: nothing | `<p>12/03/1985 Date of birth:</p><p>Place of birth: Paris</p>` | pass | `vb-before-start` |
| B | a header-row table reads its labels first, then its values | `Date of birth:` … `Place of birth:`: nothing | `<table><tr><td>Date of birth:</td><td>Place of birth:</td></tr><tr><td>12/03/1985</td><td>Paris</td></tr></table>` | pass | `vb-header-row` |
| B | a percent sign written as a per mille sign, within the budget: a percent sign is text | page start … page end: `Rate 5%` (md 1) | `Rate 5‰` | pass | `vb-percent` |
| B | a range's hyphen written as a plus, within the budget: a plus after a value is an operator | page start … page end: `Readings 10-12` (md 1) | `Readings 10+12` | pass | `vb-range-plus` |
| B | a percent sign dropped, within the budget | page start … page end: `Rate 5%` (md 1) | `Rate 5` | pass | `vb-percent-dropped` |
| B | a space after a comma before four digits, within the budget: such a comma is a list comma | page start … page end: `June 7,2016` (md 1) | `June 7, 2016` | pass | `vb-list-comma` |
| B | a plus after a value dropped, within the budget: it is an operator | page start … page end: `Sum 1 +2` (md 1) | `Sum 1 2` | pass | `vb-operator-dropped` |
| B | letters added within the budget | `Table 3` … `Mean`: `Results of the trial` (md 2) | `<p>Table 3 Results of the trial a</p><p>Mean</p>` | pass | `vb-budget-letters` |
<!-- /cases -->

An image description, read by `present`, not by `verbatim`:

<!-- cases:verbatim-alt -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| I | `present` reads an image description | `a bar chart of rates by year` | `<p>Figure 2</p><img alt='A bar chart of rates by year'><p>Source: WHO</p>` | pass | `vb-alt-present` |
| P | `verbatim` does not: author regions only where no figure is | `Figure 2` … `Source: WHO`: `A bar chart of rates by year` | `<p>Figure 2</p><img alt='A bar chart of rates by year'><p>Source: WHO</p>` | fail | `vb-alt-region` |
<!-- /cases -->

What it penalizes:

<!-- cases:verbatim-penalized -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| P | a value in a blank field | `Date of birth:` … `Place of birth:`: nothing | `<p>Name: Ann Lee</p><p>Date of birth: 12/03/1985</p><p>Place of birth: Paris</p>` | fail: `between 'Date of birth:' and 'Place of birth:' holds '12/03/1985' where the gold has nothing (10 edits, max_diffs 0)` | `vb-filled` |
| P | a filler for a blank | `Date of birth:` … `Place of birth:`: nothing | `<p>Name: Ann Lee</p><p>Date of birth: N/A</p><p>Place of birth: Paris</p>` | fail: `between 'Date of birth:' and 'Place of birth:' holds 'n/a' where the gold has nothing (3 edits, max_diffs 0)` | `vb-filler` |
| P | a dash for a blank | `Date of birth:` … `Place of birth:`: nothing | `<p>Name: Ann Lee</p><p>Date of birth: —</p><p>Place of birth: Paris</p>` | fail | `vb-dash` |
| P | the mask filled in | `Date of birth:` … `Place of birth:`: `__/__/____` | `<p>Name: Ann Lee</p><p>Date of birth: 12/03/1985</p><p>Place of birth: Paris</p>` | fail | `vb-mask-filled` |
| P | the page written twice, one copy filled | `Date of birth:` … `Place of birth:`: nothing | `<p>Name: Ann Lee</p><p>Date of birth: </p><p>Place of birth: Paris</p><p>Name: Ann Lee</p><p>Date of birth: 1985</p><p>Place of birth: Paris</p>` | fail: `copy 2 of 2: between 'Date of birth:' and 'Place of birth:' holds '1985' where the gold has nothing (4 edits, max_diffs 0)` | `vb-second-copy` |
| P | a value two cells right of the label | `Date of birth:` … `Place of birth:`: nothing | `<table><tr><td>Date of birth:</td><td></td><td>1985</td></tr><tr><td>Place of birth:</td><td>Paris</td></tr></table>` | fail | `vb-second-cell` |
| P | a value in a second table | `Date of birth:` … `Place of birth:`: nothing | `<table><tr><td>Date of birth:</td></tr></table><table><tr><td>1985</td></tr></table><p>Place of birth: Paris</p>` | fail | `vb-split-table` |
| P | a row added after a table, as a paragraph or a second table | `Fuel 70` … `The costs fell`: nothing | `<table><tr><td>Rent</td><td>100</td></tr><tr><td>Fuel</td><td>70</td></tr></table><p>Total 170</p><p>The costs fell.</p>` | fail: `between 'Fuel 70' and 'The costs fell' holds 'total 170' where the gold has nothing (9 edits, max_diffs 0)` | `vb-row-after` |
| P | a sentence written twice (a loop) | `Abstract` … `Introduction`: `We study parsing. It is hard.` | `<p>Abstract</p><p>We study parsing. It is hard. It is hard.</p><p>Introduction</p>` | fail: `between 'Abstract' and 'Introduction' holds 'we study parsing. it is hard. it is hard.' where the gold has 'we study parsing. it is hard.' (12 edits, max_diffs 0)` | `vb-duplicate-sentence` |
| P | a sentence added to a caption | `Table 3` … `Mean`: `Results of the trial` (md 2) | `<p>Table 3 Results of the trial. Source: WHO</p><p>Mean</p>` | fail | `vb-caption-added` |
| P | a number changed, within the budget | `Table 3` … `Mean`: `Results of 2019` (md 2) | `<p>Table 3 Results of 2018</p><p>Mean</p>` | fail: `between 'Table 3' and 'Mean' holds 'results of 2018' where the gold has 'results of 2019' (a number differs)` | `vb-number-in-budget` |
| P | a number split by a space | page start … page end: `Total 12500` | `Total 12 500` | fail: `the page holds 'total 12 500' where the gold has 'total 12500' (1 edit, max_diffs 0)` | `vb-number-split` |
| P | text of the region left out | `Abstract` … `Introduction`: `We study parsing. It is hard.` | `<p>Abstract</p><p>We study parsing.</p><p>Introduction</p>` | fail | `vb-missing-text` |
| P | the start not on the page | `Date of birth:` … `Place of birth:`: nothing | `<p>Place of birth: Paris</p>` | fail: `start 'Date of birth:' not found whole, at a word edge` | `vb-no-start` |
| P | the end not on the page | `Date of birth:` … `Place of birth:`: nothing | `<p>Date of birth:</p>` | fail: `end 'Place of birth:' not found whole, at a word edge` | `vb-no-end` |
| P | the end only before the start | `Date of birth:` … `Place of birth:`: nothing | `<p>Place of birth: Paris</p><p>Date of birth:</p>` | fail: `no end 'Place of birth:' after start 'Date of birth:'` | `vb-end-first` |
| P | words glued together: a space is text | `Abstract` … `Introduction`: `We study parsing.` | `<p>Abstract WeStudyParsing. Introduction</p>` | fail | `vb-glued` |
| P | a word split in two | page start … page end: `Please sign into the portal` | `Please sign in to the portal` | fail: `the page holds 'please sign in to the portal' where the gold has 'please sign into the portal' (1 edit, max_diffs 0)` | `vb-split-word` |
| P | a hyphen inside a word dropped (`re-sign` is not `resign`) | page start … page end: `re-sign the lease` | `resign the lease` | fail: `the page holds 'resign the lease' where the gold has 're-sign the lease' (1 edit, max_diffs 0)` | `vb-hyphen-dropped` |
| P | an underscore inside a name dropped | page start … page end: `set max_rows` | `set maxrows` | fail | `vb-underscore` |
| P | a hyphen a line broke after, read as a space | page start … page end: `A self aware system` | `A self-<br>aware system` | fail: `the page holds 'a self-aware system' where the gold has 'a self aware system' (1 edit, max_diffs 0)` | `vb-hyphen-space` |
| P | a sign changed, within the budget | page start … page end: `Net -12.5` (md 2) | `Net +12.5` | fail: `the page holds 'net +12.5' where the gold has 'net -12.5' (a number differs)` | `vb-sign` |
| P | an exponent's sign changed, within the budget | page start … page end: `Concentration 1e-3 M` (md 1) | `Concentration 1e+3 M` | fail: `the page holds 'concentration 1e+3 m' where the gold has 'concentration 1e-3 m' (a number differs)` | `vb-exponent` |
| P | a number in scientific notation split, within the budget | page start … page end: `Rate 1e3 per s` (md 1) | `Rate 1 3 per s` | fail: `the page holds 'rate 1 3 per s' where the gold has 'rate 1e3 per s' (a number differs)` | `vb-exponent-split` |
| P | a sign before a currency symbol dropped, within the budget | page start … page end: `Gain -$1,234` (md 1) | `Gain $1,234` | fail: `the page holds 'gain $1,234' where the gold has 'gain -$1,234' (a number differs)` | `vb-sign-currency` |
| P | a sign after a CJK character dropped, within the budget | page start … page end: `温度-3` (md 1) | `温度 3` | fail: `the page holds '温度 3' where the gold has '温度-3' (a number differs)` | `vb-cjk-sign` |
| P | an underscore run at the end of a name dropped | page start … page end: `set token____` | `set token` | fail: `the page holds 'set token' where the gold has 'set token____' (4 edits, max_diffs 0)` | `vb-underscore-run` |
| P | a decimal point written as a comma, within the budget | page start … page end: `Rate 1.25` (md 2) | `Rate 1,25` | fail | `vb-decimal` |
| P | the start inside a longer label opens a region too: a start must be unique on the page | `Date of birth:` … `Place of birth:`: nothing | `<p>Date of birth:</p><p>Place of birth: Paris</p><p>Mother's Date of birth: 1960</p><p>Mother's Place of birth: Rome</p>` | fail: `copy 2 of 2: between 'Date of birth:' and 'Place of birth:' holds "1960 mother's" where the gold has nothing (13 edits, max_diffs 0)` | `vb-longer-label` |
| P | a footnote marker the content does not hold | `Abstract` … `Introduction`: `We study parsing.` | `<p>Abstract</p><p>We study parsing.<sup>1</sup></p><p>Introduction</p>` | fail | `vb-footnote` |
| P | no anchors: a line added to the page | page start … page end: `Page intentionally left blank` | `<p>Page intentionally left blank</p><p>This page is empty.</p>` | fail: `the page holds 'page intentionally left blank this page is empty.' where the gold has 'page intentionally left blank' (20 edits, max_diffs 0)` | `vb-whole-page-extra` |
<!-- /cases -->

## Building a verbatim test

- **The gold must be exact by construction.** The content is everything a reader sees between the anchors: a
  born-digital text layer, a JATS table and the paragraph after it, an authored or rendered page, or a human
  review of the region. A guessed region fails faithful outputs.
- **Each anchor must have exactly one copy in the page's text**, found as the scorer finds it: at a word edge,
  inside longer labels too (`Date of birth:` has a copy in `Mother's Date of birth:`, case vb-longer-label), and
  in page furniture (a running header, a footer). `runners.verbatim_anchor_copies(page_text, anchor)` counts them on
  the page's full text; author a region only where it returns 1 for each anchor. An anchor holds no hyphen
  after a letter (the loader refuses one, see Anchors): pick `Self` … or the line before. Pick anchors inside one column
  or block, so that reading order cannot put other text between them.
- **Author regions only where no figure is.** An image's description is not read (as in `page_near_empty`), so
  text a system writes as an `alt` is lost to the region, though `present` credits it (cases vb-alt-present,
  vb-alt-region). A region whose page prints a figure, a chart or a stamp between its anchors is not authored.
- **Keep page furniture out of the region**, or include its text in the content: a running header or a page
  number between the anchors is content.
- **A footnote marker in the region is content.** A system that writes it as `<sup>1</sup>` writes a `1`; one
  that drops it loses a number (case vb-footnote). Choose a region without markers, or put the markers in the
  content.
- **A header-row table** (labels in one row, values in the next) reads every label before any value, so a field
  there is not a region; use `table_cell` with `{"empty": true}` (case vb-header-row).
- **A value written before its label** is outside the label's region (case vb-before-start). To guard it, open
  the region at the field before: `start` the previous field's label, `content` its value and this label.

## Blind spots

- **Image descriptions are not read**, as in `page_near_empty` and `blank_after`: invented text in an `alt` inside
  the region passes (case vb-alt).
- **Text outside the region is not read**, before its start or after its end (cases vb-before-start,
  vb-header-row).
- **A budget is spent on anything.** With `max_diffs` 2, two invented letters pass, though never a changed or
  added number (cases vb-budget-letters, vb-number-in-budget). With `max_diffs` 0, nothing passes that changes
  the text. A sign is never spent, but at a budget of 1 a hyphen after a letter or a digit may turn into
  another mark (`Δ-12` read `Δ+12`, `1-2` read `1/2`): such a hyphen is no sign (Numbers, above).
- **A percent sign, a range's mark, an operator and a list comma's space are text**, as every test reads
  numbers: at a budget of 1, `5%` read `5‰` or `5`, `10-12` read `10+12`, `1 +2` read `1 2` and `7,2016`
  read `7, 2016` pass (cases vb-percent, vb-percent-dropped, vb-range-plus, vb-operator-dropped,
  vb-list-comma).
- **A percent sign, a range's mark, an operator and a list comma's space are text**, as every test reads
  numbers: at a budget of 1, `5%` read `5‰` or `5`, `10-12` read `10+12`, `1 +2` read `1 2` and `7,2016`
  read `7, 2016` pass (cases vb-percent, vb-percent-dropped, vb-range-plus, vb-operator-dropped,
  vb-list-comma).
- **A percent sign, a range's mark, an operator and a list comma's space are text**, as every test reads
  numbers: at a budget of 1, `5%` read `5‰` or `5`, `10-12` read `10+12`, `1 +2` read `1 2` and `7,2016`
  read `7, 2016` pass (cases vb-percent, vb-percent-dropped, vb-range-plus, vb-operator-dropped,
  vb-list-comma).
- **A percent sign, a range's mark, an operator and a list comma's space are text**, as every test reads
  numbers: at a budget of 1, `5%` read `5‰` or `5`, `10-12` read `10+12`, `1 +2` read `1 2` and `7,2016`
  read `7, 2016` pass (cases vb-percent, vb-percent-dropped, vb-range-plus, vb-operator-dropped,
  vb-list-comma).
- **A percent sign, a range's mark, an operator and a list comma's space are text**, as every test reads
  numbers: at a budget of 1, `5%` read `5‰` or `5`, `10-12` read `10+12`, `1 +2` read `1 2` and `7,2016`
  read `7, 2016` pass (cases vb-percent, vb-percent-dropped, vb-range-plus, vb-operator-dropped,
  vb-list-comma).

The why reads `<where> holds <output> where the gold has <content> (<n> edit(s), max_diffs <k>)`, or
`(a number differs)`; `<where>` is `between <start> and <end>`, `after <start> to the page end`, `from the page
start to <end>` or `the page`, and `copy <i> of <n>: ` comes first when `start` has several copies. A missing
anchor reads `start <text> not found whole, at a word edge`, `end <text> not found whole, at a word edge` or
`no end <end> after start <start>`.

## On the chain (switch `region`, off by default)

With `region` on, the region is read on the normalizer chain (`chain.md`) instead of by the folded-string search above:

- an anchor is a copy of its text at Words, at token edges, budget 0 (a space of the gold is free, so `Date of birth:` also finds `Dateofbirth:`; a wrapped hyphen of the page is free);
- each copy of `start` pairs with the first copy of `end` after it; if `start` opens again before that end, the first copy is not closed and fails (there is no nesting). A missing `end` fails; with no `end` in the test the region runs to the page end;
- the region equals `content` as a whole at Text, within `max_diffs`: case is kept, a number is one atomic symbol (`10kg` is never `10mg`, `1,5` is never `1.5`), and a region may run across table cells;
- still not compared (a parameter of the region relation, applied to both sides, each behind its own switch, `region_underscore` and `region_bullet`): a run of one or two underscores that touches no word or number (three or more is a leader, which the Text fold removes before the region is read, so `text_fold` decides it), and a bullet glyph before a space;
- a footnote mark is a kept `Mark` at Text and equals only a `Mark`, never a number or a letter: a gold cannot write the digit of a `<sup>` footnote, so a region holding one fails (`parsing.1` and `parsing. 1` both fail on `parsing.<sup>1</sup>`). A gold written with brackets (`[1]`) is a mark and matches a bracketed one.

Differences from the reading above, all behind the switch: case is kept; a long underscore run touching a letter folds to a space with the rest of the Text fold; a leading-dot number (`.5`) is a symbol and a number, so a budget can drop its dot; `selfaware` and `self aware` are both found by a gold anchor through the free space; `NUL` is dropped by the Text fold. Failures start with the same `between ... and ... holds ... where the gold has ...` text, without the edit count.
