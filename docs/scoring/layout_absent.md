# `layout_absent`

**Asks:** no layout block on the page has one of these labels. Family layout; reads `blocks`. It is the layout
test for a page that holds nothing a reader would mark up: a blank page, a plate's blank back, a page with only
a folio or a stain, where a system that invents a heading, a table or an equation is wrong. The published
dataset holds no tests of this type yet.

```json
{"test_type": "layout_absent", "output_type": "blocks", "derivation": "model_panel", "tags": [],
 "args": {},
 "settings": {"kinds": ["heading", "table", "caption", "equation", "footnote", "list", "code"]}}
```

- No args and no `place`: the test reads the whole page.
- `kinds`: the labels no block may carry, a non-empty list of distinct labels of `views.LABELS`. The loader
  refuses `text`: text on a page is `page_near_empty`'s to judge, and to `layout_kind` a `list` or `form` block
  is text too, so a ban on text would have to say whether it bans those.

**The rule.** The test fails when any block of the output, anywhere and of any size, carries a label in `kinds`,
and passes otherwise. Labels are compared as written: the rule of `layout_kind` that a `list` or `form` block
passes a `text` test is not applied, so a `list` block fails a test that forbids `list` (case la-list). A block's
text and box are never read, beyond naming the block in the why. An empty block list passes (case la-none).

**The set for blank pages** forbids `heading`, `table`, `caption`, `equation`, `footnote`, `list` and `code`,
and allows `text`, `figure`, `page_furniture` and `form`. A blank page's folio or running head is page
furniture, a stain, a stamp or a plate is a figure, and ruled lines a system reads as a form to fill in are a
form (cases la-folio, la-figure, la-form). Page furniture is allowed because a folio on a blank page is
printed: a system that marks it as furniture reads the page right.

**Without blocks.** A system that returns no `blocks` output fails every layout test with `no blocks output`,
this one included (layout_kind.md), so it scores 0 on the layout family. A page is asked for the output types
its tests read (`tests.wants`): a page with a `layout_absent` test is asked for `blocks`.

## Rules

What the test ignores:

<!-- cases:layout-absent-ignored -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| I | no blocks at all: a blank page read as blank | none of the blank-page set | no blocks | pass | `la-none` |
| I | a page number as page furniture | none of the blank-page set | `page_furniture [0.4, 0.02, 0.6, 0.05] '7'` | pass | `la-folio` |
| I | a text block (`page_near_empty` reads text) | none of the blank-page set | `text [0.2, 0.4, 0.8, 0.5] 'a synthetic note'` | pass | `la-text` |
| I | a figure (a stain, a stamp, a plate) | none of the blank-page set | `figure [0, 0, 1, 1] ''` | pass | `la-figure` |
| I | ruled lines read as a form | none of the blank-page set | `form [0, 0, 1, 1] ''` | pass | `la-form` |
| I | a heading, when the test forbids only tables | no `table` | `heading [0.2, 0.4, 0.8, 0.5] 'SAMPLE HEADING'` | pass | `la-other-kinds` |
<!-- /cases -->

What it does not look at, so a wrong output passes:

<!-- cases:layout-absent-blind -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| B | a heading labeled text | none of the blank-page set | `text [0.2, 0.4, 0.8, 0.5] 'SAMPLE TITLE'` | pass | `la-heading-as-text` |
| B | the text of an allowed block is not read | none of the blank-page set | `page_furniture [0.4, 0.02, 0.6, 0.05] 'An invented sentence'` | pass | `la-text-unread` |
<!-- /cases -->

What it penalizes:

<!-- cases:layout-absent-penalized -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| P | a heading block | none of the blank-page set | `heading [0.2, 0.4, 0.8, 0.5] 'SAMPLE HEADING'` | fail: `a heading block at [0.20, 0.40, 0.80, 0.50]: 'SAMPLE HEADING'` | `la-heading` |
| P | an empty table | none of the blank-page set | `table [0.2, 0.4, 0.8, 0.5] ''` | fail: `a table block at [0.20, 0.40, 0.80, 0.50]: ''` | `la-table` |
| P | a list block (labels are compared as written: a list is not text here) | none of the blank-page set | `list [0.2, 0.4, 0.8, 0.5] '- item'` | fail | `la-list` |
| P | several forbidden blocks: the first is named | none of the blank-page set | `text [0.4, 0.02, 0.6, 0.05] '7'; caption [0.2, 0.4, 0.8, 0.5] 'Fig. 1'; equation [0.2, 0.4, 0.8, 0.5] 'x'` | fail: `a caption block at [0.20, 0.40, 0.80, 0.50]: 'Fig. 1' (and 1 more)` | `la-many` |
| P | a forbidden block however small | none of the blank-page set | `code [0.5, 0.5, 0.51, 0.51] ''` | fail | `la-tiny` |
<!-- /cases -->

## Building a test

- **Use it only where the page holds no block of the forbidden kinds**, as a person reviewing the page sees it:
  a title page or a plate carries a heading, so it is no blank page for this test. Leave out pages a model panel
  calls blank without review.
- **The label is the contract.** The test reads labels only, so author it only where every mark on the page has
  one label a system can be held to: leave out a page whose mark a reader could call a heading as well as page
  furniture (a large centered folio, a running title in capitals) or a caption as well as a figure (a stamp with
  a line of text). A faithful system that labels such a mark `heading` would fail.
- **Pair it with `page_near_empty`** for the text on the page: this test allows text blocks.

## Blind spots

- **A forbidden block labeled as an allowed one passes** (case la-heading-as-text): the test trusts the label.
- **The text of an allowed block is not read** (case la-text-unread): an invented sentence in a text or furniture
  block is `page_near_empty`'s to fail.

The why reads `a <label> block at [x0, y0, x1, y1]: <text>`, the text cut at 60 characters, then `(and <n> more)`
when more blocks are forbidden.
