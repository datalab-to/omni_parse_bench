# The claim contract

Every test type is a row of one table, `omni_parse_bench/scorers/unit_tests/schema.py`. The loader reads a test's
roles from it, the runner reads the gate on an empty output from it, and this page's table is rendered from it
(a test fails when they differ). A missing output (`html` or `blocks` absent or null) fails every row.

- **Quantifiers.** `exists`: some witness. `not_exists`: no witness. `unique`: the selection has one element.
  `all`: at least one anchor, and each has a witness. `count`: the selection's size is in the declared range.
  `locator_and_not_exists`: the locator has a witness and the claim has none. A selection is read left to right,
  keeping the leftmost candidate and, among those starting there, the longest, and dropping overlaps
  (`quantifiers.select`).
- **Gate on an empty output** (an output supplied but holding nothing a reader sees): `fail` fails it; `blank`
  (a bare negative test) passes it only on a page whose gold holds a `page_near_empty` test; `count` lets the
  statistic decide (`repeat` fails it, `page_near_empty` passes it).
- **Point.** The point of the normalizer chain a claim is read at (`chain.md`); locators read Words with
  budget 0.

<!-- schema -->
| row | reads | projection | point | relation | quantifier | budget | gate on an empty output |
|---|---|---|---|---|---|---|---|
| present | html | flat | Words (Cased with exact_case) | match_k(content) | exists | content | fail |
| present.number | html | flat | Words | match_0(one Qty) | exists | 0 | fail |
| present.latex | html | math, then flat with math as symbols | off chain (KaTeX) | contiguous symbol sequence at symbol edges | exists | 0 | fail |
| present.absent | html | flat | Words | match_k(content) | not_exists | at most a quarter of the content | blank |
| present.blank_field | html | flat + grid | Text | anchors = copies of the label; region(label to next stop) eq_0 empty or printed | all | 0 | fail |
| order | html | flat | Words | (w_b, w_a), w_b before w_a, each match at its own budget | exists | before, after | fail |
| repeat | html | flat | Words | match_0(content); selection | count | 0 | count |
| page_near_empty | html | flat | Id | visible characters | count | - | count |
| verbatim | html | flat | Text | anchors = copies of start; region(start to its paired end) eq_k content | all | content | fail |
| no_excess_repeats | html | flat minus math | Words | 16-word runs repeated over their gold count; spaced scripts only | not_exists | 0 | blank |
| table_cell | html | grid | Words | anchor line eq_k cell; every role has a witness line | exists | one, shared by the cell and its roles | fail |
| table_cell.shape | html | grid | Words | as table_cell, plus a blank side (`empty`) or no text beyond (`end`) for each anchor | all | one, shared by the cell and its roles | fail |
| layout_kind | blocks | blocks | off chain (label order) | the holder of place has label <= expected | unique | - | fail |
| layout_absent | blocks | blocks | off chain (label order) | a block whose label <= a forbidden kind | not_exists | - | blank |
| format | html | marks | Words | context match; the span carries the marks; no spill | exists | 0 | fail |
| format.absent | html | marks | Words | context match (locator); the span carries a forbidden mark (claim) | locator_and_not_exists | 0 | fail |

## The rules this step adds

Each is a named switch, off by default (`switches.py`); the table above is read with them off or on.

- `chain` (also `order`): an `order` test is two claims on the chain at Words, each at the test's budget, and passes when some copy of `before` ends before some copy of `after` begins. A pass that needs a copy other than the first of either is reported as `[copy] ordered by a copy other than the first`. A failure names the claim that is missing, `[order]` when both are found but not in order, or the chain rules whose switching off alone would pass it.
- `label_order`: `layout_absent` reads the label order: a block whose label is at most a forbidden kind counts. Only `list` and `form` are at most `text`; `caption`, `footnote` and every other label are kinds of their own. `layout_kind` already reads it as `AS_TEXT`.
- `region`: `verbatim` reads its region on the chain (`verbatim.md`, "On the chain"); `region_underscore` and `region_bullet` switch the two things the region leaves out of both sides (a printed underscore line, a bullet glyph before a space), provisionally, so the flip table measures each.
- A footnote mark is a kept `Mark` that equals only a `Mark`, in every type and point: gold `Smith 1` fails on `Smith<sup>1</sup>`, gold `Smith` passes it at Cased and Words where marks are free.
- The loader lints `order` tests (`tests.order_lint`): `before` and `after` the same text or one inside the other, which it warns of (it does not refuse). The check that either text is found more than once in the page's reference text (the transcription the test was written from) is implemented (`check(pages, references=...)`) but not run by default: a dataset ships no transcription today.
- Per-claim budgets: an `order` test keeps the budget of `before` and of `after` separately (`runners.Order.budgets`), on the chain and on the old reading alike.

## Blank fields and the format locator (step 4)

- `region_blank`: a blank field's label outside a table cell is read on the region relation: each copy of the label (at Words, in one cell or paragraph, not inside a longer stop) opens a region to the next stop or the next copy of the label, blank when it holds only white space and placeholder symbols (`_ . · …`), once the printed mask (if the test has one) is taken out once; what comes before the label in its block must be blank or another label or stop. A label in a table cell keeps the grid reading (`present-text.md`, "Blank fields"), and a page with a table the cell reader cannot parse keeps the old reading throughout.
- `format_locator`: a negative `format` test is a locator and a claim (`locator_and_not_exists`): the context must be found, and no occurrence carries a forbidden mark. An output with no marks at all passes it when the context is there; before, it failed.
