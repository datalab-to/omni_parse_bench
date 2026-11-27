# Scoring reference

These pages say what each test of the benchmark checks: what it ignores, what it penalizes, and what it cannot
see. [design.md](../design.md) says why the tests are built this way. Every rule shown in a table here is a small
case that is run against the scorer in CI (see [Keeping the pages true](#keeping-the-pages-true)).

## How a score is built

1. **A test passes or fails.** Nothing is partial and nothing is weighted. A test that fails has a short reason
   (its *why*), kept with the run's results in `unit_tests/details/<page_id>.jsonl` ([API.md](../API.md)).
2. **A family score is the share of its tests that pass.** Text, tables and layout are headline families; format is an auxiliary family.
3. **The headline is the plain mean of the headline family scores.** Each family weighs a third, however many tests it
   has. A run over part of the dataset averages the headline families it holds; when it holds none, it
   averages its available families, preserving the format-only fallback.

| test type | asks | family | tests in the dataset | page |
|---|---|---|---:|---|
| `present`, text arg | this string is on the page | text | 3,684 | [present-text.md](present-text.md) |
| `present`, number arg | this number is on the page | text | 323 | [present-number.md](present-number.md) |
| `present`, latex arg | this equation is in the page's math | text | 3,268 | [present-latex.md](present-latex.md) |
| `order` | this string comes before that one | text | 1,189 | [order.md](order.md) |
| `repeat` | this line appears exactly N times | text | 35 | [repeat.md](repeat.md) |
| `page_near_empty` | a blank page holds at most N characters | text | 0 | [page_near_empty.md](page_near_empty.md) |
| `verbatim` | the text between two anchors is this, verbatim within the test's edit budget | text | 0 | [verbatim.md](verbatim.md) |
| `no_excess_repeats` | no passage is repeated more often than the page prints its words | text | 0 | [no_excess_repeats.md](no_excess_repeats.md) |
| `present`, `{"absent": true}` | a reading the page does not print is not in the output | text | 0 | [present-absent.md](present-absent.md) |
| `table_cell` | a table has this cell, with these neighbours and headings | tables | 5,386 | [table_cell.md](table_cell.md) |
| `layout_kind` | the layout block on this line has this label | layout | 2,403 | [layout_kind.md](layout_kind.md) |
| `layout_absent` | no layout block on the page has one of these labels | layout | 0 | [layout_absent.md](layout_absent.md) |

Counts are of the published dataset: 16,288 tests on 2,937 pages. The first ten rows read the page's `html`
output; `layout_kind` and `layout_absent` read its `blocks`.

<!-- cases:readme-scoring -->
| rule | input | reads as | case |
|---|---|---|---|
| the headline is the mean of the family scores | text 3 of 4 passed, tables 0 of 1, layout 1 of 1 | `headline 0.58 (text 0.75, tables 0.00, layout 1.00)` | `score-headline` |
| a run without a family averages the families it has | text 1 of 2 passed, layout 1 of 1 | `headline 0.75 (text 0.50, layout 1.00)` | `score-subset` |
| an output the system did not give fails the tests that read it | html only, for a text, a table and a layout test | `pass; fail: no tables found; fail: no blocks output` | `score-missing-output` |
| an output of the wrong shape fails the tests that read it | html that is not a string, no blocks | `fail: malformed html output; fail: malformed html output; fail: no blocks output` | `score-malformed` |
| a failed page (refused, crashed, wrong shape) fails every test | the same three tests | `fail: no html output; fail: no html output; fail: no blocks output` | `score-failed-page` |
<!-- /cases -->

What this means for a reader of scores:

- **A test type's weight follows its count inside its family.** The text family has 8,499 tests, of which 3,268
  are equations, so equations are about 38% of the text score and about 12.8% of the headline.
- **The headline is not the share of all tests passed.** A system that passes only the layout tests has a
  headline of 33.3% but passes 14.8% of the tests. One that passes only the equation tests has a headline of 12.8%
  and passes 20.1% of the tests.
- **A missing output costs only the tests that read it.** A system with no layout output scores 0 on layout,
  which is a third of the headline.
- **A failed page costs its tests, nothing more.** A page the system refused or could not answer, or answered in
  the wrong shape, counts with every test failed.
- **Tests of one document are graded on their own but often fail together** (one misread table fails many cells).
  The summary counts `documents` next to `tests`; a score over few documents says less than its test count.

## Two words used everywhere

- **fold**: before any text comparison, the gold string and the output text are both put in one plain form:
  lowercase (case kept for an arg with `exact_case`), spacing collapsed, look-alike characters (dashes, quotes, ligatures, full-width digits) made one,
  math read as text, leaders and footnote brackets removed. Diacritics, punctuation and digits are kept. The full
  list is in [internals.md](internals.md#fold).
- **squeeze**: fold, then remove every space. A text test that fails tries once more on the squeezed strings, so
  `TotalDue` matches `Total Due`.

## How to read the tables

Each row is one case: a gold (what the test asks for), an output (the html a system returned), and the verdict
the scorer gives. An output written without tags is run as `<p>output</p>`. `md` is `max_diffs`, the number of
character edits a text test allows. The first column says what the row shows:

- **I** (ignored): the output is right, and the difference from the gold does not change the verdict.
- **B** (blind): the output is wrong, but the test does not look at the difference, so it passes.
- **P** (penalized): the difference makes the test fail.

The last column names the case. The same name appears in [observed.txt](../../tests/scoring_probes/observed.txt)
and in the case files under [tests/scoring_probes](../../tests/scoring_probes/).

## What the tests cannot see

| blind spot | example | test types | shown by |
|---|---|---|---|
| where on the page the string is | `42` is found in `Page 42 of 100` | `present`, `repeat` | (case num-context) |
| word edges | `Total` is found in `Totally` | `present`, `order` | (cases text-longer-word, ord-glued) |
| image descriptions | `Total` is found in `<img alt='Total'>` | `present`, `order` | (cases text-alt, ord-alt) |
| styling | struck-through text still counts; bold and italic are dropped | every html test but `format` | (case text-strike) |
| table structure, outside `table_cell` | two adjacent cells read as one string | `present`, `order` | (case text-table-flat) |
| the slack of an edit budget | with 1 edit, `ab` is found in `a` | `present`, `table_cell` | (cases text-short-fuzzy, cell-insertions) |
| letters around an equation | `xy` is found in `$wxy$` | `present` (latex) | (case tex-letter-beside) |
| unknown LaTeX commands | `x+y` is found in `$x+\foo y$` | `present` (latex) | (case tex-unknown-macro) |
| a second copy elsewhere | `Alpha` before `Beta` passes on `Beta Alpha Beta` | `order` | (case ord-any-pair) |
| word edges, for a mark | `total` is bold in `<b>subtotal</b>` | `format` | (case fm-word-edge) |
| a marked copy elsewhere | a bold test passes on a page with one plain and one bold copy of its phrase | `format` | (case fm-a-copy) |
| the text of a layout block | a block with the right label and box passes, whatever its text | `layout_kind` | (case lay-text-unread) |
| one block for the whole page | a page-sized `table` block passes every `table` test | `layout_kind` | (case lay-page-block) |
| extra content | a loop that repeats the string passes; only `repeat` caps a count, `verbatim` a closed stretch and `no_excess_repeats` a page's repeats | all but `repeat`, `verbatim` and `no_excess_repeats` | (case text-loop) |

## Empty output

A test that only says what the output must not hold (`present` with `{"absent": true}`, `no_excess_repeats`,
`layout_absent`) fails an output with nothing in it: html with no character a reader sees outside image
descriptions (as `page_near_empty` counts), or no block at all. It is a floor, not a guard: one stray character, or
one block with no text, is an output, and passes. A page that carries a `layout_absent` test must also carry a
`page_near_empty` test (the loader refuses one that does not), so that its honest empty answer is not failed. Every other test
type needs its text, cell, anchor or label and already fails an empty output. The exception is a blank page: when
the page's gold holds a `page_near_empty` test, an empty output is the right answer and passes these three. So an
empty output, on a page that is not blank, passes no test but `page_near_empty` (and a `verbatim` test with no anchor and no content, which asks
the page to be blank). Each type's page gives its cases.

## Pages

- [present-text.md](present-text.md), [present-number.md](present-number.md),
  [present-latex.md](present-latex.md), [order.md](order.md), [repeat.md](repeat.md),
  [page_near_empty.md](page_near_empty.md), [verbatim.md](verbatim.md), [no_excess_repeats.md](no_excess_repeats.md),
  [present-absent.md](present-absent.md), [format.md](format.md),
  [table_cell.md](table_cell.md), [layout_kind.md](layout_kind.md), [layout_absent.md](layout_absent.md): one page per test, each with the same shape:
  what it asks, its rules table, its blind spots.
- [internals.md](internals.md): how an output becomes the text the tests compare: markdown to html, the text
  view, the fold steps, the dollar reader, the edit budget, the hyphen rule, and what a gold must be to load.
- [schema.md](schema.md): the claim contract, one row per test type, its quantifier and gate on an empty output; the order, region and label-order rules, each a switch.
- [chain.md](chain.md): the normalizer chain (Id, Text, Cased, Words), the one distance, and the rules that decide a text match, each a switch.
- [reader.md](reader.md): the reader behind the scorer's text views: what it drops (hidden text, alt text), cells, tokens, scripts and quantities, and the switches that turn each rule on or off.

## Keeping the pages true

The tables are written by `tests/scoring_probes/render.py` from the case files, and
`tests/test_scoring_reference.py` fails in CI when a case no longer gives what it claims, when the recorded
results change, when a page's tables were edited by hand, or when a page cites a case that does not exist. After
a deliberate scorer change, update the cases and the text around them, then run:

```
python tests/test_scoring_reference.py --regenerate
```

## Not covered

These pages do not show:

- how a run's `coverage` is computed (outside this repository);
- the full lists of arrow and space characters that fold treats as one, and of the html tags that end a line;
- whether a nested table's rows also count in the outer table, and that a table split over two `<table>`
  elements is two tables whose relations do not cross;
- how providers handle a rotated or cropped page for `layout_kind` places;
- which unit test pins which rule;
- counts by suite, by `max_diffs` and by table role.
