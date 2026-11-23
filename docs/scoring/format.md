# `format`

**Asks:** the output keeps the marks a page prints: the span of text is bold, italic, underlined, struck through,
superscript or subscript (or, in a negative test, none of the marks the test lists), and the words next to it
are not. Family `format`, reported beside the headline and excluded from it when any headline family is present; reads `html`. It is the only test type that
reads the output's markup: every other test reads the text view, which drops it (the styling row of the
[blind spots](README.md#what-the-tests-cannot-see)).

A test gives the text before the span, the span and the text after it (`before` and `after` are optional, but a
span under 3 letters or digits needs a context with one), `max_diffs` 0, and exactly one of two settings: `marks`,
the marks every letter or digit of the span must carry (a span is not both superscript and subscript), or
`absent`, the marks none of them may carry. There is no edit budget: the context (before, span and after, together)
is found as written, anywhere on the output, and a wrong, missing or added character in it means it is not found
(case fm-wrong-letter). Contexts are kept short, just enough to make the span unique on the page. The words are
compared as `marks.fold` leaves them: the character forms unified, case folded, and no white space (not the whole
[fold](internals.md): no footnote, hyphen, bullet or maths rule), so the span is read at its place in the context, and
a span whose letters repeat the end of the context before it is not mistaken for the letters before it (case
fm-repeat-at-edge).

Only letters and digits are looked at, in the span and around it. A positive test passes when every letter or digit of
the span carries every mark asked, and the letter or digit on each side of the span (the nearest, within the context)
carries none of them (cases fm-whole-paragraph, fm-neighbour, fm-far-neighbour): bolding the whole line fails the test
of one bold word, while a mark that takes in or stops before a comma is the same mark (cases fm-punct-inside,
fm-punct-outside). A negative test passes when no letter or digit of the span carries a listed mark, and fails when
the words are not on the page at all (case fm-neg-missing), or when no text of the output carries a mark: with none,
nothing shows the system could have written one, so a system that never writes marks gets no credit for not marking
(cases fm-neg-no-marks, fm-neg-empty-element: an empty `<b></b>` or an icon is not a mark on any text). That is how
`layout_kind` treats an output with no typed blocks: a test the output cannot show an answer to fails. When the
context occurs twice, a positive test passes if either place does, and a negative one only if neither carries the
mark (cases fm-a-copy, fm-neg-all-copies).

Format tests may share pages and suites with headline tests, so one prediction serves both. The summary reports their pass rate and document and test counts in `auxiliary.format`, overall and in `auxiliary.format.per_suite`; a suite score pools only its headline tests. A format test counts in its family and test type, and in none of the tag, arg kind and derivation
slices: those pool what the headline families measure, and a format test has no tag of its own.

## What a mark is

| mark | elements and styles |
|---|---|
| bold | `<b>`, `<strong>`, `font-weight` bold, bolder or 600 and over, the `font` shorthand |
| italic | `<i>`, `<em>`, `font-style` italic or oblique, the `font` shorthand |
| underline | `<u>`, `<ins>`, `text-decoration` underline |
| strike | `<s>`, `<strike>`, `<del>`, `text-decoration` line-through |
| sup, sub | `<sup>`, `<sub>`, `vertical-align` super or sub (the style replaces the other script) |

An element that is a mark by default is a mark, and a style sheet is not read: `<ins>` is underlined and `<del>` struck
through (cases fm-ins, fm-class). A style that draws the text plain (`font-weight: normal`, `font-style: normal`, a `font` shorthand
that names neither) takes bold or italic off (cases fm-style-cancelled, fm-font-resets); on an element's own mark,
`text-decoration: none` takes off its underline or strikethrough and `vertical-align: baseline` its script
(case fm-own-none), but neither takes off a mark an ancestor makes, as in a browser (cases fm-underline-none,
fm-baseline). An
end tag that crosses another mark leaves it on after it (cases fm-crossed, fm-crossed-goes-on), and what `views.html` hides is hidden here too: a comment, a doctype, and a script, style, head or title that an end tag closes, with everything
in it; one that is never closed hides nothing, so its text is read like any other (cases fm-closed-head, fm-unclosed-head,
fm-head-bare-text). Markdown is a vendor's output, and the harness turns it into html before any test
reads it, so `**x**` and `<strong>x</strong>` are the same marks (case fm-markdown); markdown markers written into an html
output are text, not marks (case fm-raw-markdown), and an html tag inside the markdown is read as html (case
fm-markdown-html). Markdown has no superscript or subscript and no single-tilde
strikethrough, so a markdown-only output cannot carry them. Not marks: a heading or a table heading (drawn bold),
`<mark>`, a link, a class, a Unicode superscript, mathematical bold letters, and LaTeX (cases fm-heading, fm-th,
fm-mark-element, fm-link, fm-class, fm-unicode-sup, fm-math-bold-letters, fm-latex-sup). Text inside `<math>` carries no
mark, and nothing in a script, a comment or the head is read (cases fm-in-math, fm-hidden); code is read like any
other text (case fm-in-code).

## Rules

<!-- cases:format-rules -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| I | the span in `<b>` | bold on `total`, context `the total due` | `the <b>total</b> due` | pass | `fm-bold` |
| I | `<strong>` is bold | bold on `total`, context `the total due` | `the <strong>total</strong> due` | pass | `fm-strong` |
| I | an inline style is bold | bold on `total`, context `the total due` | `the <span style="font-weight: 700">total</span> due` | pass | `fm-bold-style` |
| I | `<em>` is italic | italic on `total`, context `the total due` | `the <em>total</em> due` | pass | `fm-italic` |
| I | `<u>` is underlined | underline on `total`, context `the total due` | `the <u>total</u> due` | pass | `fm-underline` |
| I | `<del>` is struck through | strike on `total`, context `the total due` | `the <del>total</del> due` | pass | `fm-strike` |
| I | a superscript inside a word | sup on `2`, context `H2O` | `H<sup>2</sup>O` | pass | `fm-sup` |
| I | a subscript inside a word | sub on `2`, context `H2O` | `H<sub>2</sub>O` | pass | `fm-sub` |
| I | markdown bold, turned to html as the harness does | bold on `total`, context `the total due` | `the **total** due` | pass | `fm-markdown` |
| I | letter case | bold on `total`, context `the total due` | `THE <b>TOTAL</b> DUE` | pass | `fm-case` |
| I | white space, entities and no-break spaces | bold on `brown fox`, context `the quick brown fox due` | `the&nbsp;quick\n<b>brown&#32;fox</b> due` | pass | `fm-spacing` |
| I | curly quotes and dashes | italic on `isn't well-known`, context `it isn't well-known due` | `it <i>isn’t well–known</i> due` | pass | `fm-typography` |
| I | two marks, nested in either order | bold + italic on `total`, context `the total due` | `the <i><b>total</b></i> due` | pass | `fm-two-marks` |
| I | one mark written in adjacent runs | bold on `total amount`, context `the total amount due` | `the <b>total</b><b> amount</b> due` | pass | `fm-adjacent` |
| I | one mark written in a run per word | bold on `total amount`, context `the total amount due` | `the <b>total</b> <b>amount</b> due` | pass | `fm-spaced-runs` |
| I | a run that continues across a paragraph break | bold on `total amount`, context `the total amount due` | `<p>the <b>total</b></p><p><b>amount</b> due</p>` | pass | `fm-across-paragraphs` |
| I | a span whose letters repeat the end of the context before it | bold on `ggg`, context `xyzg ggg abc` | `xyzg <b>ggg</b> abc` | pass | `fm-repeat-at-edge` |
| P | one wrong character in the context: there is no edit budget | bold on `total`, context `the total due` | `thx <b>total</b> due` | fail: `the context is not in the output` | `fm-wrong-letter` |
| I | another mark on the span as well | bold on `total`, context `the total due` | `the <i><b>total</b></i> due` | pass | `fm-other-mark` |
| I | marked words elsewhere on the page | bold on `total`, context `the total due` | `<p><b>Invoice</b> 12</p><p>the <b>total</b> due</p><p><i>paid</i></p>` | pass | `fm-elsewhere` |
| I | a negative test on plain words, on a page that has a mark elsewhere | not bold on `total`, context `the total due` | `<p>the total due</p><p><b>note</b></p>` | pass | `fm-neg-plain` |
| I | a negative test for bold, the span italic | not bold on `total`, context `the total due` | `the <i>total</i> due` | pass | `fm-neg-other-mark` |
| P | the span is plain | bold on `total`, context `the total due` | `the total due` | fail: `the span lacks ['bold']` | `fm-no-mark` |
| P | italic where bold is asked | bold on `total`, context `the total due` | `the <i>total</i> due` | fail: `the span lacks ['bold']` | `fm-wrong-mark` |
| P | half the span marked | bold on `total amount`, context `the total amount due` | `the <b>total</b> amount due` | fail: `the span lacks ['bold']` | `fm-half` |
| P | the whole paragraph marked | bold on `total`, context `the total due` | `<p><b>the total due</b></p>` | fail: `['bold'] runs onto the text around the span` | `fm-whole-paragraph` |
| P | a neighbouring word marked too | bold on `total`, context `the total due` | `the <b>total due</b>` | fail: `['bold'] runs onto the text around the span` | `fm-neighbour` |
| P | a negative test on an output that has no mark anywhere: nothing shows it could have written one | not bold on `total`, context `the total due` | `the total due` | fail: `the output has no marks at all, so it cannot show that a mark is absent` | `fm-neg-no-marks` |
| I | `<ins>` is underlined | underline on `total`, context `the total due` | `the <ins>total</ins> due` | pass | `fm-ins` |
| I | the mark takes in the comma after the span | bold on `total`, context `the total, due` | `the <b>total,</b> due` | pass | `fm-punct-inside` |
| I | the mark stops before the comma after the span | bold on `total`, context `the total, due` | `the <b>total</b>, due` | pass | `fm-punct-outside` |
| I | a marked word two words away is not the span's neighbour | bold on `total`, context `the old total due` | `<b>the</b> old <b>total</b> due` | pass | `fm-far-neighbour` |
| I | an end tag that crosses another mark: the first word keeps what it closes | bold on `big`, context `the big total due` | `the <b><i>big</b> total</i> due` | pass | `fm-crossed` |
| I | an end tag that crosses another mark: the second goes on after it | italic on `total`, context `total` | `the <b><i>big</b> total</i> due` | pass | `fm-crossed-goes-on` |
| I | an unclosed head does not hide the body | bold on `total`, context `the total due` | `<html><head><title>t<body><p>the <b>total</b> due` | pass | `fm-unclosed-head` |
| I | the font shorthand | italic + bold on `total`, context `the total due` | `the <span style="font: italic bold 12px serif">total</span> due` | pass | `fm-font-shorthand` |
| I | a numeric font weight of 600 or more | bold on `total`, context `the total due` | `the <span style="font-weight:650">total</span> due` | pass | `fm-weight-650` |
| I | `text-decoration: none` on a span inside `<u>` does not take the inherited underline off, as in a browser | underline on `total`, context `the total due` | `the <u><span style="text-decoration:none">total</span></u> due` | pass | `fm-underline-none` |
| I | `vertical-align: baseline` does not take an inherited superscript off, as in a browser | sup on `2`, context `x2 + 1` | `x<sup><span style="vertical-align: baseline">2</span></sup> + 1` | pass | `fm-baseline` |
| P | a superscript element with a subscript style is a subscript | sup on `2`, context `H2O` | `H<sup style="vertical-align: sub">2</sup>O` | fail: `the span lacks ['sup']` | `fm-sup-style-sub` |
| P | a negative test where the only marks are on no text: empty elements do not count | not bold on `total`, context `the total due` | `<p>the total due</p><b></b><i class=fa></i>` | fail: `the output has no marks at all, so it cannot show that a mark is absent` | `fm-neg-empty-element` |
| I | `text-decoration: none` takes off the element's own underline | not underline on `total`, context `the total due` | `<p>the <u style="text-decoration: none">total</u> due</p><p><b>x</b></p>` | pass | `fm-own-none` |
| I | a `font` shorthand that names no weight draws the text plain | not bold on `total`, context `the total due` | `<p>the <b style="font: 12px serif">total</b> due</p><p><i>x</i></p>` | pass | `fm-font-resets` |
| P | a mark inside a head and title that an end tag closes is hidden, as the text view hides them | bold on `total`, context `the total due` | `<head><title>the <b>total</b> due</title></head><p>the total due</p>` | fail: `the span lacks ['bold']` | `fm-closed-head` |
| I | an unclosed head hides nothing: its text and marks are read, as the text view reads them | bold on `total`, context `the total due` | `<head>intro the <b>total</b> due` | pass | `fm-head-bare-text` |
| I | an unclosed comment hides nothing, as in the text view: what follows it is read | bold on `total`, context `the total due` | `<p>Intro</p><!-- figure placeholder <p>the <b>total</b> due</p>` | pass | `fm-unclosed-comment` |
| I | markup that is no tag is text: CDATA, a processing instruction and a stray < hide nothing | bold on `total`, context `the total due` | `<![CDATA[x]]><?xml v?><p>a<b the <b>total</b> due</p>` | pass | `fm-cdata` |
| I | an html tag inside markdown is read as html | sub on `2`, context `H2O` | `H<sub>2</sub>O` | pass | `fm-markdown-html` |
| P | a negative test, the span marked | not bold on `total`, context `the total due` | `the <b>total</b> due` | fail: `the span carries ['bold']` | `fm-neg-marked` |
| P | a negative test, the words not on a page that has marks | not bold on `total`, context `the total due` | `<p>nothing <b>here</b></p>` | fail: `the context is not in the output` | `fm-neg-missing` |
| P | the context is not on the page | bold on `total`, context `the total due` | `<b>total</b>` | fail: `the context is not in the output` | `fm-missing-context` |
| P | a heading is drawn bold but is not a mark | bold on `total`, context `total` | `<h2>total</h2>` | fail: `the span lacks ['bold']` | `fm-heading` |
| P | a table heading is not a mark | bold on `total`, context `total` | `<table><tr><th>total</th></tr></table>` | fail: `the span lacks ['bold']` | `fm-th` |
| P | `<mark>` is not a mark here | bold on `total`, context `the total due` | `the <mark>total</mark> due` | fail: `the span lacks ['bold']` | `fm-mark-element` |
| P | a link is drawn underlined but is not a mark | underline on `total`, context `the total due` | `the <a href='#'>total</a> due` | fail: `the span lacks ['underline']` | `fm-link` |
| P | markdown markers written into an html output | bold on `total`, context `the total due` | `the **total** due` | fail: `the context is not in the output` | `fm-raw-markdown` |
| P | mathematical bold letters read as the letters, not as a mark | bold on `total`, context `the total due` | `the 𝐭𝐨𝐭𝐚𝐥 due` | fail: `the span lacks ['bold']` | `fm-math-bold-letters` |
| P | a Unicode superscript is not `<sup>` | sup on `2`, context `x2 + 1` | `x² + 1` | fail: `the span lacks ['sup']` | `fm-unicode-sup` |
| P | LaTeX is not `<sup>`: maths has its own tests | sup on `2`, context `x2 + 1` | `$x^{2}$ + 1` | fail: `the context is not in the output` | `fm-latex-sup` |
| P | a mark inside `<math>` is not read | bold on `total`, context `the total due` | `the <math><b>total</b></math> due` | fail: `the span lacks ['bold']` | `fm-in-math` |
| I | a mark inside `<code>` is read like any other | bold on `total`, context `the total due` | `the <code><b>total</b></code> due` | pass | `fm-in-code` |
| P | a mark inside a script is not on the page | bold on `total`, context `the total due` | `the <script><b>total</b></script> due` | fail: `the context is not in the output` | `fm-hidden` |
| P | a style that draws the text plain inside `<b>` | bold on `total`, context `the total due` | `the <b><span style="font-weight:normal">total</span></b> due` | fail: `the span lacks ['bold']` | `fm-style-cancelled` |
| P | a class is not read: there is no style sheet | bold on `total`, context `the total due` | `the <span class="bold">total</span> due` | fail: `the span lacks ['bold']` | `fm-class` |
| P | a word broken at a line end is not joined | bold on `total`, context `the total due` | `the <b>to-\ntal</b> due` | fail: `the context is not in the output` | `fm-hyphen-break` |
| P | the words in another order | bold on `total amount`, context `the total amount due` | `the <b>amount total</b> due` | fail: `the context is not in the output` | `fm-wrong-order` |
| P | a subscript where a superscript is asked | sup on `2`, context `H2O` | `H<sub>2</sub>O` | fail: `the span lacks ['sup']` | `fm-sub-for-sup` |
| B | a span inside a longer word is found: word edges are not read | bold on `total`, context `total` | `<b>subtotal</b>` | pass | `fm-word-edge` |
| B | one marked copy among unmarked ones passes | bold on `total`, context `the total due` | `<p>the total due</p><p>the <b>total</b> due</p>` | pass | `fm-a-copy` |
| B | spaces are not compared, so words may be run together | bold on `total`, context `the total due` | `the<b>total</b>due` | pass | `fm-spacing-edge` |
| B | a case error on the span is not seen | bold on `Total`, context `the Total due` | `the <b>TOTAL</b> due` | pass | `fm-case-blind` |
| P | a negative test fails when any copy is marked | not bold on `total`, context `the total due` | `<p>the total due</p><p>the <b>total</b> due</p>` | fail: `the span carries ['bold']` | `fm-neg-all-copies` |
<!-- /cases -->

## Blind spots

- **Word edges are not read.** A span inside a longer word is found, so `total` is bold in `<b>subtotal</b>` (case
  fm-word-edge); the three words of a context give the test its anchor, so tests should carry one.
- **Spaces are not compared**, so words run together are the same words (case fm-spacing-edge).
- **Case is not compared**: a case error on the span is the exact-text tests' business (case fm-case-blind).
- **A second copy** of the phrase elsewhere on the page can carry the mark for a positive test (case fm-a-copy).

## What it cannot do

- A word broken at a line end is not joined, so a span a system hyphenates fails with "the context is not in the output"
  (case fm-hyphen-break). A character form that spans two runs (a combining accent, two apostrophes that fold to a
  quotation mark, an arrow written in two characters) is read as written when a mark boundary falls inside it
  (relation M57b in the certificate).
- It reads no style sheet or class (case fm-class); a system that writes `<span class="bold">` fails.
- A mark is read from the output, not from the page: the gold says what the page prints, and a test whose page does not
  print it is wrong (the datasets check this against the pages' fonts, not this scorer).

The why reads `the span lacks ['bold']`, `['bold'] runs onto the text around the span`, `the span carries ['bold']`,
`the context is not in the output` or `the output has no marks at all, so it cannot show that a mark is absent`.
