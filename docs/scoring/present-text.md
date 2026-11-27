# `present` with a text arg

A raised decimal point directly before a digit folds to `.` unless the character before it is a letter, a digit or a
closing bracket: `·79` matches `.79`, as do `p<·05`, `≈·5`, `(·5)`, `-·25` and `£·5`. After a letter, a digit-less
closing bracket or a CJK character the dot separates or multiplies and stays: `A·1`, `太原·2020`, `(a)·1` and `x)·2`
stay distinct from `A.1`, `太原.2020`, `(a).1` and `x).2`.

**Asks:** this string appears somewhere in the page's text (or, with `blank_after`, that a form label is followed by nothing: [Blank fields](#blank-fields-blank_after)). 3,684 tests; family text; reads `html`.

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
| I | a raised decimal point without a leading zero | `·2480550383` | `.2480550383` | pass | `text-leading-middot` |
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
| B | a superscript digit after a letter read as a footnote marker | `area in m is` | `<p>area in m<sup>2</sup> is</p>` | pass | `text-sup-unit` |
| B | two adjacent cells read as one string | `1 2` | `<table><tr><td>1</td><td>2</td></tr></table>` | pass | `text-table-flat` |
| B | a short gold with an edit to spend | `ab` (md 1) | `a` | pass | `text-short-fuzzy` |
| B | a unit changed within the budget | `Rate 5%` (md 1) | `Rate 5‰` | pass | `text-budget-unit` |
| B | a letter changed into another real word | `Take it from the list` (md 1) | `Take it form the list` | pass | `text-budget-real-word` |
| B | a negation dropped, at a budget that pays for it | `It does not work well` (md 4) | `It does work well` | pass | `text-budget-negation` |
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
| P | a middle-dot separator after a letter | `A·1` | `A.1` | fail | `text-middot-letter` |
| P | a middle-dot separator after a CJK character | `太原·2020` | `太原.2020` | fail | `text-middot-cjk` |
| P | a dropped thousands separator | `1,240` | `1240` | fail | `text-thousands` |
| P | decimal comma for a point | `1.5` | `1,5` | fail | `text-decimal-comma` |
| P | a dropped currency sign | `$5.00` | `5.00` | fail | `text-currency-lost` |
| P | an extra word inside | `Hello World` | `Hello big World` | fail | `text-extra-word` |
| P | words swapped | `Hello World` | `World Hello` | fail | `text-word-order` |
| P | checked against unchecked | `☒ Yes` | `<p><input type=checkbox> Yes</p>` | fail | `text-checkbox-state` |
| P | a look-alike character | `l` | `1` | fail | `text-homoglyph` |
| P | markdown stars printed in html | `Total Due` | `**Total** Due` | fail | `text-literal-stars` |
| P | a `^` the gold writes as text | `x^2` | `$x^2$` | fail | `text-caret` |
| P | an exponent is not a digit of the number before it | `12` | `<p>1<sup>2</sup></p>` | fail | `text-exponent` |
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
| P | a space splits a number, so the squeeze never joins two | `1 2` | `12 3` | fail | `edge-squeeze-spaced` |
| P | a spaced copy is two numbers | `40` | `400 4 0` | fail | `edge-glued-and-spaced` |
| P | digits spaced out | `305357` | `3 0 5 3 5 7` | fail | `edge-squeeze-digits` |
| I | spacing between a word and a number stays free | `Total 40` | `Total40` | pass | `edge-squeeze-word` |
| P | with `max_diffs` 1, an exact match is still guarded | `Total: 40` (md 1) | `Total: 400` | fail: `'Total: 40' found only inside a longer number` | `edge-fuzzy` |
<!-- /cases -->

A fuzzy match (one that spends an edit) is not checked here; a gold with a digit keeps its numbers
exact instead ([Numbers are exact](#numbers-are-exact)).

## Numbers are exact

A gold that holds a digit must match with each of its numbers whole and unchanged, after fold, at any
`max_diffs`: an edit may not change, add, drop, split or join a number, the squeezed retry never joins two, and
the matched text may not end inside one. A number is digit runs joined by a single `.` between digits, or by a
single `,` (and a space or none) before one to three digits: `1.2`, `1,240`, `12.05.2021`, `0.39, 1.56`, but not
`7,2016`. A leading `.` (`.5`) after white space, a bracket or an operator is part of it. Its separators are part
of it: `1,2` or `12` for `1.2`, `1240` for `1,240` and `5` for `.5` are other numbers; only a space after a
comma between two numbers is free (`(1.13, 3.99)` is `(1.13,3.99)`). A leading zero the page adds (`0.150` for
`.150`) is a digit the guard refuses. Every other character still costs one edit, and a gold without a digit is
matched as above.

A sign belongs to its number: a `-` (or `−`, or an en dash, which fold to one), `+` or `±` directly before a
number is a sign unless the character before it is a letter or a digit. So `-5`, `+1.55`, `x = -5`, `(-5)` and
`3 -5` are signed, and so are an exponent's sign (`1e-3`) and a sign after a Chinese, Japanese or Korean
character (such a text puts no space before it). A gold's sign must be written and cannot be added: `+1.55` is
not `1.55`. A sign before a currency symbol counts too (`-$1,234`, `(−€5)`), the symbol being part of the
number, and a spaced minus on the page (`− 0.756` for the gold's `−0.756`) is the gold's minus unless a value comes
before it (`3 - 5`). In a `table_cell` cell, a `- ` with a space (`− 0.756`, `(− 5)`) is a sign too at the start of the
cell, after an opening bracket or after `, ` (in a page text `- 12` may start a list item).

A `-` after a Latin letter or a digit is a hyphen: `A-12`, `2026-11-26`, `1-2` and `COVID-19` keep costing one
edit to drop, as do a list dash (`- 5` in the middle of a text) and a space-dash-space (`3 - 2`). This differs
on purpose from the number reader of `region`, which reads a sign after a letter too (`A-12`): a page often
writes such an id as `COVID 19` or `A12`, and a budget exists for that kind of noise. Spacing a unit exponent either way does not change
what a number is: a gold's `kg-1` is matched by the page's spaced `kg -1`, and a gold's `dm -3` by `dm-3` (after a
letter only). A `+` or `±` between two values (`6% ± 2%`, `1 +2`) is an operator, not a sign. The cost of this narrow rule: a minus written right after a Latin letter (`x-5`) reads as a hyphen, so
a budget can still drop it, and a spaced minus in the middle of a text (`was − 5`) is not guarded. `order` and
`table_cell` apply the same rule ([order.md](order.md#how-it-differs-from-present),
[table_cell.md](table_cell.md#blind-spots)).

<!-- cases:text-numbers -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| P | with an edit to spend, a different number | `Total: 41` (md 1) | `Total: 400` | fail: `'Total: 41' not found with its numbers exact (a number differs, or one was added, split or joined)` | `text-fuzzy-wrong-gold` |
| P | a changed digit | `Total: 41` (md 3) | `Total: 40` | fail | `num-fuzzy-digit` |
| P | a number split by a space | `Total: 41` (md 1) | `Total: 4 1` | fail | `num-fuzzy-split` |
| P | a number split by a point | `Total: 41` (md 3) | `Total 4.1` | fail | `num-fuzzy-point` |
| P | a letter read as a digit adds a number | `Total 41` (md 1) | `Tota1 41` | fail | `num-fuzzy-added` |
| P | two numbers joined | `Pages 1 to 2` (md 3) | `Pages 12` | fail | `num-fuzzy-joined` |
| P | a dropped thousands separator joins two numbers | `1,000` (md 1) | `1000` | fail | `num-fuzzy-thousands` |
| P | a comma for the decimal point | `Rate 1.2 per` (md 1) | `Rate 1,2 per` | fail | `txt-decimal-comma` |
| P | a decimal point dropped | `Rate 1.2 per` (md 2) | `Rate 12 per` | fail | `txt-decimal-dropped` |
| P | a lost plus sign | `Dose +1.55 mg` (md 2) | `Dose 1.55 mg` | fail | `txt-plus-lost` |
| P | a lost plus-minus sign | `Dose ±0.3 mg` (md 2) | `Dose 0.3 mg` | fail | `txt-plus-minus-lost` |
| P | a leading point is part of the number | `Area .5 ha` (md 2) | `Area 5 ha` | fail | `txt-leading-point` |
| P | a zero the page adds before a leading point is a digit the guard refuses | `Area .150 (4.07)` (md 1) | `Area 0.150 (4.07)` | fail | `txt-leading-zero` |
| I | a space after a comma between numbers is free | `CI (1.13, 3.99) here` (md 1) | `CI (1.13,3.99) here` | pass | `txt-comma-space` |
| I | so is a space dropped from a date list | `on 12, 19 November 2012` (md 1) | `on 12,19 November 2012` | pass | `txt-comma-space-date` |
| P | a digit of another script is another number | `3.` (md 1) | `๓.` | fail | `num-fuzzy-script` |
| P | a lost minus sign | `Net -5 total` (md 2) | `Net 5 total` | fail | `txt-sign-lost` |
| P | a minus sign added | `Net 5 total` (md 2) | `Net -5 total` | fail | `txt-sign-added` |
| P | a lost minus sign inside brackets | `Margin (-5)` (md 2) | `Margin (5)` | fail | `txt-sign-bracket` |
| I | a minus written as `−` or an en dash | `Net -5 total` (md 1) | `Net −5 total` | pass | `txt-sign-spelling` |
| I | a hyphen after a letter or between figures is no sign: dropping one is an edit | `Case A-12 ok` (md 1) | `Case A12 ok` | pass | `txt-hyphen` |
| I | a letter edit beside a number | `Total: 41` (md 1) | `Totel: 41` | pass | `num-fuzzy-letter` |
| I | full-width digits fold first | `Room 3` (md 1) | `Room ３` | pass | `num-fuzzy-fullwidth` |
| I | a number after the matched text is outside it | `Figure 3` (md 1) | `Figure 3 2019 data` | pass | `num-fuzzy-after` |
<!-- /cases -->

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

## Blank fields (`blank_after`)

`present` with `"settings": {"blank_after": true}` asks the opposite of a plain `present`: the content is a form
field's label, and **nothing is written after it**. It catches a system that fills a field the page leaves blank
(`Date of birth: 01/02/1990`, `N/A`, a copy of the printed mask). Two optional roles say where the field ends and
what it prints:

```json
{"test_type": "present", "derivation": "authored", "tags": ["form"],
 "args": {"content": {"text": "Date of birth:", "max_diffs": 0},
          "printed": {"text": "__/__/____", "max_diffs": 0},
          "stops": [{"text": "Name:", "max_diffs": 0}, {"text": "Place of birth:", "max_diffs": 0}]},
 "settings": {"blank_after": true}}
```

- `content`: the label. Every text arg of the test has `max_diffs` 0 (a fuzzy match has no exact boundary), no
  `exact_case`, no `place`; the loader refuses anything else, and `printed` or `stops` without the setting.
- `stops`: every other field label on the page, where this field's region ends. A stop equal to the label is refused.
  Without stops the region runs to the end of the page, so the next field's value counts against the field.
- `printed`: the placeholder the page prints in the field (`__/__/____`, `DD / MM / YYYY`). One copy of it may follow
  the label.

**The test passes when every occurrence of the label is blank.** An occurrence is a copy of the folded label at a
word edge (not inside a longer word, not cut out of a longer number; a page that glues its words is searched with
the spaces removed, as `present` does), in the text view without image descriptions and without the marks the text
view writes for an empty element (as `page_near_empty`). A copy inside a longer stop (`Name:` in `Last Name:`) is that
stop, not the label. It also needs a plain `present` pass, so a `blank_after` pass is always a `present` pass.

- **A label printed twice** is two fields, and both must be blank: a clean copy next to a filled one (a duplicated form
  block, a table written twice) fails. A copy's region also ends at the next copy of the label, and an earlier copy in the same line or row is that copy's, not a value before this one. The price: a page that
  prints one label twice with a real value beside one of them fails a faithful output, so a gold uses a label that is
  unique on the page, or one long enough to be (`Signature of the applicant:` for the second `Signature:`).
- **Before the label,** the text before it in its paragraph, line (`<br>`) or cell must be blank, unless another stop comes
  first in it (what follows that stop is its value). `12/03/1985 Date of birth: ____` fails. The price: a number or
  word printed before the label in the same line, with no stop before it (`3 Date of birth:`), counts as a value, so a
  gold puts it in the label (`3 Date of birth:`) or lists what precedes it as a stop.
- **In running text,** the region runs from the label to the first later stop or copy of the label, or to the end of the
  page. Remove one copy of `printed`; the field is blank when only white space and the characters `_`, `.`, `·` and `…`
  remain. Three or more of `_`, `.` or `-` already fold away as a leader; `__` and `..` stay, and are blank here; a lone
  `-`, `N/A`, `[blank]` and a checkbox are values. A mask of underscores that markdown read as bold (`__/__/____` written
  in markdown, left as `//`) is the printed mask too, only when the page holds the converter's own html for it
  (`<strong>/</strong>/____`); `//` written in html is a value.
- **In a table cell,** the rest of the label's own cell (up to a stop) is the first region. If it is blank, the value
  cells are read in three directions, and each must show nothing but the same characters (an image is not blank):
  every cell to its right, up to another field's label (its whole text is a stop) or another copy of this one; in a table
  of several columns, the cells below it, in its columns and in those of the blank cells to its right, down to a label in
  its own columns (a header-row layout, a label in the last column or a blank cell to
  its right: the value is below); and the cells to its left, back to another field's label (the value of that field is
  not this one's). A cell whose whole text is a stop is a label, not a value; a cell that holds a stop and more
  (`Name: Ann`) is a value. A label that spans rows or columns needs every cell beside it blank. Cells are read as
  written, with no stand-in for an empty one (unlike a `table_cell` text arg), so a copy of the value beside or above
  it fails.
- **After the table:** when no other label comes below the label in its table (it is the table's last field), its region
  goes on after `</table>`, up to the next stop or copy of the label: a value in a table or a paragraph written after
  it fails. The price: text printed after a form's last table that is no field's label (a footer, a note) counts as a
  value, so a gold lists every field label, and a note too, as a stop.
- A label in one cell of a one-column table has no value column: the cells below are not read, but when no label comes
  below it the region goes on past the table, as above.

Failure reasons: `'Date of birth:' not found ...` (plain `present`'s), `'Date of birth:' not found whole, at a word
edge, in one paragraph or one table cell`, `'Date of birth:' is followed by '01/02/1990' before the next field` (or
`to the end of the page`, or `in its cell`) and `'Date of birth:' cell's value cell (right) holds '01/02/1990'` (or
`(below)`, or `(left)`), `'Date of birth:' has '12/03/1985' before it` and `is followed by '12/03/1985' after its table, before the next field`. Several failing occurrences are joined, the first two shown.

<!-- cases:blank-after -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| I | nothing after the label, then the next field | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<p>Name: Ann</p><p>Date of birth:</p><p>Place of birth: Paris</p>` | pass | `blank-nothing` |
| I | the last field on the page, nothing after it | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<p>Name: Ann</p><p>Date of birth:</p>` | pass | `blank-last` |
| I | a run of underscores (a leader) | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<p>Date of birth: ____</p><p>Place of birth: Paris</p>` | pass | `blank-underscores` |
| I | a run of dots | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<p>Date of birth: ........</p><p>Place of birth: Paris</p>` | pass | `blank-dots` |
| I | two underscores (not a leader, still a placeholder) | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<p>Date of birth: __</p><p>Place of birth: Paris</p>` | pass | `blank-two-underscores` |
| I | leaders glued to the next label | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<p>Date of birth: _____Place of birth: ____</p>` | pass | `blank-leader-glued` |
| I | the printed mask copied once | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<p>Date of birth: __/__/____</p><p>Place of birth: Paris</p>` | pass | `blank-printed` |
| I | white space, `<br>` and an empty element | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<p>Date of birth: <br>  <span></span></p><p>Place of birth: Paris</p>` | pass | `blank-white-space` |
| I | the label in another case | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<p>DATE OF BIRTH:</p><p>Place of birth: Paris</p>` | pass | `blank-case` |
| I | another field written before it | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<p>Place of birth: Paris</p><p>Date of birth:</p><p>Name: Ann</p>` | pass | `blank-moved-field` |
| I | an image description in the region is not text | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<p>Date of birth: <img alt='box'></p><p>Place of birth: Paris</p>` | pass | `blank-image-alt` |
| I | a text layer that glues words, found with its spaces removed | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<p>Dateofbirth:____Placeofbirth:Paris</p>` | pass | `blank-glued-words` |
| I | markdown, as the harness converts it | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `Name: Ann\n\nDate of birth: \n\nPlace of birth: Paris` | pass | `blank-markdown` |
| I | a two-column label and value table, the value cell empty | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<table><tr><td>Date of birth:</td><td></td></tr><tr><td>Place of birth:</td><td>Paris</td></tr></table>` | pass | `blank-table-2col` |
| I | the value cell holds the printed mask | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<table><tr><td>Date of birth:</td><td>__/__/____</td></tr></table>` | pass | `blank-table-2col-mask` |
| I | the rest of the label's own cell is blank | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<table><tr><td>Date of birth: ____</td><td></td></tr></table>` | pass | `blank-table-rest-of-cell` |
| I | a header-row table: the cell below the label is empty | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<table><tr><td>Date of birth:</td><td>Place of birth:</td></tr><tr><td></td><td>Paris</td></tr></table>` | pass | `blank-table-header-row` |
| I | a header-row table: no row below | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<table><tr><td>Name:</td><td>Date of birth:</td></tr></table>` | pass | `blank-table-header-row-end` |
| I | the label in the last column: the cell below is empty | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<table><tr><td>Name: Ann</td><td>Date of birth:</td></tr><tr><td>x</td><td></td></tr></table>` | pass | `blank-table-last-column` |
| I | the cell below is another field's label, not a value | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<table><tr><td>Date of birth:</td><td>Place of birth:</td></tr><tr><td>Name:</td><td></td></tr></table>` | pass | `blank-table-label-below` |
| I | the label printed twice, blank both times | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<p>Date of birth:</p><p>Name: Ann</p><p>Date of birth: ____</p>` | pass | `blank-repeated-both` |
| I | a label ending its table, the next field after it in a paragraph | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<table><tr><td>Name:</td><td>Ann</td></tr><tr><td>Date of birth:</td><td></td></tr></table><p>Place of birth: Paris</p>` | pass | `blank-split-table` |
| I | the value left of the label is another field's | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<table><tr><td>Name:</td><td>Ann</td><td>Date of birth:</td><td></td></tr></table>` | pass | `blank-table-field-before` |
| I | a copy inside a longer stop is that stop, not the label | `Name:`, stops `Last Name:` | `<p>Last Name: ____</p><p>Name: ____</p>` | pass | `blank-inside-label` |
| P | a checkbox is out of scope: it reads as text, so a box beside the label fails | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<p>Date of birth: <input type=checkbox></p>` | fail: `'Date of birth:' is followed by '☐' to the end of the page` | `blank-checkbox` |
| I | a mask of underscores in markdown: the converter reads `__` as bold, and the mask without its underscores is still the mask | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `Date of birth: __/__/____\n\nPlace of birth: Paris` | pass | `blank-markdown-mask` |
| P | the label printed twice, one copy filled | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<p>Date of birth: 01/02/1990</p><p>Date of birth:</p>` | fail: `'Date of birth:' is followed by '01/02/1990' before the next field` | `invent-repeated-one-filled` |
| P | the label in a table cell and in a paragraph: the paragraph's copy is filled | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<p>Date of birth: 01/02/1990</p><table><tr><td>Date of birth:</td><td></td></tr></table>` | fail | `invent-repeated-cell-paragraph` |
| I | the label printed twice in one line, blank both times | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<p>Date of birth: __/__/____ Date of birth: __/__/____ Place of birth: Paris</p>` | pass | `blank-repeated-line` |
| I | the label in two cells of one row, blank both times | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<table><tr><td>Date of birth:</td><td></td><td>Date of birth:</td><td></td></tr></table>` | pass | `blank-repeated-row` |
| P | the label in two cells of one row, the second copy filled | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<table><tr><td>Date of birth:</td><td></td><td>Date of birth:</td><td>01/02/1990</td></tr></table>` | fail: `'Date of birth:' cell's value cell (right) holds '01/02/1990'` | `invent-repeated-row` |
| P | a value below the blank right cell, in its column | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<table><tr><td>Date of birth:</td><td></td></tr><tr><td></td><td>01/02/1990</td></tr></table>` | fail: `'Date of birth:' cell's value cell (below) holds '01/02/1990'` | `invent-table-right-column-below` |
| P | two slashes in html are not the markdown mask | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<p>Date of birth: //</p>` | fail | `invent-slashes-html` |
| P | a value in a paragraph after a one-column table | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<table><tr><td>Date of birth:</td></tr></table><p>01/02/1990</p>` | fail: `'Date of birth:' is followed by '01/02/1990' after its table, to the end of the page` | `invent-after-one-column` |
| P | a value written before the label | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<p>Name: Ann</p><p>01/02/1990 Date of birth: __/__/____</p>` | fail: `'Date of birth:' has '01/02/1990' before it` | `invent-before-label` |
| P | a value written before the label in its cell | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<table><tr><td>01/02/1990 Date of birth:</td><td></td></tr></table>` | fail: `'Date of birth:' has '01/02/1990' before it` | `invent-table-before-label` |
| P | a value in the cell left of the label | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<table><tr><td>01/02/1990</td><td>Date of birth:</td><td></td></tr></table>` | fail: `'Date of birth:' cell's value cell (left) holds '01/02/1990'` | `invent-table-left` |
| P | a value two cells right of the label, the cell beside it blank | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<table><tr><td>Date of birth:</td><td></td><td>01/02/1990</td></tr></table>` | fail: `'Date of birth:' cell's value cell (right) holds '01/02/1990'` | `invent-table-two-right` |
| P | a value below the label, the cell beside it blank | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<table><tr><td>Date of birth:</td><td></td></tr><tr><td>01/02/1990</td><td></td></tr></table>` | fail: `'Date of birth:' cell's value cell (below) holds '01/02/1990'` | `invent-table-below-blank-right` |
| P | a value two rows below the label of a header-row table | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<table><tr><td>Date of birth:</td><td>Place of birth:</td></tr><tr><td></td><td>Paris</td></tr><tr><td>01/02/1990</td><td></td></tr></table>` | fail: `'Date of birth:' cell's value cell (below) holds '01/02/1990'` | `invent-table-two-down` |
| P | a value in a table written after the label's table | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<table><tr><td>Date of birth:</td><td></td></tr></table><table><tr><td>01/02/1990</td></tr></table>` | fail: `'Date of birth:' is followed by '01/02/1990' after its table, to the end of the page` | `invent-after-table` |
| P | an invented value | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<p>Date of birth: 01/02/1990</p><p>Place of birth: Paris</p>` | fail: `'Date of birth:' is followed by '01/02/1990' before the next field` | `invent-value` |
| P | `N/A` is a value the page does not print | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<p>Date of birth: N/A</p><p>Place of birth: Paris</p>` | fail: `'Date of birth:' is followed by 'n/a' before the next field` | `invent-na` |
| P | a lone dash (not a leader) is a value | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<p>Date of birth: -</p><p>Place of birth: Paris</p>` | fail | `invent-dash` |
| P | `[blank]` is a value | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<p>Date of birth: [blank]</p>` | fail | `invent-blank-word` |
| P | the printed mask copied twice | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<p>Date of birth: __/__/____ __/__/____</p>` | fail | `invent-mask-twice` |
| P | the mask written but the gold names none | `Date of birth:`, stops `Name:`, `Place of birth:` | `<p>Date of birth: __/__/____</p>` | fail | `invent-mask-without` |
| P | an invented value after the last field | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<p>Name: Ann</p><p>Date of birth: 5 May</p>` | fail: `'Date of birth:' is followed by '5 may' to the end of the page` | `invent-last` |
| P | a value glued to the label | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<p>Date of birth:1990</p>` | fail | `invent-glued` |
| P | without stops the region runs to the page's end: the next field's value is in it | `Date of birth:`, printed `__/__/____` | `<p>Date of birth:</p><p>Place of birth: Paris</p>` | fail | `invent-no-stop` |
| P | a value in the value cell to the right | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<table><tr><td>Date of birth:</td><td>01/02/1990</td></tr></table>` | fail: `'Date of birth:' cell's value cell (right) holds '01/02/1990'` | `invent-table-right` |
| P | a value under the label in a header-row table | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<table><tr><td>Date of birth:</td><td>Place of birth:</td></tr><tr><td>01/02/1990</td><td></td></tr></table>` | fail: `'Date of birth:' cell's value cell (below) holds '01/02/1990'` | `invent-table-below` |
| P | the next field's value shifted into the cell | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<table><tr><td>Date of birth:</td><td>Paris</td></tr><tr><td>Place of birth:</td><td></td></tr></table>` | fail | `invent-table-shifted` |
| P | a value in the label's own cell | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<table><tr><td>Date of birth: 5</td><td></td></tr></table>` | fail: `'Date of birth:' is followed by '5' in its cell` | `invent-table-rest` |
| P | a value under a label in the last column | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<table><tr><td>Name: Ann</td><td>Date of birth:</td></tr><tr><td>x</td><td>1990</td></tr></table>` | fail | `invent-table-last-column` |
| P | an image in the value cell | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<table><tr><td>Date of birth:</td><td><img src='a.png'></td></tr></table>` | fail | `invent-table-image` |
| P | a merged label cell: every cell beside it must be blank | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<table><tr><td rowspan=2>Date of birth:</td><td></td></tr><tr><td>1990</td></tr></table>` | fail | `invent-table-merged` |
| P | an invented value in markdown | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `Date of birth: 01/02/1990\n\nPlace of birth: Paris` | fail | `invent-markdown` |
| P | the label missing: a plain `present` failure | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<p>Name: Ann</p>` | fail: `'Date of birth:' not found (best 0.300 < 1.000); closest 'name:ann'` | `invent-missing` |
| P | the label inside a longer word | `Name` | `<p>Surnames: Ann</p>` | fail: `'Name' not found whole, at a word edge, in one paragraph or one table cell` | `invent-word-edge` |
| P | the label split over two cells | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<table><tr><td>Date of</td><td>birth:</td></tr></table>` | fail: `'Date of birth:' not found whole, at a word edge, in one paragraph or one table cell` | `invent-split-label` |
| P | a two-column form read across, the next field's label not a stop | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:` | `<p>Date of birth: Sex: F</p>` | fail | `invent-read-across` |
| I | a two-column form read across with the other field's label a stop | `Date of birth:`, printed `__/__/____`, stops `Name:`, `Place of birth:`, `Sex:` | `<p>Date of birth: ____ Sex: F</p>` | pass | `blank-read-across` |
<!-- /cases -->

Blind spots of `blank_after`, besides those of `present`:

- **Right-to-left pages** are read in the html's order, as `table_cell` does: an output in visual order is not
  checked. A value printed to the left of its label is not read.
- **Reading order.** A value moved far from its label but in front of the next stop is caught only if it lies between
  them; a value moved after the next stop is not this field's. A value written before the label is caught only in its
  own paragraph, line or cell, or in the cells to its left, and not when another stop comes first (that stop's value).
  A value on the line above the label (`<br>`) is not read.
- **Image descriptions** never count here either, as in `page_near_empty`: a value written as the alt text of an image
  beside the label passes.
- **Fields the output drops** fail by `not found`, which is right for transcription and counts twice with a `present`
  test of the same label; a label that is itself mistranscribed fails the same way.
- **A one-column table** has no value column, so the row after a label is not read; a value there passes. A table the cell
  reader cannot parse (`<td>` outside a `<tr>`) is read as text. Image descriptions in the region are ignored (case blank-image-alt) but an image in a
  value cell is a value; a checkbox, a footnote mark or math in the region reads as text (case blank-checkbox).

## Blind spots

- **No word edges.** `Total` is found in `Totally` (case text-longer-word). Use `repeat` for whole words.
- **Letters beside a number are free.** `4.8` is found in `a4.8` (case text-letter-beside). Use a number arg
  ([present-number.md](present-number.md)) when sign and percent matter.
- **A budget still pays for anything that is not a digit or a sign.** A unit that reads as another (`5%` for
  `5‰`, case text-budget-unit), a letter change that makes another real word (`from` for `form`, case
  text-budget-real-word), and, on a long passage with a budget of 2 or more, a dropped `not` (case
  text-budget-negation) all pass. This is not a negation guard: keep the budget at 0 where one word flips the
  meaning.
- **Brackets round a number are not a sign.** An accounting negative `(1,234)` passes for `1,234` and the other
  way round when the budget has 2 edits to spend (case cell-accounting-brackets); keep the budget at 0 for it.
- **Image descriptions pay.** A description that contains the string passes the test (case text-alt).
- **Most budgets are real.** 1,370 of the 3,684 real present text tests allow 1 to 4 edits; the others allow none.
- **Short golds and edit budgets are loose.** With one edit, `ab` is found in a page holding `a` (case
  text-short-fuzzy). How edits are counted is in [internals.md](internals.md#the-edit-budget).
- **A table is flat text here.** A gold that spans two adjacent cells passes (case text-table-flat).

A failure's why reads `'gold' not found with its numbers exact (...)` when the edits fit the budget only by
changing a number, `'gold' found only inside a longer number` when the digit edge rejected every exact
match, and otherwise `'gold' not found (best r < threshold); closest '...'`: the best match ratio, the ratio
needed (`1 - max_diffs / length of the folded gold`), and the closest part of the page. The ratio is
rapidfuzz's partial ratio, a first pass that a page within budget always clears; when that passes with edits to
spend, the edits are counted and the ratio is `1 - edits / length of the folded gold`.
