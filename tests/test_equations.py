"""The equation comparison: what an equation renders to, not how its LaTeX is written."""
from __future__ import annotations

import pytest

from omni_parse_bench import equations, markdown, views
from omni_parse_bench.scorers.unit_tests import runners


@pytest.mark.parametrize("test, output", [
    (r"\frac{a}{b} \leq c", r"<p>$\dfrac{a}{b} \leqslant c$</p>"),
    (r"f: A \to B", r"<p>\(f\colon A \rightarrow B\)</p>"),
    (r"\left\{ \begin{aligned} x &= 1 \\ y &= 2 \end{aligned} \right.",
     r"$$\begin{cases} x = 1 \\ y = 2 \end{cases}$$"),
    (r"x_1 + y", '<math display="block">x_{1} +\\, y</math>'),
    (r"X \coloneqq (x_1,\cdots,x_n)", r"$X := (x_1, \dots, x_n)$"),
    (r"a \coloneq b", r"$a := b$"),
    (r"a \coloneq b", r"$a \coloneqq b$"),
    (r"a \Coloneq b", r"$a \Coloneqq b$"),
    (r"x \leqq y", r"$x \le y$"),
    ("x ≦ y", r"$x \le y$"),
    (r"x \geqq y", r"$x \ge y$"),
    ("x ≧ y", r"$x \ge y$"),
    (r"\rho_{AB},\sigma_{A'B'}", r"$\rho_{AB}$, $\sigma_{A'B'}$"),
    (r"\Phi(y)\not\in B", r"$\Phi(y) \notin B$"),
    (r"\varphi_{\mid S_1}", r"$\varphi|_{S_1}$"),
    (r"a^{2}.(2 n-2)", r"$a^{2} \cdot (2n-2)$"),
    (r"\boldsymbol{\mathcal{C}}", r"$\mathcal{C}$"),  # KaTeX renders no bold calligraphic
    (r"x \in \mathbb{R}", r"$x \in \R$"),
    (r"d_{\text{min}}^\mathcal{C}", r"$d_{\min}^{\mathcal{C}} = 6$"),
])
def test_one_equation_written_two_ways_matches(test, output):
    assert equations.appears(test, output)[0]


@pytest.mark.parametrize("test, output", [
    (r"x_{1}+y", r"<p>$x_{2}+y$</p>"),
    (r"a^{2}+b", r"<p>$a+b$</p>"),
    (r"\sum_{i=1}^{n} x_i", r"<p>$\sum_{i=1} x_i$</p>"),
    (r"\mathbb{R}^n", r"$R^n$"),
    (r"\bar{x}", r"$\overline{x}$"),
    (r"A\setminus B", r"$A - B$"),
    (r"\mathcal{Z}", r"$\Z$"),
    (r"d_{\min}^{\mathcal{C}}", r"$d_{\min}^{\mathcal{Q}}$"),
    (r"a :- b", r"$a := b$"),  # Note: the colon-minus is a different symbol, not \coloneq's alias
    (r"a \coloneq b", r"$a :- b$"),
])
def test_a_different_equation_fails(test, output):
    assert not equations.appears(test, output)[0]


@pytest.mark.parametrize("before", ["Price $5", "Price $5.00 and $6", "Cost: $"])
def test_a_price_before_an_equation_never_pairs_with_its_dollar(before):
    assert equations.appears(r"\frac{a}{b} \leq c", f"<p>{before}</p><p>$$\\frac{{a}}{{b}} \\leq c$$</p>")[0]


def test_inline_math_may_hold_a_line_break_but_not_a_block():
    assert equations.appears("a + b", "<p>$a +<br>b$</p>")[0]
    assert not equations.appears("x y", "<td>$x</td><td>y$</td>")[0]


# An adversarial probe of the scorer, through the whole path: markdown, its HTML view, the present test.
@pytest.mark.parametrize("test, output, ok", [
    (r"\frac{a}{b}", r"$\frac{b}{a}$", False),
    (r"x_i^2", r"$x_2^i$", False),
    (r"x_{i}^{2}", r"$x^{i}_{2}$", False),
    (r"\sqrt{-d}b", r"$\sqrt{-db}$", False),
    (r"\frac{a}{b}c", r"$\frac{ac}{b}$", False),
    (r"\frac{a}{b+c}", r"$\frac{a}{b}+c$", False),
    (r"\begin{pmatrix}1&2\\3&4\end{pmatrix}", r"$$\begin{pmatrix}3&4\\1&2\end{pmatrix}$$", False),
    (r"y=-x+1", r"$y=x+1$", False),
    (r"x+1=0", r"$-x+1=0$", False),
    (r"a+b", r"$\alpha+b$", False),
    (r"G=(V,E)", r"$\mathcal{G}=(V,E)$", False),
    (r"E=mc", r"$E=mc^2$", False),
    (r"ab", r"Let $a$ be the width and $b$ the height.", False),
    (r"2^{10}", r"The total is 210 units.", False),
    (r"\left(x+y\right)^2", r"$(x+y)^2$", True),
    (r"\big(x+y\big)", r"$(x+y)$", True),
    (r"\frac{a}{b}", r"${a \over b}$", True),
    (r"x\le y", r"$x\leq y$", True),
    (r"x\in\mathbb{R}", r"$x\in R$", False),  # a dropped blackboard font is a difference
    (r"x^2+y_1", r"${x}^{{2}}+{y}_{{1}}$", True),
    (r"\sin x", r"$\operatorname{sin} x$", True),
    (r"E=mc^2 \tag{3}", r"$$E=mc^2$$", True),
    (r"E=mc^2", r"$$E=mc^2 \tag{3}$$", True),
    (r"E=mc^2 \tag{3}", r"$$E=mc^2$$ (3)", True),
    (r"a=b,", r"$a=b$", False),  # inline: the printed comma is missing
    (r"a=b", r"$a=b.$", True),
    (r"\alpha^2\le 1", r"α² ≤ 1", True),
    (r"x\le y", r"$x ≤ y$", True),
    (r"\frac{1}{2}", r"$\dfrac{1}{2}$", True),
    (r"\begin{aligned}a&=b\\c&=d\end{aligned}", '$$a=b$$\n\n$$c=d$$', True),
    (r"\int f(x)\,dx", r"$\int f(x)dx$", True),
    (r"x \text{ if } y", r"$x \mathrm{if} y$", True),
    (r"x_1+x_2", r"\(x_1+x_2\)", True),
    (r"x_1+x_2", '\\[\nx_1+x_2\n\\]', True),
    (r"x^2+y^2=z^2", r"x^2+y^2=z^2", True),
    (r"\frac{a}{b}=c", r"\frac{a}{b}=c", True),
    (r"a=b", '\\begin{equation}\na=b\n\\end{equation}', True),
    (r"a=b", r"$$\begin{equation}a=b\end{equation}$$", True),
    (r"\frac{a}{b}", r"$ \frac{a}{b} $", True),
    (r"\bar{x}", r"$\overline{x}$", False),  # \bar and \overline differ
    (r"f=\begin{cases}1&x>0\\0&x\le0\end{cases}",
     r"$$f=\left\{\begin{array}{ll}1&x>0\\0&x\le0\end{array}\right.$$", True),
    (r"x^2+y", r"$x^2+y \badmacro$", True),
    (r"E=mc^2", r"$E=mc^2 \tag{3}$", True),
    (r"\hat{x}", r"$\widehat{x}$", True),
    (r"x_i^2", r"$x^2_i$", True),
    (r"1+\cdots+n", r"$1+\ldots+n$", True),
    (r"\alpha^2\le 1", r"$α^2 ≤ 1$", True),
    (r"\frac{a}{b}+y", r"$\frac{a}{b}+y \badmacro$", True),
    (r"a=b.", r"$a=b$ and $c$", False),  # inline: the printed full stop is missing
])
def test_an_equation_is_found_only_as_written(test, output, ok):
    v = views.html(markdown.to_html(output))
    assert runners.present(runners.Present(runners.Latex(test)), v)[0] is ok


@pytest.mark.parametrize("test, output, ok", [
    (r"\mu : S \longrightarrow G", r"$\mu : S \rightarrow G$", False),
    (r"\pi_1: V\longrightarrow W", r"$\pi_1: V\longrightarrow W$", True),
    (r"g \cdot (h \cdot x) = (gh) \cdot x", "g . (h . x) = (gh) . x", False),
    (r"a \cdot b", r"$a.b$", True),
    (r"x \eta=\text { const. }", r"so that $x\eta = $ const., where", True),
    (r"M = \{ m_1 , ..., m_r \}", r"$M = \{m_1, \dots, m_r\}$", True),
    (r"H(Z) = -\sum_{z} P(z) \log P(z)", r"$$H(Z) = -\sum_{z} P(z) \log P(z), \eqno(10)$$", True),
    (r"\mu_1(0)= \mu_2(0)", "with μ_1(0) = μ_2(0) = n, then", True),
    (r"g(X_1 \# X_2) = g(X_1) + g(X_2)", "whether g(X1#X2) = g(X1)+g(X2).", False),
    (r"\mathbf{v}=a\mathbf{u}", r"$\boldsymbol{v}=a\boldsymbol{u}$", True),
    (r"a=b,", r"$$a=b$$", True),
    (r"a=b.", r"\[a = b\] where", True),
    (r"a=b;", r"$$a=b$$ and", True),
    (r"a=b,", r"$a=b$ and", False),
    (r"a=b,c=d", r"$$a=b$$ $$c=d$$", False),
    (r"a=b,", r"$$a=b, \quad \dots \quad (1)$$", True),
    (r"a=b", r"$$a = b \; . \; . \; . \; (2)$$", True),
    (r"a=b \dots (3)", r"$$a=b$$", True),
    (r"a=b,", r"$$a=b \ldots (1)$$", True),
    (r"f(x)=(x+1)", r"$$f(x)=x+1$$", False),
    (r"a=b \dots (1)", r"$a=b \dots (1)$ where", True),
    (r"a=b (1)", r"$$a=b$$", False),
    (r"\angle A = 30^\circ", r"$\angle A = 30°$", True),
    (r"\angle A = 30°", r"$\angle A = 30^{\circ}$", True),
    (r"x^\circ", r"$x$", False),
    (r"a \geqq b", r"$a \geq b$", True),
    (r"a \leq b", r"$a ≦ b$", True),
    (r"a \geq b", r"$a > b$", False),
    (r"R_n = a+b", r"$$R_n = a+b \dots\dots\dots (4)^*.$$", True),
    (r"R_n = a+b.", r"$$R_n = a+b \ldots (4*).$$", True),
    (r"R_n = a+b \dots (4)^*", r"$$R_n = a+b$$", True),
    (r"\begin{pmatrix}a&b\\\cdots&\cdots\\c&d\end{pmatrix}",
     r"$$\begin{pmatrix}a&b\\\ldots&\\c&d\end{pmatrix}$$", True),
    (r"\begin{array}{cc}a&b\\. . .&. . .\\c&d\end{array}",
     r"$$\begin{array}{cc}a&b\\\cdot\cdot\cdot\cdot&\cdot\cdot\\c&d\end{array}$$", True),
    (r"\begin{pmatrix}a&b\\\cdots&\cdots\\c&d\end{pmatrix}",
     r"$$\begin{pmatrix}a&b\\c&d\end{pmatrix}$$", False),
    (r"\begin{pmatrix}a&\cdots&b\end{pmatrix}", r"$$\begin{pmatrix}a&b\end{pmatrix}$$", False),
    (r"\begin{pmatrix}a&b\\\vdots&\vdots\\c&d\end{pmatrix}",
     r"$$\begin{pmatrix}a&b\\\vdots& \\c&d\end{pmatrix}$$", True),
    (r"\begin{pmatrix}a&b&c\\\vdots&\ddots&\vdots\\d&e&f\end{pmatrix}",
     r"$$\begin{pmatrix}a&b&c\\⋮&⋮&⋮\\d&e&f\end{pmatrix}$$", True),
    (r"\begin{pmatrix}a&b\\\vdots&\vdots\\c&d\end{pmatrix}",
     r"$$\begin{pmatrix}a&b\\\cdots&\cdots\\c&d\end{pmatrix}$$", False),
    (r"\begin{pmatrix}a&b\\\vdots&\vdots\\c&d\end{pmatrix}",
     r"$$\begin{pmatrix}a&b\\c&d\end{pmatrix}$$", False),
])
def test_look_alikes_and_prose_count_only_as_decided(test, output, ok):
    v = views.html(markdown.to_html(output))
    assert runners.present(runners.Present(runners.Latex(test)), v)[0] is ok
