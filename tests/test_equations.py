"""The equation comparison: what an equation renders to, not how its LaTeX is written."""
from __future__ import annotations

import pytest

from omni_parse_bench import equations


@pytest.mark.parametrize("test, output", [
    (r"\frac{a}{b} \leq c", r"<p>$\dfrac{a}{b} \leqslant c$</p>"),
    (r"f: A \to B", r"<p>\(f\colon A \rightarrow B\)</p>"),
    (r"\left\{ \begin{aligned} x &= 1 \\ y &= 2 \end{aligned} \right.",
     r"$$\begin{cases} x = 1 \\ y = 2 \end{cases}$$"),
    (r"x_1 + y", '<math display="block">x_{1} +\\, y</math>'),
    (r"X \coloneqq (x_1,\cdots,x_n)", r"$X := (x_1, \dots, x_n)$"),
    (r"\rho_{AB},\sigma_{A'B'}", r"$\rho_{AB}$, $\sigma_{A'B'}$"),
    (r"\Phi(y)\not\in B", r"$\Phi(y) \notin B$"),
    (r"\varphi_{\mid S_1}", r"$\varphi|_{S_1}$"),
    (r"a^{2}.(2 n-2)", r"$a^{2} \cdot (2n-2)$"),
    (r"\boldsymbol{\mathcal{C}}", r"$\mathcal{C}$"),
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
])
def test_a_different_equation_fails(test, output):
    assert not equations.appears(test, output)[0]
