# `layout_kind`

**Asks:** the layout block that holds this line's place has this label. 2,403 tests; family layout; reads
`blocks`. The dataset's labels are `text`, `table` and `heading`; the code accepts the 11 labels of
`views.LABELS`.

A system's `blocks` are boxes with a label (`[x0, y0, x1, y1]`, fractions of the page, origin top left). The test
has a *place*: one box per printed line. A block **covers** the place when it overlaps at least half of the
place's area. The **holder** is the smallest covering block (on equal areas, the first listed; areas that differ
within a relative 1e-9 of each other, which covers float rounding, are equal). The test passes when the holder has the gold label; for `text`,
a `list` or `form` block passes too. The line's text is never compared.

## Rules

In every case the place is `[0.2, 0.2, 0.6, 0.25]`, and the gold column holds the expected label.

<!-- cases:layout-rules -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| I | a block on the line, right label | `text` | `text [0.2, 0.2, 0.6, 0.25]` | pass | `lay-match` |
| I | a list or form block passes a text test | `text` | `list [0.2, 0.2, 0.6, 0.25]` | pass | `lay-list-is-text` |
| I | the smallest block that covers half wins | `heading` | `text [0, 0, 1, 1]; heading [0.2, 0.2, 0.6, 0.25]` | pass | `lay-smallest` |
| I | a block covering half the place | `text` | `text [0.4, 0.2, 0.6, 0.25]; heading [0.2, 0.2, 0.4, 0.25]` | pass | `lay-half` |
| B | one block over the whole page | `table` | `table [0, 0, 1, 1]` | pass | `lay-page-block` |
| B | the block's text is not read | `text` | `text [0.2, 0.2, 0.6, 0.25]` | pass | `lay-text-unread` |
| B | equal areas: the first listed wins | `heading` | `heading [0.2, 0.2, 0.6, 0.25]; text [0.2, 0.2, 0.6, 0.25]` | pass | `lay-tie` |
| B | equal areas, other shapes: the first listed still wins | `heading` | `heading [0.2, 0.15, 0.4, 0.25]; text [0.2, 0.2, 0.6, 0.25]` | pass | `lay-tie-shapes` |
| P | another label | `text` | `caption [0.2, 0.2, 0.6, 0.25]` | fail: `its block is labelled 'caption', not 'text': ''` | `lay-wrong-label` |
| P | a list block for a heading | `heading` | `list [0.2, 0.2, 0.6, 0.25]` | fail | `lay-heading-list` |
| P | a smaller block with another label inside | `text` | `text [0, 0, 1, 1]; heading [0.2, 0.2, 0.6, 0.25]` | fail | `lay-small-wrong` |
| P | a block covering 40% of the place | `text` | `text [0.2, 0.2, 0.36, 0.25]` | fail: `no block covers 50% of its place` | `lay-too-little` |
| P | no blocks | `text` | no blocks | fail: `no block covers 50% of its place` | `lay-none` |
<!-- /cases -->

## Blind spots

- **One big block passes by default.** A page-sized block labelled `table` passes every `table` test on the page
  (case lay-page-block); smaller blocks inside it take over.
- **The text is not read.** A block with the right box and label passes whatever its text (case lay-text-unread).
- **Ties go to list order.** Two blocks of equal area: the first listed is the holder, whatever their shapes
  (cases lay-tie, lay-tie-shapes).
- **Labels are the provider's mapping.** [providers.md](../providers.md) maps each provider's block types to
  these labels; the test cannot tell a wrong mapping from a wrong detection.

A system that returns no `blocks` fails every layout test with `no blocks output`; an empty list fails each with
`no block covers 50% of its place`.
