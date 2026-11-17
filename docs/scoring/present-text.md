# `present` with a text arg

**Asks:** this string appears somewhere in the page's text. 3,684 tests; family text; reads `html`.

The test folds the gold and the page text ([README](README.md#two-words-used-everywhere)) and looks for the gold
as a substring, allowing up to `max_diffs` character edits (a character substituted, inserted or deleted, or
two adjacent characters swapped, is one edit). If that fails it tries again on the squeezed strings,
then once more allowing a hyphen at a line end to be kept or dropped. It does not ask where the string is, what
element holds it, or what is next to it. The page text includes image descriptions (`alt`) and reads a table cell
by cell ([internals.md](internals.md#the-text-view)).

Case is folded, unless the arg sets `exact_case`: then the same search, squeeze and hyphen retry run on
strings that keep their case (every other fold still applies), so `iPhone` does not pass for `iphone`
(cases `text-exact-case`, `text-exact-case-line-hyphen-wrong`) and does pass in its case through every other
difference (cases `text-exact-case-kept`, `text-exact-case-folds`, `text-exact-case-line-hyphen`). With edits
to spend, a changed letter's case costs one, so `exact_case` and a `max_diffs` above 0 exclude each other and the loader refuses the pair.

## Rules

What the test ignores:

<!-- cases:text-ignored -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| I | letter case | `Total Due` | `TOTAL due` | pass | `text-case` |
| I | Greek case | `α` | `Α` | pass | `text-case-greek` |
| I | spacing inside the string | `Total Due` | `TotalDue` | pass | `text-spacing` |
| I | bold, italic, strike tags | `Total Due` | `<p><b>Total</b> <s>Due</s></p>` | pass | `text-markup` |
| I | dash family (hyphen, en dash, minus) | `a-b` | `a–b` | pass | `text-dash` |
| I | quote family | `it's` | `it’s` | pass | `text-quote` |
| I | ligature | `final` | `ﬁnal` | pass | `text-ligature` |
| I | full-width digits | `12` | `１２` | pass | `text-fullwidth` |
| I | superscript digit | `m2` | `m²` | pass | `text-superscript` |
| I | zero-width space | `ab` | `a` U+200B `b` | pass | `text-zero-width` |
| I | footnote marker in brackets | `Smith` | `Smith[1]` | pass | `text-footnote` |
| I | footnote marker in `<sup>` | `Probiotic` | `<p>Probiotic<sup>1</sup></p>` | pass | `text-sup-marker` |
| I | footnote marker in `<sup>` inside the string | `Smith and Jones` | `<p>Smith<sup>1</sup> and Jones</p>` | pass | `text-sup-inside` |
| I | leader dots | `Name 5` | `Name ........ 5` | pass | `text-leaders` |
| I | bullet at the start of a line | `Item one` | `• Item one` | pass | `text-bullet` |
| I | word broken at a line end | `developers` | `develop- ers` | pass | `text-line-hyphen` |
| I | hyphenated compound broken at a line end | `self-aware` | `self- aware` | pass | `text-compound` |
| I | checkbox written another way | `☒ Yes` | `<p><input type=checkbox checked> Yes</p>` | pass | `text-checkbox` |
| I | a variable in math | `U test` | `$U$ test` | pass | `text-math-letter` |
| I | a symbol in math | `3σ` | `$3\sigma$` | pass | `text-math-symbol` |
| I | middle dot as a decimal point | `2.3` | `2·3` | pass | `text-middot` |
| I | dashes glued to a number are a leader | `Revenue 5` | `Revenue -----5` | pass | `text-glued-dash` |
| I | with `exact_case`, the case as printed | `iPhone` (exact case) | `I bought an iPhone` | pass | `text-exact-case-kept` |
| I | with `exact_case`, every other difference still folds | `Total Due` (exact case) | `<p><b>Total</b>  Due</p>` | pass | `text-exact-case-folds` |
| I | with `exact_case`, a word broken at a line end in its case | `Developers` (exact case) | `Develop- ers` | pass | `text-exact-case-line-hyphen` |
| I | with `exact_case`, a checkbox word in another case is still the one mark | `[Checked] Yes` (exact case) | `[checked] Yes` | pass | `text-exact-case-checkbox` |
| I | with `exact_case`, an unchecked word in capitals is still the one mark | `[unchecked] No` (exact case) | `[UNCHECKED] No` | pass | `text-exact-case-unchecked` |
| I | two letters swapped, within 1 edit | `Total` (md 1) | `Toatl` | pass | `text-transposition` |
<!-- /cases -->

What it does not look at, so a wrong output passes:

<!-- cases:text-blind -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| B | with `exact_case`, the string in an image description in its case | `Total` (exact case) | `<img alt='Total'>` | pass | `text-exact-case-alt` |
| B | with `exact_case`, text styled to look uppercase counts as the case it is written in | `nasa` (exact case) | `<p><span style='text-transform:uppercase'>nasa</span></p>` | pass | `text-exact-case-css-lower` |
| B | struck-through text still counts | `Total Due` | `<p><s>Total Due</s></p>` | pass | `text-strike` |
| B | the string repeated in a loop | `Total Due` | `Total Due Total Due Total Due` | pass | `text-loop` |
| B | a longer word holds the string | `Total` | `Totally` | pass | `text-longer-word` |
| B | a letter glued to a number | `4.8` | `a4.8` | pass | `text-letter-beside` |
| B | a currency sign the gold lacks | `5.00` | `$5.00` | pass | `text-currency-extra` |
| B | the string only in an image description | `Total` | `<img alt='Total'>` | pass | `text-alt` |
| B | an exponent read as a digit | `12` | `<p>1<sup>2</sup></p>` | pass | `text-exponent` |
| B | a superscript digit after a letter read as a footnote marker | `area in m is` | `<p>area in m<sup>2</sup> is</p>` | pass | `text-sup-unit` |
| B | two adjacent cells read as one string | `1 2` | `<table><tr><td>1</td><td>2</td></tr></table>` | pass | `text-table-flat` |
| B | with an edit to spend, a different number | `Total: 41` (md 1) | `Total: 400` | pass | `text-fuzzy-wrong-gold` |
| B | a short gold with an edit to spend | `ab` (md 1) | `a` | pass | `text-short-fuzzy` |
<!-- /cases -->

What it penalizes:

<!-- cases:text-penalized -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| P | a changed letter | `Total` | `Totel` | fail: `'Total' not found (best 0.800 < 1.000); closest 'totel'` | `text-changed` |
| P | more edits than `max_diffs` | `Total` (md 1) | `Tutel` | fail | `text-over-budget` |
| P | each inserted letter is an edit | `lorem ipsum dolor sit amet` (md 2) | `lorem izpsum dolqor sit amjet` | fail | `text-inserted` |
| P | a text at the edge of the page gets no extra edits | `lorem ipsum` (md 2) | `abc xxxem ipsum` | fail | `text-page-edge` |
| P | a dropped diacritic | `naïve` | `naive` | fail | `text-diacritic` |
| P | dropped punctuation | `Mr. Smith` | `Mr Smith` | fail | `text-punctuation` |
| P | a dropped thousands separator | `1,240` | `1240` | fail | `text-thousands` |
| P | decimal comma for a point | `1.5` | `1,5` | fail | `text-decimal-comma` |
| P | a dropped currency sign | `$5.00` | `5.00` | fail | `text-currency-lost` |
| P | an extra word inside | `Hello World` | `Hello big World` | fail | `text-extra-word` |
| P | words swapped | `Hello World` | `World Hello` | fail | `text-word-order` |
| P | checked against unchecked | `☒ Yes` | `<p><input type=checkbox> Yes</p>` | fail | `text-checkbox-state` |
| P | a look-alike character | `l` | `1` | fail | `text-homoglyph` |
| P | markdown stars printed in html | `Total Due` | `**Total** Due` | fail | `text-literal-stars` |
| P | a `^` the gold writes as text | `x^2` | `$x^2$` | fail | `text-caret` |
| P | a superscript after a digit is an exponent, not a marker | `10 cells` | `<p>10<sup>5</sup> cells</p>` | fail | `text-sup-exponent` |
| P | a sign after leaders | `Revenue 4.8` | `Revenue ....... -4.8` | fail | `text-sign-after-leaders` |
| P | with `exact_case`, a changed letter case | `iPhone` (exact case) | `I bought an iphone` | fail | `text-exact-case` |
| P | with `exact_case`, an acronym in lower case | `NASA` (exact case) | `Nasa launched` | fail | `text-exact-case-acronym` |
| P | with `exact_case`, a word broken at a line end in another case | `Developers` (exact case) | `develop- ers` | fail | `text-exact-case-line-hyphen-wrong` |
| P | with `exact_case`, an uppercase gold on text that only looks uppercase (`text-transform`) | `NASA` (exact case) | `<p><span style='text-transform:uppercase'>nasa</span></p>` | fail | `text-exact-case-css-upper` |
| P | with `exact_case`, a capital on text in small caps written in lower case | `Nasa` (exact case) | `<p><span style='font-variant:small-caps'>nasa</span></p>` | fail | `text-exact-case-small-caps` |
| P | a case change that changes letters | `straße` | `STRASSE` | fail | `text-case-mapping` |
<!-- /cases -->

## The digit edge

A substring test would find `40` in `400`. To prevent that, an exact match does not count when a gold that starts
(or ends) with a digit continues a longer number in the output: a digit, a sign, or a separator then a digit is
glued to it. One clean copy anywhere is enough.

<!-- cases:text-digit-edge -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| P | a digit continues the number | `Total: 40` | `Total: 400` | fail: `'Total: 40' found only inside a longer number` | `edge-digit-after` |
| P | a digit before the number | `4.8` | `14.8` | fail | `edge-digit-before` |
| P | a minus sign glued before | `4.8` | `-4.8` | fail | `edge-sign` |
| P | a plus sign glued before | `4.8` | `+4.8` | fail | `edge-plus` |
| P | a separator and a digit after | `4.8` | `4.8.5` | fail | `edge-separator` |
| I | one clean copy is enough | `4.8` | `-4.8 and 4.8` | pass | `edge-one-clean` |
| I | a hyphen after a letter or digit is not a sign | `4.8` | `12-4.8` | pass | `edge-hyphen` |
| I | parentheses, a percent sign, a full stop | `4.8` | `(4.8%).` | pass | `edge-paren` |
| P | a gold ending in a digit is guarded at that end | `x1` | `x12` | fail | `edge-end-digit` |
| B | a gold ending in a letter is not | `x1` | `x1y` | pass | `edge-end-letter` |
| P | spacing removed, then judged on the spaced text | `1 2` | `123` | fail | `edge-squeeze-glued` |
| I | a space is not a digit | `1 2` | `12 3` | pass | `edge-squeeze-spaced` |
| I | a spaced copy counts beside a glued one | `40` | `400 4 0` | pass | `edge-glued-and-spaced` |
| I | digits spaced out | `305357` | `3 0 5 3 5 7` | pass | `edge-squeeze-digits` |
| P | with `max_diffs` 1, an exact match is still guarded | `Total: 40` (md 1) | `Total: 400` | fail: `'Total: 40' found only inside a longer number` | `edge-fuzzy` |
<!-- /cases -->

A fuzzy match (one that spends an edit) is not checked. So with `max_diffs` 1, the wrong gold `Total: 41` passes
on `Total: 400` while the right gold `Total: 40` fails (cases text-fuzzy-wrong-gold, edge-fuzzy).

## Footnote markers

The page text reads a footnote marker as a spaced number: `Smith[1]` as `smith 1`, and `Smith<sup>1</sup>` the
same way. When the gold is not found, the test tries once more with the page's markers dropped, so a marker
inside the gold's span costs nothing (case text-sup-inside). A marker is:

- a bracketed `[n]` or `[^n]` (one to three digits, or one to three letters or digits after `^`), unless it
  stands between two digits (`12[3]4` keeps it, so the two numbers never join);
- a `<sup>` holding only one to three ASCII digits, or one to three of `*`, `†`, `‡`, `§`, `¶`, `#` (white
  space and inline tags such as a link aside), unless a digit comes right before it: there it is an exponent
  (`10<sup>5</sup>`, case text-sup-exponent).

A superscript holding letters (`1<sup>st</sup>`, `H<sup>+</sup>`) is never a marker, nor is an exponent in math
(`$x^2$`, `<math>`) or a superscript character (`x²`). A superscript digit after a letter is a marker, so a gold
that leaves out a unit's exponent passes (case text-sup-unit).

## Blind spots

- **No word edges.** `Total` is found in `Totally` (case text-longer-word). Use `repeat` for whole words.
- **Letters beside a number are free.** `4.8` is found in `a4.8` (case text-letter-beside). Use a number arg
  ([present-number.md](present-number.md)) when sign and percent matter.
- **Spacing is free, so an exponent is a digit.** `12` is found in `1<sup>2</sup>` (case text-exponent).
- **Image descriptions pay.** A description that contains the string passes the test (case text-alt).
- **Most budgets are real.** 1,370 of the 3,684 real present text tests allow 1 to 4 edits; the others allow none.
- **Short golds and edit budgets are loose.** With one edit, `ab` is found in a page holding `a` (case
  text-short-fuzzy). How edits are counted is in [internals.md](internals.md#the-edit-budget).
- **A table is flat text here.** A gold that spans two adjacent cells passes (case text-table-flat).

A failure's why reads `'gold' found only inside a longer number` when the digit edge rejected every exact
match, and otherwise `'gold' not found (best r < threshold); closest '...'`: the best match ratio, the ratio
needed (`1 - max_diffs / length of the folded gold`), and the closest part of the page. The ratio is
rapidfuzz's partial ratio, a first pass that a page within budget always clears; when that passes with edits to
spend, the edits are counted and the ratio is `1 - edits / length of the folded gold`.
