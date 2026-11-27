# `present` with a latex arg

**Asks:** an equation that renders like this one appears in the page's math, as a whole expression. 3,268 tests;
family text; reads `html`.

This is the one text test that does not fold. Both the gold and each math span of the output are rendered with
KaTeX and compared as sequences of symbols, so spacing, fonts that KaTeX treats alike, and synonyms vanish, while
case and symbols that render differently count.
Within a superscript, `\top`, `\intercal` and plain `T` compare alike, including in `A^{-T}`. A T in
blackboard, script or fraktur remains distinct, as do indexed symbols such as `T_1` and uses outside a
superscript. Two adjacent single
bars compare as a double bar, so `||x||` and `\lVert x\rVert` match. This also folds the touching bars in
`|a||b|`, allowing a match with `|a\|b|` even though those expressions can have different meanings.

- `\bar` and `\overline` match over one symbol; `\vec` and `\overrightarrow` match over one letter.
  Accents over multiple symbols remain distinct.
- Short and long arrows match in each direction: →/⟶, ↦/⟼, ←/⟵, ⇒/⟹, ⇐/⟸, ⇔/⟺ and ↔/⟷.
- Binary and big operator glyphs match when they carry scripts: ∪/⋃, ∩/⋂, ⊕/⨁, ⊗/⨂, ⊙/⨀,
  ∨/⋁, ∧/⋀ and ⊔/⨆. Σ/∑ and Π/∏ match only with an explicit lower limit containing =, ≠, ∈, ∉, ≤ or ≥.
  Their scripts and surrounding structure still have to match. Ordinary binary operators and indexed
  covariance symbols such as `\Sigma_{xy}` stay distinct from big operators.
- The triangle forms ⊲/◃ and ⊳/▹, and the subset forms ⊊/⫋, ⊋/⫌, ⊆/⫅ and ⊇/⫆ match.
  ⊴ and ⊵ stay distinct; no smaller counterparts are supplied by KaTeX for these forms.
- The bullet operator ∙ and middle dot · stay distinct. `\mid`, `\vert` and `|` already match, as do
  a degree sign and `^\circ`.
- Double-bracket glyphs ⟦ and ⟧ match pairs of square brackets, as in `W⟦z⟧` and `W[[z]]`.
  A pair remains distinct from a single bracket, though the matcher can find a single-bracket expression
  nested inside a pair.
- Explicitly sized angle fences (`\left<...\right>`, `\bigl<...\bigr>`) and the Unicode angle
  brackets 〈 〉 and 〈 〉 match ⟨ ⟩. Bare `<` and `>` remain relations.
- Unicode mathematical letters are normalized to their base letter while retaining double-struck, script
  and fraktur fonts; bold and italic are dropped as with the corresponding LaTeX fonts. For example ℝ
  matches `\mathbb{R}`, not plain R. `\mathds` is read as `\mathbb` and `\mbox` as `\text`.
- Unicode prime marks ′, ″ and ‴ match one, two and three LaTeX primes. A raw `%` in math reads as `\%`
  when that renders; otherwise the original TeX is tried.
- ϱ/ρ and ϰ/κ match; ϖ (`\varpi`) is drawn differently from π and stays distinct. ∬ and ∭ match two and three consecutive ∫ symbols.
- Top-level `\\` in display math marks a row, as in an aligned or gathered environment. Empty superscripts
  and subscripts are dropped. If the row-aware match fails, the matcher also tries the earlier reading that
  ignored top-level row breaks; similarly, it can retry the earlier reading of a TeX percent comment.
- The plain-text fallback uses the same arrow, triangle and subset glyph aliases as math.
- **Math nested more than 64 groups deep is not read.** KaTeX reads nested groups (`{`, `\left`, `\begin`) by
  recursion, and a span that nests thousands of them (or loops thousands of `\dots`) overran the stack of the
  embedded engine and killed the whole scoring process. A span nested deeper than `equations.MAX_NESTING` (64)
  now renders as no math, so a test whose equation is on the page's other spans still passes, and one that
  needed that span fails with `no math in the output` (case tex-too-deep). A gold equation that deep is refused
  as one that does not render. A run of unbraced commands (`\sqrt\sqrt...`, `\dots\dots...`) is bounded by the
  engine's own stack limit (256 KB), with the same result; that limit is set when the first `MiniRacer` of the
  process starts, so a program that started its own before scoring keeps V8's default and only the 64-group
  bound protects it.

These glyph folds do not infer mathematical meaning: for example a long arrow can match a short arrow, and
an explicitly limited Σ can match a summation sign. Angle brackets stay distinct from inequality signs, and ℓ from `l`.
Script, double-struck and fraktur letters, Greek and Latin lookalikes, check and breve accents, = and ≡,
1 and 𝟙, ϖ and π, and Δ and △ stay distinct.

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
| I | a transpose in another form | `x^\top A x` | `$x^T A x$` | pass | `tex-transpose` |
| I | a transpose inside a superscript | `A^{-\top}` | `$A^{-T}$` | pass | `tex-transpose-composite` |
| I | two single bars for a double bar | `\lVert x\rVert` | `$\|\|x\|\|$` | pass | `tex-norm-bars` |
| I | a double bracket in two spellings | `W\llbracket z\rrbracket` | `$W[[z]]$` | pass | `tex-double-bracket` |
| I | an explicitly sized angle fence | `\langle x\rangle` | `$\left<x\right>$` | pass | `tex-angle-fence` |
| I | a Unicode double-struck letter | `\mathbb{R}` | `$ℝ$` | pass | `tex-letterlike` |
| I | a Unicode bold letter | `\mathbf{x}+1` | `$𝐱+1$` | pass | `tex-math-bold` |
| I | Unicode and LaTeX primes | `x''` | `$x″$` | pass | `tex-primes` |
| I | a raw percent sign in one-line math | `5\%+3` | `$5%+3$` | pass | `tex-percent` |
| I | a rho variant | `x=\rho` | `$x=\varrho$` | pass | `tex-greek-variant` |
| I | two integrals for a double integral | `\iint f` | `$\int\!\int f$` | pass | `tex-multiple-integrals` |
| I | display rows without an environment | `\begin{aligned}a&=b\\c&=d\end{aligned}` | `$$a=b\\c=d$$` | pass | `tex-top-level-rows` |
| I | an empty script | `x` | `$x^{}$` | pass | `tex-empty-script` |
| I | mathds for blackboard font | `\mathbb{R}` | `$\mathds{R}$` | pass | `tex-mathds` |
| I | mbox for text | `\text{hi}` | `$\mbox{hi}$` | pass | `tex-mbox` |
| I | a bar or overline on one symbol | `\bar{x}` | `$\overline{x}$` | pass | `tex-bar` |
| I | a short or long arrow on one letter | `\vec{x}` | `$\overrightarrow{x}$` | pass | `tex-vector` |
| I | a longer arrow | `a\to b` | `$a\longrightarrow b$` | pass | `tex-long-arrow` |
| I | a big union with a limit | `\cup_i A_i` | `$\bigcup_i A_i$` | pass | `tex-big-union` |
| I | a summation sign with an explicit lower limit | `\Sigma_{i=1}^n x_i` | `$\sum_{i=1}^n x_i$` | pass | `tex-sum` |
| I | a triangle variant | `a\lhd b` | `$a\triangleleft b$` | pass | `tex-triangle` |
| I | a subset variant | `A⊆B` | `$A⫅B$` | pass | `tex-subset` |
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
| B | adjacent absolute-value bars for a double bar | `\|a\|\|b\|` | `$\|a\\|b\|$` | pass | `tex-adjacent-bars` |
| B | digits just after the span | `x^2` | `$x^2$.5` | pass | `tex-outside-span` |
| B | a bare line read as LaTeX | `x^2` | `<p>x^23</p>` | pass | `tex-bare-line` |
| B | an equation split over two cells | `x=1` | `<table><tr><td>$x</td><td>=1$</td></tr></table>` | pass | `tex-split-cells` |
<!-- /cases -->

What it penalizes:

<!-- cases:latex-penalized -->
| | difference | gold | output | verdict | case |
|---|---|---|---|---|---|
| P | letter case | `x^2` | `$X^2$` | fail: `equation not found (4 symbols; the output's math has 4)` | `tex-case` |
| P | math nested more than 64 groups deep is not read | `x` | `$\frac{1}{\frac{1}{…x…}}$`, 65 levels | fail | `tex-too-deep` |
| P | a different exponent | `x^2` | `$x^3$` | fail | `tex-symbol` |
| P | a single bracket for a double bracket | `[[z,w]]` | `$[z,w]$` | fail | `tex-single-bracket` |
| P | blackboard, script or fraktur dropped | `\mathbb{R}` | `$R$` | fail | `tex-blackboard` |
| P | a top symbol outside a superscript for T | `\top \land p` | `$T \land p$` | fail | `tex-top-logic` |
| P | a blackboard T for a transpose | `A^T` | `$A^{\mathbb T}$` | fail | `tex-transpose-font` |
| P | a big union without a limit | `A\cup B` | `$A\bigcup B$` | fail | `tex-binary-union` |
| P | a summation sign for indexed sigma | `\Sigma_{xy}` | `$\sum_{xy}$` | fail | `tex-sigma-variable` |
| P | a bullet operator for a middle dot | `a\cdot b` | `$a\bullet b$` | fail | `tex-bullet-operator` |
| P | a bar on one symbol for an overline on two | `\bar{x}` | `$\overline{xy}$` | fail | `tex-long-bar` |
| P | a vector arrow over two symbols | `\vec{xy}` | `$\overrightarrow{xy}$` | fail | `tex-long-vector` |
| P | angle brackets for inequality signs | `\langle x,y\rangle` | `$<x,y>$` | fail | `tex-angle-relation` |
| P | script ell for Latin l | `ℓ` | `$l$` | fail | `tex-ell` |
| P | `\cdot` for `\times` | `a\times b` | `$a\cdot b$` | fail | `tex-times` |
| P | `\epsilon` for `\in` | `x\in A` | `$x \epsilon A$` | fail | `tex-epsilon-in` |
| P | an extra term | `E=mc` | `$E=mc^2$` | fail | `tex-term` |
| P | a sign before it | `x+1=0` | `$-x+1=0$` | fail | `tex-sign` |
| P | a digit continues a number | `x=1` | `$x=10$` | fail | `tex-number` |
| P | a digit continues the decimals | `1.5` | `$1.55$` | fail | `tex-decimals` |
| P | prose between two spans | `a+b` | `$a$ plus $b$` | fail | `tex-prose` |
| P | a fraction written with a slash | `\frac{a}{b}` | `$a/b$` | fail | `tex-fraction-text` |
| P | a decimal comma | `2.5` | `$2{,}5$` | fail | `tex-decimal-comma` |
| P | an en dash for a minus | `a-b` | `$a–b$` | fail | `tex-en-dash` |
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
- **Adjacent bars are a double bar** even between absolute values: `|a||b|` is found in `$|a\|b|`
  (case tex-adjacent-bars).
- **Text after a closing dollar is outside the span**: `x^2` is found in `$x^2$.5` (case tex-outside-span).
- **A bare line is read as LaTeX, a line with prose is not.** `x^2` is found in a line `x^23` but not in
  `so x^23 grows` (cases tex-bare-line, tex-bare-prose).
- **The plain-text fallback can join cells**: `x=1` is found in `$x` and `=1$` written in two cells (case
  tex-split-cells).
- **Case counts here and not in text tests.** The same `x^2` written as a text arg would pass `X^2`.

The why reads `equation not found (N symbols; the output's math has M)`, or `no math in the output`. After the
plain-text fallback misses, the why is still the KaTeX one, so `no math in the output` can appear on a page whose
text holds the equation slightly wrong (case tex-plain-near).
