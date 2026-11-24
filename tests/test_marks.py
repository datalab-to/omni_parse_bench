"""`marks.style_marks`: what an inline style does to marks, declaration by declaration."""
from __future__ import annotations

import pytest

from omni_parse_bench import marks

F = frozenset


@pytest.mark.parametrize("style, add, drop, own", [
    ("font-weight: bold", {"bold"}, set(), set()),
    ("font-weight: 650", {"bold"}, set(), set()),
    ("font-weight: 500", set(), {"bold"}, set()),
    ("font-weight: bold; font-weight: normal", set(), {"bold"}, set()),      # the later declaration wins
    ("font-weight: normal; font-weight: bold", {"bold"}, set(), set()),
    ("font: bold 12px serif", {"bold"}, {"italic"}, set()),
    ("font: italic bold 12px serif", {"bold", "italic"}, set(), set()),
    ("font: 12px serif", set(), {"bold", "italic"}, set()),                   # names neither: plain
    ("font: inherit", set(), set(), set()),                                  # no change
    ("font: var(--font)", set(), set(), set()),
    ("font-weight: inherit", set(), set(), set()),
    # a keyword takes the earlier one back
    ("font-weight: bold; font-weight: inherit", set(), set(), set()),
    ("font-weight: bold; font-weight: unset", set(), set(), set()),
    ("font-weight: bold; font-weight: initial", set(), {"bold"}, set()),     # initial is plain
    ("font-style: italic; font-style: initial", set(), {"italic"}, set()),
    ("font-style: italic; font-style: inherit", set(), set(), set()),
    ("font: bold 12px serif; font: inherit", set(), set(), set()),
    ("font: bold 12px serif; font: initial", set(), {"bold", "italic"}, set()),
    ("text-decoration: underline; text-decoration: inherit", set(), set(), set()),
    ("text-decoration: underline; text-decoration: initial", set(), set(), {"underline", "strike"}),
    ("vertical-align: super; vertical-align: inherit", set(), set(), set()),
    ("font-weight: bold !important; font-weight: normal", {"bold"}, set(), set()),   # an important one wins
    ("font-weight: normal; font-weight: bold !important", {"bold"}, set(), set()),
    ("font-weight: bold !important; font-weight: normal !important", set(), {"bold"}, set()),
    ("font: 12px serif !important; font-weight: bold", set(), {"bold", "italic"}, set()),
    ("text-decoration: underline !important; text-decoration: none", {"underline"}, set(), set()),
    ("font-weight: bold ! important; font-weight: normal", {"bold"}, set(), set()),   # a space after `!`
    # each half alone
    ("font-weight: bold !important; font: italic 12px serif", {"bold", "italic"}, set(), set()),
    ("font-style: italic !important; font: bold 12px serif", {"bold", "italic"}, set(), set()),
    ("text-decoration: underline", {"underline"}, set(), set()),
    ("text-decoration: underline; text-decoration: none", set(), set(), {"underline", "strike"}),
    ("text-decoration: line-through underline", {"underline", "strike"}, set(), set()),
    ("vertical-align: super", {"sup"}, {"sub"}, set()),
    ("vertical-align: sub", {"sub"}, {"sup"}, set()),
    ("vertical-align: baseline", set(), set(), {"sup", "sub"}),
    ("color: red; vertical-align: top", set(), set(), set()),
])
def test_what_a_style_does_to_marks(style, add, drop, own):
    assert marks.style_marks(style) == (F(add), F(drop), F(own))


def _kinds(html, span, before="", after=""):
    """The marks `format` finds on `span` in `html`: whether sub and sup tests pass."""
    return {k: marks.check(marks.read(html), before, span, after, (k,), ())[0] for k in ("sub", "sup")}


@pytest.mark.parametrize("html", [
    "<p>the volume V<sub>1</sub> was</p>", "<p>the volume $V_1$ was</p>", "<p>the volume $V_{1}$ was</p>",
    r"<p>the volume \(V_1\) was</p>", r"<p>the volume \(V_{1}\) was</p>", "<p>the volume $$V_1$$ was</p>",
    r"<p>the volume \[V_1\] was</p>",
])
def test_a_subscript_in_maths_is_a_subscript(html):
    assert _kinds(html, "1", "the volume V", " was") == {"sub": True, "sup": False}


@pytest.mark.parametrize("html, before, span", [
    ("$x^2$", "x", "2"), ("$x^{2}$", "x", "2"), ("<sup>2</sup>", "", "2"), ("$0.06^{a}$", "0.06", "a"),
    (r"$\mathrm{LC}_{50}$", "LC", "50"), (r"$\text{CO}_2$", "CO", "2"),
    (r"$\mathrm{LC}_{\mathrm{50}}$", "LC", "50"),
    ("$V_{12}$", "V", "12"), ("$V_{1,2}$", "V", "1,2"), ("$x_1^2$", "x1", "2"),
])
def test_scripts_in_maths_with_and_without_braces_and_with_text_bases(html, before, span):
    kind = "sup" if "^" in html or "sup" in html else "sub"
    assert _kinds(html, span, before)[kind]


def test_a_subscript_is_one_character_without_braces():
    assert _kinds("$V_12$", "1", "V")["sub"] and not _kinds("$V_12$", "12", "V")["sub"]


@pytest.mark.parametrize("html", ["the volume $V_2$ was", "the volume $V_{12}$ was", "the volume V_1 was",
                                  "the volume $V^1$ was"])
def test_a_maths_script_that_differs_from_the_span_does_not_pass(html):
    assert not _kinds(html, "1", "the volume V", " was")["sub"]


@pytest.mark.parametrize("html", [
    r"$\frac{x}{y}_1$", r"$\sqrt{x}_1$", r"$\bar{x}_1$", r"$\begin{matrix}a_1\end{matrix}$", "$x_{1_2}$",
    "$x_{\\frac{1}{2}}$", "$x_{}$",
])
def test_maths_with_another_command_or_a_nested_script_makes_no_script(html):
    assert not any(_kinds(html, "1", "").values()) and not any(_kinds(html, "x", "").values())


def test_a_fraction_or_root_creates_no_sub_or_sup():
    for html in (r"$\frac{1}{2}$", r"$\sqrt{2}$", r"$\sqrt[3]{2}$"):
        assert not any(_kinds(html, "2", "").values())


def test_maths_does_not_make_bold_or_italic():
    for html in (
        r"the $\mathbf{total}$ due", r"the $\mathit{total}$ due", r"the $\textbf{total}$ due",
        "the $total_1$ due",
    ):
        m = marks.read(html)
        assert not m.emitted or set().union(*m.marks) <= {"sub", marks.FROM_MATHS}
        for kind in ("bold", "italic"):
            assert not marks.check(m, "the ", "total", "due", (kind,), ())[0]


def test_an_absent_subscript_test_fails_on_a_maths_subscript():
    ok, why = marks.check(
        marks.read("<p>the volume $V_1$ was</p>"), "the volume V", "1", " was", (), ("sub",)
    )
    assert not ok and "sub" in why


def test_prices_are_not_maths():
    assert not any(_kinds("it cost $5 and then $6_1", "5").values())


# --- the red team's findings

ABSENT_OTHERS = ("bold", "italic", "underline", "strike")


@pytest.mark.parametrize("kind", ABSENT_OTHERS)
@pytest.mark.parametrize(
    "html", ["<p>the total due</p><p>$x_1$</p>", r"<p>the total due</p><p>\(x^{2}\)</p>"]
)
def test_maths_is_no_evidence_for_an_absent_bold_italic_underline_or_strike_test(kind, html):
    ok, why = marks.check(marks.read(html), "the ", "total", " due", (), (kind,))
    assert not ok and "no marks at all" in why


@pytest.mark.parametrize("kind", ["sub", "sup"])
def test_maths_is_evidence_for_an_absent_sub_or_sup_test(kind):
    ok, _ = marks.check(
        marks.read("<p>the total due</p><p>$x_1^2$</p>"), "the ", "total", " due", (), (kind,)
    )
    assert ok


def test_a_real_mark_elsewhere_still_is_evidence_for_every_absent_test():
    for kind in ABSENT_OTHERS:
        assert marks.check(marks.read("<p>the total due</p><p><b>x</b> $y_1$</p>"), "the ", "total", " due",
                           (), (kind,))[0]


@pytest.mark.parametrize("html, before, span, kind", [
    (r"$1.5 \times 10^{-3}$ m", "1.5×10", "-3", "sup"), (r"$5 \times 10^{5}$", "5×10", "5", "sup"),
    (r"$\sim 10^{5}$ K", "∼10", "5", "sup"), (r"$\pm 0.5\,\mathrm{cm}^{2}$", "±0.5cm", "2", "sup"),
    (r"$\mu m^2$", "μm", "2", "sup"), (r"$E = mc^{2} + \alpha$", "E=mc", "2", "sup"),
    (r"$\Delta T_c$", "ΔT", "c", "sub"), (r"$\left( x^2 \right)$", "(x", "2", "sup"),
    (r"$\epsilon_r$ end", "ε", "r", "sub"), (r"$\mu_0$", "μ", "0", "sub"), (r"$\sigma_{x}$", "σ", "x", "sub"),
    (r"$\beta_{1}$", "β", "1", "sub"), (r"$T_{\max}$", "T", "max", "sub"),
    (r"$\lambda_{\max}$", "λ", "max", "sub"),
    (r"$x^{\circ}$", "x", "°", "sup"),
])
def test_a_command_with_no_argument_is_a_symbol_and_the_scripts_around_it_are_read(html, before, span, kind):
    if span == "°": pytest.skip("a span with no letter or digit is no format test")
    assert marks.check(marks.read(html), before, span, "", (kind,), ())[0], marks.with_scripts(html)


def test_greek_in_maths_lines_up_with_the_letter_in_html():
    assert marks.read(r"$\epsilon_r$").text == marks.read("ε<sub>r</sub>").text


@pytest.mark.parametrize("html, before, span, kind", [
    (r"$\mathrm{H_2O}$", "H", "2", "sub"), (r"$\mathrm{IC_{50}}$", "IC", "50", "sub"),
    (r"$\text{CO_2}$", "CO", "2", "sub"), (r"word${}^{a}$ note", "word", "a", "sup"),
    (r"${}^{14}\mathrm{C}$", "", "14", "sup"), ("$x _ 1$", "x", "1", "sub"), ("$x ^ 2$", "x", "2", "sup"),
    ("$x_ 1$", "x", "1", "sub"), (r"$\mathrm{H_2O}$", "H", "2", "sub"),
])
def test_scripts_inside_a_font_group_after_an_empty_base_and_after_spaces_are_read(html, before, span, kind):
    assert marks.check(marks.read(html), before, span, "", (kind,), ())[0], marks.with_scripts(html)


@pytest.mark.parametrize("html", [
    "<code>$a_1$</code>", "<pre>echo $a_1 $b_2</pre>", "<p><kbd>$a_1$</kbd></p>", "<samp>\\(a_1\\)</samp>",
    "<code>$a_1$", "<pre>\\[ a_1 \\]</pre>",
])
def test_maths_inside_code_is_not_read(html):
    assert marks.with_scripts(html) == html
    assert not marks.read(html).emitted


def test_code_ends_where_it_closes_and_maths_after_it_is_read():
    assert "<sub" in marks.with_scripts("<code>$a_1$</code> and $b_2$")
    assert "<sub" not in marks.with_scripts("<code>$a_1$</code> and $b_2$").split("</code>")[0]


@pytest.mark.parametrize("opener", ["\\[", "\\("])
def test_unclosed_maths_openers_are_read_in_one_pass(opener):
    import time

    start = time.perf_counter()
    marks.with_scripts("<p>" + f"{opener} x_1 " * 20000 + "</p>")
    assert time.perf_counter() - start < 1.0


def test_an_unclosed_opener_before_a_closed_span_does_not_hide_it():
    assert "<sub" in marks.with_scripts("\\( stray and $V_1$")
