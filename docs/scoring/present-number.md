# `present` with a number arg

**Asks:** this number appears somewhere on the page, digit for digit, with its sign and, if the gold has one, its
percent sign. 323 tests; family text; reads `html`.

The test reads the gold's digits, then looks for them in the folded page text (math read as text). The digits must
match exactly; separators are lenient. A match is never preceded by a digit, nor followed by a digit or by a dot
or comma and a digit. A number found anywhere counts: its row, label and place are not checked.

## How the gold is read

A gold that is ambiguous is refused when the dataset is loaded, so no test in the dataset has one.

<!-- cases:number-gold -->
| rule | input | reads as | case |
|---|---|---|---|
| one `.`: a decimal point | `12.5` | `12.5` | `gold-point` |
| one `.`: any number of decimals | `1.2345678` | `1.2345678` | `gold-point-long` |
| one `.` and exactly three digits after a nonzero part: ambiguous | `1.240` | `refused` | `gold-point-three` |
| the same after `0`: a decimal | `0.500` | `0.500` | `gold-point-zero` |
| one `,` and three digits: a thousands mark | `1,240` | `1240` | `gold-comma-three` |
| one `,` and one or two digits: ambiguous | `12,5` | `refused` | `gold-comma-short` |
| one `,` and four or more digits: a decimal comma | `1,2345` | `1.2345` | `gold-comma-long` |
| two kinds of separator: the last is the decimal point | `1.240,5` | `1240.5` | `gold-two-seps` |
| a sign and a percent | `-4.8%` | `-4.8%` | `gold-sign-percent` |
<!-- /cases -->

## Rules

What the test ignores:

<!-- cases:number-ignored -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| I | no thousands separator | `1,240` | `1240` | pass | `num-thousands-none` |
| I | a space as thousands separator | `1,240` | `1 240` | pass | `num-thousands-space` |
| I | a dot as thousands separator | `1,240` | `1.240` | pass | `num-thousands-dot` |
| I | a decimal comma | `12.5` | `12,5` | pass | `num-decimal-comma` |
| I | a currency sign | `1,240.00` | `$1,240.00` | pass | `num-currency` |
| I | a space before `%` | `-4.8%` | `-4.8 %` | pass | `num-percent-space` |
| I | a minus sign or an en dash for `-` | `-4.8%` | `–4.8%` | pass | `num-minus` |
| I | parentheses around it | `4.8` | `(4.8)` | pass | `num-parens` |
| I | a full stop after it | `5` | `5.` | pass | `num-stop` |
| I | spaced digits in math | `42` | `$$4 2$$` | pass | `num-latex` |
| I | a footnote marker after it | `42` | `<p>42<sup>1</sup></p>` | pass | `num-sup` |
| I | a full stop or comma, then a word | `12.5` | `12.5. Next, 12.5, then` | pass | `num-stop-decimals` |
| I | leaders before a negative | `-4.8` | `Total ....... -4.8` | pass | `num-leaders` |
<!-- /cases -->

What it does not look at, so a wrong output passes:

<!-- cases:number-blind -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| B | letters glued to it | `123` | `x123y` | pass | `num-letters` |
| B | a hyphen after a word is not a sign | `3` | `COVID-3` | pass | `num-word-hyphen` |
| B | any place on the page | `42` | `Page 42 of 100` | pass | `num-context` |
| B | a percent sign the gold lacks | `4.8` | `4.8%` | pass | `num-percent-extra` |
<!-- /cases -->

What it penalizes:

<!-- cases:number-penalized -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| P | a changed digit | `-4.8%` | `-4.9%` | fail: `'-4.8%' not found digit-for-digit` | `num-digit` |
| P | a digit continues it | `123` | `1234` | fail | `num-longer` |
| P | a number before it | `1,240` | `21,240` | fail | `num-longer-before` |
| P | an extra decimal | `12.5` | `12.50` | fail | `num-decimals-extra` |
| P | lost decimals | `1,240.00` | `1,240` | fail | `num-decimals-lost` |
| P | a fraction after a whole gold | `12` | `12.5` | fail | `num-fraction-after` |
| P | a separator and a digit after the decimals | `12.5` | `12.5.7` | fail | `num-tail` |
| P | a dropped leading zero | `0.5` | `.5` | fail | `num-leading-zero` |
| P | a lost sign | `-4.8%` | `4.8%` | fail: `'-4.8%' present but sign lost` | `num-sign-lost` |
| P | an added sign | `4.8` | `-4.8` | fail: `'4.8' present but sign added` | `num-sign-added` |
| P | a lost percent sign | `4.8%` | `4.8` | fail: `'4.8%' present but percent lost` | `num-percent-lost` |
| P | parentheses are not a minus | `-4.8` | `(4.8)` | fail | `num-parens-negative` |
| P | a minus written as a hyphen after a word | `-19` | `COVID-19` | fail | `num-word-sign` |
| P | digits split by a space inside a group | `1,240` | `1 2 40` | fail | `num-split` |
| P | digits split by a superscript | `42` | `<p>4<sup>2</sup></p>` | fail | `num-exponent` |
| P | digits of another script | `42` | `٤٢` | fail | `num-script` |
<!-- /cases -->

## Blind spots

- **Context-free.** The number may be in the wrong row, a footer or another table (case num-context).
- **Letters are not an edge.** `123` is found in `x123y` (case num-letters). A `-` after a letter or digit is a
  hyphen, not a sign: `3` is found in `COVID-3` and `-19` is not found in `COVID-19` (cases num-word-hyphen,
  num-word-sign).
- **Separators are lenient both ways.** `1,240` also accepts `1.240`, which in a decimal-comma locale is 1.24
  (case num-thousands-dot).
- **Percent and parentheses are one-way.** An added percent sign is free; a lost one fails. Parentheses never make
  a number negative (cases num-percent-extra, num-percent-lost, num-parens-negative).

A text arg that holds a number is a different test: it has a digit edge but no separator leniency
([present-text.md](present-text.md#the-digit-edge)).
