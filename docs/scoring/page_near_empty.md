# `page_near_empty`

**Asks:** a page that holds nothing a reader would transcribe yields at most N non-space characters. Family
text; reads `html`. It is the test for a model that invents text on a blank page. The published dataset holds
no tests of this type yet.

The test counts every character of the text view that is not white space, without image descriptions, and passes
when the count is at most `max_chars` (0 or more, set per test). Invisible format characters (a zero-width
space, a byte-order mark, a soft hyphen) are not counted, and nor are the marks the text view writes for an element
that holds nothing: an empty `<math>`, an empty list item and a hidden input (cases ne-invisible, ne-empty-math,
ne-empty-item, ne-hidden-input). A list item with text keeps its number, as it does everywhere in the text view
(case ne-item-number). It has no gold text, no args and no edit budget.
It does not fold: case, punctuation and symbols all count.

## Rules

<!-- cases:near-empty-rules -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| I | a page with no text | at most 0 | `""` | pass | `ne-blank` |
| I | spaces and line breaks are not counted | at most 0 | `<p> </p><p>\n</p><br>` | pass | `ne-spaces` |
| I | an image description is not counted | at most 0 | `<p></p><img alt='stamp'>` | pass | `ne-alt` |
| I | a page number within the limit | at most 2 | `<p>12</p>` | pass | `ne-folio` |
| I | spaces inside the text do not count | at most 2 | `<p>1 2</p>` | pass | `ne-spacing` |
| B | an image is not read, however much it shows | at most 0 | `<img src='scan.png'>` | pass | `ne-image-only` |
| P | one character over the limit | at most 2 | `<p>123</p>` | fail: `3 non-space characters (limit 2)` | `ne-one-over` |
| I | an invisible format character (a zero-width space, a byte-order mark, a soft hyphen) | at most 0 | `<p>​﻿­</p>` | pass | `ne-invisible` |
| I | an empty math element | at most 0 | `<math></math>` | pass | `ne-empty-math` |
| I | an empty list item | at most 0 | `<ol><li></li></ol>` | pass | `ne-empty-item` |
| I | a hidden input | at most 0 | `<input type=hidden value=v>` | pass | `ne-hidden-input` |
| P | a list item is text, with its number | at most 0 | `<ol><li>x</li></ol>` | fail: `3 non-space characters (limit 0)` | `ne-item-number` |
| P | a transcribed line | at most 0 | `Total due` | fail: `8 non-space characters (limit 0)` | `ne-text` |
| P | text in a table cell | at most 0 | `<table><tr><td>5</td></tr></table>` | fail: `1 non-space characters (limit 0)` | `ne-cell` |
<!-- /cases -->

## Blind spots

- **It counts characters, not meaning.** A page number within the limit passes, and so does any other mark of the
  same size (case ne-folio). The limit is the only judgement in the test.
- **Images are not read.** A page holding only an image has no text, however much the image shows (case
  ne-image-only).
- **Image descriptions never count**, so a model cannot fail by describing a stamp (case ne-alt).

The why reads `N non-space characters (limit M)`.
