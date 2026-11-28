# The reader

The reader turns an output's html into one document, and a gold string into tokens by the same rules. It lives
in `omni_parse_bench/reader.py`. The rules below change what a test can see, so each is a named switch
(`omni_parse_bench/switches.py`, `OPB_SWITCHES`): a regrade can turn one on or off and count the verdicts it
moves. Every switch is off until the rules ship together; with the switches off the scorer reads as it did.

| switch | rule |
|---|---|
| `visibility` | Text the page hides is not read: `hidden`, an inline style `display:none` or `visibility:hidden`, `<template>`, `<noscript>`, `<input type=hidden>`, and everything inside them. `aria-hidden` text is printed, so it is read. Stylesheets are not evaluated: a class that hides text is read as visible. |
| `alt_text_out` | Image alt text (an `alt` attribute, a markdown `![..](..)`) is not page text. A figure contributes its caption. |
| `cell_windows` | A window of text stops at a table cell: two cells never form one window, and a cell never joins text outside every table. Paragraphs and lines do not stop one. |
| `sup_exponent` | A `<sup>` (or a Unicode superscript) right after a digit is an exponent and part of the number: `10<sup>2</sup>` and `10²` are both `10^2`, never `10` and a footnote mark. |
| `tokens` | Text is read as tokens at grapheme-cluster edges (below), not as characters. |
| `text_fold` | The Id to Text fold (compatibility forms, typography, invisible characters, leaders, look-alike symbols) runs between the quantity scan and word tokenization, so Text tokens are fixed once per output. A quantity keeps its spelling through it. |

Today the scorer's text views consult `visibility` and `alt_text_out`. The other three are rules of the reader
itself, used by the steps that follow.

## One parser

One HTML5 parser (the WHATWG algorithm, scripting on) reads every output, so malformed html has one reading.
The text is kept in blocks (a paragraph, a heading, a list item, a table cell, a caption, a math element), each
block in lines (split at `<br>`), each line in tokens. A table cell is its own block, addressed by (table, row,
column). Every token keeps the inline markup it sits in (`b`, `i`, `sup`, ...).

## Tokens

Tokens are fixed for an output: no later step splits or joins one.

| class | what | example |
|---|---|---|
| `Word` | a run of letters (and digits glued to them) in a script that writes spaces; one grapheme cluster in Han, kana, Hangul, Thai, Lao, Khmer, Myanmar and Tibetan | `Total`, `self-aware`, `don't`, `x123y`, `税`, `กี` |
| `Qty` | a quantity | `-1,240.5`, `45%`, `$45`, `10kg`, `3万`, `1/2`, `1.2.3`, `10²` |
| `Sym` | any other visible character; a hyphen or apostrophe between two letters is not one: it stays in the word | `:`, `(`, `☒` |
| `Space` | the gap between two tokens on a line | |
| `Break` | the boundary between two lines or blocks | |
| `Mark` | a footnote marker: a `<sup>` of 1 to 3 digits or `* † ‡ § ¶ #`, or `[n]` and `[^n]`, not right after a digit | `¹` in `Smith¹` |
| `Wrap` | in an output only: a hyphen at the end of a line, directly after a letter, before a lowercase letter; the line break is part of it | `self-⏎aware` |
| `Math` | a `<math>` element, with its TeX source | |

A space between two Han or kana characters is not content, and the reader drops it. ZWJ and ZWNJ stay inside
the word they sit in. A combining mark belongs to its base. A boundary between two script classes is an edge,
so `iPhone手机` is `iPhone`, `手`, `机`.

## Quantities

A quantity is read once, on the raw characters, before any fold:

- a sign belongs to it when it stands right before the digits and what comes before it is a start of line, a
  space, an opening bracket, `=`, an operator or a CJK character. After a letter or a digit with no space it is
  a `Sym`: `10-12` is `10`, `-`, `12`, and `x-5` is `x`, `-`, `5`. A spaced sign (`- 0.756`) is a sign when no
  quantity or letter comes before it on the line;
- digits of one script, with `.`, `,`, `'` or a thin space between two digits; `1,000`, `1000`, `1,5` and `1.5`
  are four different quantities, because equality is by spelling and the reader does not guess a locale;
- an exponent: `e` and digits, a `<sup>` of digits, or Unicode superscripts, written `^` in its canonical
  spelling (`10²` and `10<sup>2</sup>` agree; `1e3` does not equal `10^3`);
- a suffix glued to the digits: `%`, `‰`, a currency sign, or an entry of `QTY_SUFFIX` (SI units with their
  prefixes, common units, and magnitudes such as `k`, `M`, `万`). Letters glued to digits that are not in the
  table make the whole run a `Word` (`10kgs`, `A4`, `COVID19`). Case is kept: `1M` is not `1m`;
- a fraction or date: two quantities joined by `/` with no spaces.

A unit with a space (`10 kg`) is a quantity and a word; a unit is protected only when glued to its number.
CJK numerals (`三万`) are words.

## Spaced suffixes and unit exponents (switches `qty_spaced_suffix`, `unit_exponent_dash`)

- `qty_spaced_suffix`: one ordinary space between a number and a listed unit or magnitude suffix is part of the quantity, and its spelling drops it: `2100 万`, `2100万`, `20 kg` and `20kg` are one spelling. Two spaces, a word that merely starts like a suffix (`20 kgs`) and a single ASCII letter after a space (`763791104 b Account`, `5 s`) are not.
- `unit_exponent_dash`: a minus after a unit word of the suffix list, with no digit before the word, perhaps with one space or a `{` (`^{`) between (`kg -1`, `kg{-1}`, `kg^{-1}`), is a `Sym` as in `kg-1`, never the sign of a number. `in` is left out (`in -5` is a word and a number).

## Leading-dot decimals and math spans (switches `leading_dot`, `math_spans`)

- `leading_dot`: a decimal written without its integer part (`.5`, `-.5`, `$.50`, `.5kg`) is one `Qty`, scanned at the same places as any quantity (after a space, a bracket, the start of a line; not after a letter or digit, so `x.5` is `x`, `.`, `5`). Equality is by spelling: `.5` is not `0.5`, and a budget can no longer drop its point.
- `math_spans`: a math span written in the text of an output (`$..$` and `$$..$$` as `mathspans` pairs them, so a price stays text, and `\(..\)` and `\[..\]`) is one `Math` token carrying its source, as a `<math>` element is, and compared as the text it renders (`$\alpha$` reads `α`, `$x^2$` reads `x2`, as the text view writes them; its delimiters and TeX commands are not text, and math too long or too spaced to read is compared as written). A span that crosses a change of markup or a line is left as text. The leading-dot rule also takes a spaced sign (`− .5`) and a fraction (`1/.5`) as one quantity.
