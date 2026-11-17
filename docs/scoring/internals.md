# Internals: how an output becomes the text the tests compare

This page is for readers who want the mechanics behind the test pages. Each table is generated from cases that
CI runs, as on the other pages ([README](README.md#how-to-read-the-tables)).

## From markdown to html

A system answers with `html` (and `blocks` for layout). A provider that returns markdown has it converted to html
by the harness (`markdown.to_html`) before scoring, so the scorer only sees html. Html a system writes itself is
not converted: a literal `**x**` in html stays visible text.

<!-- cases:internals-markdown -->
| rule | input | reads as | case |
|---|---|---|---|
| emphasis and code lose their markup | `` **Bold** *it* ~~del~~ `code` `` | `bold it del code` | `md-emphasis` |
| a list marker stays as text | `29. Item\n\n- bullet` | `29. item - bullet` | `md-list` |
| an image becomes its description | `![chart of sales](x.png)` | `chart of sales` | `md-image` |
| a pipe table with a separator row is a table | `\| A \| B \|\n\|---\|---\|\n\| 1 \| 2 \|` | `A \| B \| 1 \| 2` | `md-table` |
| without the separator row it is not | `\| A \| B \|\n\| 1 \| 2 \|` | `no table` | `md-no-separator` |
| amounts beside math stay in their cells | `\| a \| b \| c \|\n\|---\|---\|---\|\n\| $5 \| x_1 \| US$6 \|` | `a \| b \| c \| $5 \| x_1 \| US$6` | `md-amounts` |
| a math span may cross a pipe | `\| a \| b \|\n\|---\|---\|\n\| $x_1 \| y$ \|` | `a \| b \| $x_1 \| y$ \| (empty)` | `md-math-cell` |
<!-- /cases -->

## The text view

The text tests read the html's *text view* (`views.html(output).text`). `table_cell` parses the html into a grid
and reads each cell's text the same way; the equation test takes its dollar and bracket spans from the text view
and MathML and environments from the html. The text view is the html with these rewrites, in order.

1. `<math>` becomes `$..$` (from its TeX annotation; MathML without one reads as its text).
2. Each item of an ordered list gets its number, from the list's `start`.
3. Checkboxes become `☒` or `☐`; an `<input>` shows its value.
4. An image becomes its `alt` text. `repeat` reads a second view, *seen*, without it.
5. Comments, `<script>`, `<style>`, `<head>` and `<title>` are removed.
6. `<sup>` becomes a space, so a footnote marker never joins the number before it; `</sup>` becomes a space
   before a number (a digit, or a sign or point and a digit), so a marker never joins the number after it.
7. Block tags (paragraphs, cells, rows, lists, headings) end a line with a block break, which fold reads as a
   space but which stops a leader run; `<br>` and other tags become a space or nothing, so `<sub>` text joins
   its word.
8. Entities are unescaped.

<!-- cases:internals-views -->
| rule | input | reads as | case |
|---|---|---|---|
| tags are dropped | `<p><b>Total</b> <i>Due</i></p>` | `total due` | `view-tags` |
| `<sub>` text joins its word | `<p>H<sub>2</sub>O</p>` | `h2o` | `view-sub` |
| `<sup>` is set apart by a space | `<p>1,240<sup>1</sup></p>` | `1,240 1` | `view-sup` |
| so is `</sup>` before a number | `<p><sup>1</sup>-4.8 and x<sup>2</sup>y</p>` | `1 -4.8 and x 2y` | `view-sup-before` |
| an ordered list item gets its number | `<ol start='3'><li>Item</li></ol>` | `3. item` | `view-ol` |
| an input shows its value | `<p>Name: <input value='Bob'></p>` | `name: bob` | `view-input` |
| a checkbox is a box glyph | `<p><input type=checkbox checked> Yes</p>` | `☒ yes` | `view-checkbox` |
| scripts, styles, comments and `<head>` are not text | `<head><title>T</title></head><script>x</script><!-- c --><p>Body</p>` | `body` | `view-hidden` |
| a table reads cell by cell, row by row | `<table><tr><td>A</td><td>B</td></tr><tr><td>C</td></tr></table>` | `a b c` | `view-cells` |
| an image reads as its description | `<p>See</p><img alt='Chart'>` | `see chart` | `view-alt` |
| `repeat` reads the text without descriptions | `<p>See</p><img alt='Chart'>` | `see` | `view-seen` |
<!-- /cases -->

A table cell is read the same way, on the cell alone, and uses its `alt` text only when it has no other text.

## Fold

`normalize.fold` puts both the gold and the page text in one form before any text comparison. The steps run in
this order: math spans read as text; a line-end hyphen before a lowercase letter joined; a superscript digit after
a digit set apart; compatibility forms unified (NFKC) and invisible characters removed; checkboxes unified;
footnote brackets and line-start bullets removed; leaders removed (runs of 3 or more dots, ideographic full stops
`。` among them, even though full-width punctuation is made ASCII only later); dash, quote, space and arrow
families unified, then two single quotes in a row read as a double quote (TeX's ``` `` ``` and `''`, or a mixed
pair `'’`); full-width punctuation made ASCII; a decimal middle dot made a point; spacing collapsed;
lowercase.

White space may sit inside a leader run, and a `<br>` or a newline is white space. A block break (the end of a
paragraph, cell or other block tag) is not: a leader run stops at it. For a line-end hyphen a block break is a
line break like any other, so the hyphen joins across it: outputs that write one paragraph per printed line
(`<p>Head-</p><p>quarters</p>`) rely on it. A text that ends in a hyphen before a paragraph that starts with
a lowercase letter is then read joined (`well-` before `known` reads `wellknown`).

<!-- cases:internals-fold -->
| rule | input | reads as | case |
|---|---|---|---|
| math is read as text | `$c_{\text{MC}}$ and $$2 . 5 5$$` | `cmc and 2.55` | `fold-math` |
| a line-end hyphen before a lowercase letter joins | `develop- ers, R- M` | `developers, r- m` | `fold-hyphen` |
| a block break is a line break for a hyphen: it joins, as a `<br>` does | `<p>Head-</p><p>quarters</p><p>develop-<br>ers</p>` | `headquarters developers` | `fold-hyphen-block` |
| a superscript digit after a digit is set apart | `1,240¹` | `1,240 1` | `fold-superscript` |
| compatibility forms (ligatures, full width, sub- and superscripts) | `ﬁnal １２ m² H₂O ½ №` | `final 12 m2 h2o 1/2 no` | `fold-nfkc` |
| zero-width and soft hyphen characters vanish | `a` U+200B `b a` U+00AD `b` | `ab ab` | `fold-invisible` |
| checkboxes become ☒ or ☐ | `[x] Yes [ ] No ☑ ok` | `☒ yes ☐ no ☒ ok` | `fold-checkbox` |
| a bracketed footnote marker becomes a spaced number | `Smith[1] and [12] Jones` | `smith 1 and 12 jones` | `fold-footnote` |
| a bullet starting a line goes; one inside a line stays | `• one • two` | `one • two` | `fold-bullet` |
| runs of 3 or more dots, dashes, `_`, `=`, `*` become a space | `Name ........ 5 a --- b ___ c *** d` | `name 5 a b c d` | `fold-leaders` |
| a leader run stops at a block break; a `<br>` does not stop it | `<p>a _</p><p>__</p><p>b _<br>__ c</p>` | `a _ __ b c` | `fold-leaders-block` |
| a run of 3 or more ideographic full stops is a leader too | `目次。。。。5 第一章｡｡｡8` | `目次 5 第一章 8` | `fold-leader-cjk` |
| a dash run before a spaced digit keeps its sign | `Revenue ....... -4.8` | `revenue -4.8` | `fold-leader-sign` |
| two underscores are not a leader | `Name: __` | `name: __` | `fold-blank` |
| dash, quote, space and arrow families | `a–b a−b it’s «hi» a`(nbsp)`b ⇒` | `a-b a-b it's "hi" a b →` | `fold-typography` |
| then two single quotes of any mix are a double quote, as TeX writes one | `` ``Yes'' '’No’' `` | `"yes" "no"` | `fold-tex-quote` |
| full-width punctuation becomes ASCII | `日本語。３％` | `日本語.3%` | `fold-cjk` |
| a middle dot between digits is a decimal point; `⋅` is not | `2·3 2⋅3` | `2.3 2⋅3` | `fold-middot` |
| case is folded, but no letter is changed into others | `STRASSE straße Α` | `strasse straße α` | `fold-case` |
| kept apart: diacritics, punctuation, currency, `**` | `naïve Mr. $5.00 **x**` | `naïve mr. $5.00 **x**` | `fold-kept` |
<!-- /cases -->

**Squeeze** is fold with every space removed. `present` and `order` try it once when the folded comparison fails,
and `table_cell` compares cells both ways. It runs after fold, so the hyphen rule and the math reading still see
the spaces.

## The dollar reader

A `$` is either a math delimiter or a currency sign. One reader (`omni_parse_bench/mathspans.py`) decides which
for both the text tests and the equation test. Its rules:

- a single-dollar span stays on one line (a block tag ends it, a `<br>` does not); `$$..$$` may span lines;
- neighbouring dollars pair, so the words between two spans never become a span;
- no dollar span holds a `\(..\)` span, or part of one: the dollars on either side of it are left over or pair
  elsewhere, so both kinds of test read the `\(..\)` as its own span. A `\(` whose `\)` comes only after a dollar
  is a stray, and the dollars pair as if it were not there;
- a dollar left over is currency; a dollar before a digit is the cheapest to leave over, and on a tie the earliest
  is left;
- a pair is math when its body has LaTeX markup, is one to three letters, is spaced digits, or is plain symbols
  touching both dollars; it is not math when it is two prices, a form blank (`__`) or prose (three bare words);
- a span longer than 120 characters or with more than 4 rendered spaces is math, but left as written;
- padding (`$ x $`) counts as math only on a page that pads its math elsewhere.

<!-- cases:internals-dollars -->
| rule | input | reads as | case |
|---|---|---|---|
| neighbouring dollars pair | `$a$ and $b$` | `a and b` | `dollar-pairs` |
| a price is a stray dollar | `costs $5 and $x^2$` | `costs $5 and x2` | `dollar-price` |
| two prices are not a span | `$92,000; Net +$60,000` | `$92,000; net +$60,000` | `dollar-two-prices` |
| on a tie the earlier dollar is the stray | `Cost $ and $ x $ now` | `cost $ and x now` | `dollar-tie` |
| a single-dollar span stops at a block | `<p>$a</p><p>b$</p>` | `$a b$` | `dollar-block` |
| a `<br>` does not stop it | `<p>$x<br>_1$</p>` | `x1` | `dollar-br` |
| plain symbols hugging their dollars are math | `$p < 0.05$` | `p < 0.05` | `dollar-hug` |
| padded symbols are not | `$p < 0.05 $` | `$p < 0.05 $` | `dollar-padded` |
| a padded word is math on a page that pads its math | `$ ab $ and $ x_1 $` | `ab and x1` | `dollar-pad-page` |
| but not on its own | `$ ab $` | `$ ab $` | `dollar-pad-alone` |
| three bare words are prose, not math | `$the quick brown fox$` | `$the quick brown fox$` | `dollar-prose` |
| a dollar written as an entity is a dollar | `&#36;x^2&#36;` | `x2` | `dollar-entity` |
| an escaped dollar is not a delimiter | `x \$5 and \$6` | `x \$5 and \$6` | `dollar-escaped` |
| a `\(..\)` is not inside a dollar span | `$5.00 \(a_2\) $` | `$5.00 a2 $` | `dollar-paren` |
<!-- /cases -->

## The edit budget

`max_diffs` counts character edits on the folded gold, and must be below its length. The three text matchers
count edits differently:

- `present` passes when the best-matching window scores at least `1 - max_diffs / length` (a rapidfuzz partial
  ratio). For substituted letters this is true edit distance. It forgives more in two ways. Two swapped letters
  count as one edit. And an inserted letter can cost less than one edit, as can a letter deleted at the end of
  the gold or from a page that holds only the gold: three letters inserted into `lorem ipsum dolor sit amet`
  pass with `max_diffs` 2.
- `order` uses true edit distance (fuzzysearch), so two swapped letters count as two.
- `table_cell` compares whole cells with a ratio over both lengths, so an inserted character costs half an edit.

Measured on random strings (the figures come from the installed rapidfuzz and fuzzysearch):

<!-- cases:internals-edits -->
| rule | input | reads as | case |
|---|---|---|---|
| 1 random edit, no adjacent swap, `max_diffs` 1 | 4,000 random needles, seed 1 | `3050 cases, 0 passed above budget, 0 failed within budget` | `edits-1` |
| 1 random edit, with adjacent swap, `max_diffs` 1 | 4,000 random needles, seed 1 | `1021 cases, 820 passed above budget, 0 failed within budget` | `edits-1-swap` |
| 2 random edits, no adjacent swap, `max_diffs` 2 | 4,000 random needles, seed 1 | `2229 cases, 0 passed above budget, 0 failed within budget` | `edits-2` |
| 2 random edits, with adjacent swap, `max_diffs` 2 | 4,000 random needles, seed 1 | `1782 cases, 1016 passed above budget, 0 failed within budget` | `edits-2-swap` |
<!-- /cases -->

## The hyphen rule

A word broken at a line end (`develop- ers`) is joined by fold when a lowercase letter follows, in every test.
`present` alone also accepts a hyphenated compound broken the same way (`self- aware` for `self-aware`): when its
other comparisons fail, it tries the match with each such hyphen kept or dropped, without spending edits.

<!-- cases:internals-hyphen -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| I | `present`: kept or dropped hyphen, either reading | `self-aware` | `self- aware` | pass | `hyph-present` |
| P | `order`: the hyphen is dropped | `self-aware` before `ZZZ` | `<p>self- aware</p><p>ZZZ</p>` | fail | `hyph-order` |
| P | `repeat`: the hyphen is dropped | `self-aware` ×1 | `self- aware` | fail | `hyph-repeat` |
| P | `table_cell`: the hyphen is dropped | `self-aware` | `<table><tr><td>self- aware</td></tr></table>` | fail | `hyph-cell` |
| P | an unspaced hyphen is never optional | `develop-ers` | `developers` | fail | `hyph-unspaced` |
<!-- /cases -->

## What a gold must be to load

The dataset is checked when it is read; a test that breaks these rules is refused, so none is in the dataset.

<!-- cases:internals-loader -->
| rule | input | reads as | case |
|---|---|---|---|
| `max_diffs` must be below the folded length | present: content `ab` (md 2) | `refused` | `load-md-max` |
| one edit on two characters | present: content `ab` (md 1) | `loads` | `load-md-ok` |
| `repeat` takes no edits | repeat: content `ab` (md 1) | `refused` | `load-repeat-md` |
| the args of one test share `max_diffs` | order: before `abc` (md 1), after `abc` (md 0) | `refused` | `load-shared-md` |
| a gold that folds to nothing | present: content U+200B (md 0) | `refused` | `load-empty` |
| a latex gold that renders nothing | present: content `\quad` | `refused` | `load-latex-empty` |
<!-- /cases -->

A number gold must read as one number ([present-number.md](present-number.md#how-the-gold-is-read)).
