# `present` with a latex arg

**Asks:** an equation that renders like this one appears in the page's math, as a whole expression. 3,268 tests;
family text; reads `html`.

This is the one text test that does not fold. Both the gold and each math span of the output are rendered with
KaTeX and compared as sequences of symbols, so spacing, fonts that KaTeX treats alike, and synonyms vanish, while
case and symbols that render differently count.

1. **Math spans** are `$..$`, `$$..$$`, `\(..\)`, `\[..\]`, `<math>` (TeX annotation or MathML), an equation
   environment, and a line that is nothing but LaTeX. Which dollars pair is decided by one reader, shared with the
   text tests ([internals.md](internals.md#the-dollar-reader)).
2. **The match is a whole expression**: no digit, sign or exponent may continue it. Letters beside it are allowed
   (a longer product), and two spans may join when only spaces or block breaks lie between them.
3. **Plain text fallback.** When the gold uses only symbols plain text can write (Greek letters, operators,
   relations, simple scripts) and reads as at least 2 characters, its text reading may also appear in the page
   text: `α = 0.05` for `\alpha=0.05`.
4. **Before rendering**, an unknown command in the output is dropped (up to four distinct ones per span), and so
   are equation tags and labels.

## Rules

What the test ignores:

<!-- cases:latex-ignored -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| I | inline or display, braces | `x^2` | `$$x^{2}$$` | pass | `tex-display` |
| I | `\(..\)` for `$..$` | `x=1` | `\(x=1\)` | pass | `tex-delimiters` |
| I | an equation environment and its tag | `x=1` | `\begin{equation}x=1\tag{3}\end{equation}` | pass | `tex-environment` |
| I | MathML with a TeX annotation | `x=1` | `<math>` with annotation `x=1` | pass | `tex-mathml` |
| I | spacing commands | `x\,y` | `$x y$` | pass | `tex-spacing` |
| I | bold letters | `\mathbf{x}+y` | `$x+y$` | pass | `tex-bold` |
| I | upright letters | `\mathrm{d}x` | `$dx$` | pass | `tex-upright` |
| I | a function name without its backslash | `\sin x` | `$sin x$` | pass | `tex-function` |
| I | `\dfrac` for `\frac` | `\frac{a}{b}` | `$\dfrac{a}{b}$` | pass | `tex-dfrac` |
| I | limits placement | `\sum_{i=1}^{n} x_i` | `$\sum\limits_{i=1}^n x_{i}$` | pass | `tex-limits` |
| I | a synonym for a relation | `\leq` | `$\le$` | pass | `tex-synonym` |
| I | a synonym for an arrow | `\to` | `$\rightarrow$` | pass | `tex-arrow` |
| I | `\varepsilon` for `\epsilon` | `\epsilon` | `$\varepsilon$` | pass | `tex-variant` |
| I | `\widehat` for `\hat` | `\hat{x}` | `$\widehat{x}$` | pass | `tex-hat` |
| I | a minus sign for a hyphen | `a-b` | `$a−b$` | pass | `tex-minus` |
| I | `\left( \right)` for `( )` | `\left(a\right)` | `$(a)$` | pass | `tex-left-right` |
| I | a full stop after the equation | `x+1=0` | `$x + 1 = 0.$` | pass | `tex-full-stop` |
| I | one equation over two blocks | `x+1=0 y=2` | `<p>$x+1=0$</p><p>$y=2$</p>` | pass | `tex-join-blocks` |
| I | a break between displays for `\\` | `a=1 \\ b=2` | `<p>$$a=1$$</p><p>$$b=2$$</p>` | pass | `tex-display-break` |
| I | a middle dot inside `\text{}` | `c=1\,\text{kJ/(kg·K)}` | `$c=1\,\text{kJ/(kg·K)}$` | pass | `tex-text-middot` |
| I | plain text for a plain equation | `\alpha=0.05` | `α = 0.05` | pass | `tex-plain-text` |
| I | a `<sup>` for an exponent | `x^2` | `<p>x<sup>2</sup></p>` | pass | `tex-plain-sup` |
| I | a `<sub>` for an index | `\mathrm{H_2O}` | `<p>H<sub>2</sub>O</p>` | pass | `tex-plain-sub` |
<!-- /cases -->

What it does not look at, so a wrong output passes:

<!-- cases:latex-blind -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| B | letters beside the match | `xy` | `$wxy$` | pass | `tex-letter-beside` |
| B | text before it in the same span | `x+1=0` | `$y: x+1=0$` | pass | `tex-prefix` |
| B | an unknown command | `x+y` | `$x+\foo y$` | pass | `tex-unknown-macro` |
| B | four unknown commands | `x+y` | `$x+y\fooa\foob\fooc\food$` | pass | `tex-unknown-four` |
| B | a raised dot for a decimal point | `2.5` | `$2\cdot 5$` | pass | `tex-dot` |
| B | digits just after the span | `x^2` | `$x^2$.5` | pass | `tex-outside-span` |
| B | a bare line read as LaTeX | `x^2` | `<p>x^23</p>` | pass | `tex-bare-line` |
| B | an equation split over two cells | `x=1` | `<table><tr><td>$x</td><td>=1$</td></tr></table>` | pass | `tex-split-cells` |
<!-- /cases -->

What it penalizes:

<!-- cases:latex-penalized -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| P | letter case | `x^2` | `$X^2$` | fail: `equation not found (4 symbols; the output's math has 4)` | `tex-case` |
| P | a different exponent | `x^2` | `$x^3$` | fail | `tex-symbol` |
| P | blackboard, script or fraktur dropped | `\mathbb{R}` | `$R$` | fail | `tex-blackboard` |
| P | `\overline` for `\bar` | `\bar{x}` | `$\overline{x}$` | fail | `tex-bar` |
| P | `\cdot` for `\times` | `a\times b` | `$a\cdot b$` | fail | `tex-times` |
| P | `\sum` for `\Sigma` | `\Sigma` | `$\sum$` | fail | `tex-sum` |
| P | `\varrho` for `\rho` | `x=\rho` | `$x=\varrho$` | fail | `tex-varrho` |
| P | `\epsilon` for `\in` | `x\in A` | `$x \epsilon A$` | fail | `tex-epsilon-in` |
| P | an extra term | `E=mc` | `$E=mc^2$` | fail | `tex-term` |
| P | a sign before it | `x+1=0` | `$-x+1=0$` | fail | `tex-sign` |
| P | a digit continues a number | `x=1` | `$x=10$` | fail | `tex-number` |
| P | a digit continues the decimals | `1.5` | `$1.55$` | fail | `tex-decimals` |
| P | prose between two spans | `a+b` | `$a$ plus $b$` | fail | `tex-prose` |
| P | a fraction written with a slash | `\frac{a}{b}` | `$a/b$` | fail | `tex-fraction-text` |
| P | a decimal comma | `2.5` | `$2{,}5$` | fail | `tex-decimal-comma` |
| P | an en dash for a minus | `a-b` | `$a–b$` | fail | `tex-en-dash` |
| P | a Unicode bold letter | `\mathbf{x}+1` | `$𝐱+1$` | fail | `tex-math-bold` |
| P | five unknown commands | `x+y` | `$x+y\fooa\foob\fooc\food\fooe$` | fail | `tex-unknown-five` |
| P | no math and not plain | `\alpha` | `alpha` | fail: `no math in the output` | `tex-no-math` |
| P | one symbol as text | `\Sigma` | `Σ` | fail | `tex-one-symbol` |
| P | plain text slightly off | `\alpha=0.05` | `α = 0.050` | fail: `no math in the output` | `tex-plain-near` |
| P | the same text inside prose | `x^2` | `so x^23 grows` | fail | `tex-bare-prose` |
| P | two displays joined by prose | `a=1 \\ b=2` | `$$a=1$$ and $$b=2$$` | fail | `tex-displays-prose` |
<!-- /cases -->

## Blind spots

- **Letters around the match are free** (case tex-letter-beside), and so is a prefix in the same span (case
  tex-prefix).
- **Unknown commands are dropped**, so an invented command costs nothing (case tex-unknown-macro).
- **A raised dot and a decimal point are one symbol**: `2.5` is found in `$2\cdot 5$` (case tex-dot).
- **Text after a closing dollar is outside the span**: `x^2` is found in `$x^2$.5` (case tex-outside-span).
- **A bare line is read as LaTeX, a line with prose is not.** `x^2` is found in a line `x^23` but not in
  `so x^23 grows` (cases tex-bare-line, tex-bare-prose).
- **The plain-text fallback can join cells**: `x=1` is found in `$x` and `=1$` written in two cells (case
  tex-split-cells).
- **Case counts here and not in text tests.** The same `x^2` written as a text arg would pass `X^2`.

The why reads `equation not found (N symbols; the output's math has M)`, or `no math in the output`. After the
plain-text fallback misses, the why is still the KaTeX one, so `no math in the output` can appear on a page whose
text holds the equation slightly wrong (case tex-plain-near).
