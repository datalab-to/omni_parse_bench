"""Relations of math: the text tests and the equation test read the same math (M10), an equation written in
equivalent forms (M17), and a middle dot in \\text{} (M21).

The text tests read math through fold; the equation test (present with a latex arg) through `equations.spans`
and `equations.appears`. M10 checks one direction: every span fold reads as math is also found by the
equation test, where found means a span of `equations.spans` with the same body once white space and
\\( \\) \\[ \\] are removed, or one with the same KaTeX-rendered symbols."""
from __future__ import annotations

import re
import string

import pytest
from hypothesis import assume, example, given
from hypothesis import strategies as st

from metamorphic.common import BUG, HOLDS, deviation, more_evidence, passes, relation
from omni_parse_bench import equations, normalize, views
from omni_parse_bench.normalize import fold
from omni_parse_bench.scorers.unit_tests import runners


def math_read_by_the_text_tests(html: str) -> list[str]:
    """The bodies of the math spans that fold converts to text on this page: it records each body passed to
    fold's two math readers (`normalize._read`, and `_display_or_paren` when it changes the span)."""
    seen, read, display = [], normalize._read, normalize._display_or_paren

    def recording_read(body):
        seen.append(body)
        return read(body)

    def recording_display(whole, body, *, inline):
        out = display(whole, body, inline=inline)
        if out is not None and out != whole:
            seen.append(body)
        return out

    normalize._read, normalize._display_or_paren = recording_read, recording_display
    try:
        fold(views.text(html))
    finally:
        normalize._read, normalize._display_or_paren = read, display
    return seen


def found_by_the_equation_test(body: str, spans: list[tuple[str, bool]]) -> bool:
    """Whether the equation test has the span `body`: one of `spans` with the same rendered symbols ('\\alpha'
    and 'α'), or with the same body once white space and \\( \\) \\[ \\] are removed."""
    bare = lambda s: re.sub(r"\s+|\\[()\[\]]", "", s)  # noqa: E731
    if any(bare(body) == bare(tex) for tex, _ in spans):
        return True
    want = equations.symbols(body) or equations.symbols(body, True)
    return bool(want) and any(want in (equations.symbols(tex), equations.symbols(tex, True))
                              for tex, _ in spans)


def assert_both_read_the_same_math(html: str) -> int:
    """Asserts the equation test finds every span the text tests read as math; returns how many they read."""
    spans, bodies = equations.spans(html), math_read_by_the_text_tests(html)
    for body in bodies:
        assert found_by_the_equation_test(body, spans), (body, spans)
    return len(bodies)


@more_evidence()
def test_the_math_comparison_sees_spans_and_notices_a_missing_one():
    """The M10 comparison finds three kinds of math and rejects a span the equation test lacks; and on one
    fixed page each for M10c, M10d, M10f and M10g fold reads at least one span, so those relations are not met
    by pages without math. [M10a, M10c, M10d, M10f, M10g]
    Why it matters for a score: without this, a comparison that saw nothing would make every M10 test pass."""
    # Given a page with a dollar span, a \( \) span and a <math> element; Then all three are compared
    assert assert_both_read_the_same_math("<p>$x_1$ and \\(a_2\\) and <math>c_1</math></p>") >= 3
    # And one fixed page per relation (its first @example) has a span fold reads: M10c, M10d, M10f, M10g
    for page in ("<p><img alt='$q_1$'>\\($</p>", "<p>$$x$<b>$$</p>", "<p>$5.00<br>$U$<br>$5.00</p>",
                 "<p>$$ $x_1$ $$</p><p>$$ </p>"):
        assert assert_both_read_the_same_math(page) >= 1, page
    # And the comparison accepts a rendered match and rejects a span the equation test does not hold
    assert found_by_the_equation_test("\\alpha", [(" α ", False)])
    assert not found_by_the_equation_test("x_1", [("y^2", False)])
    assert not found_by_the_equation_test("5.00", [])


# Complete spans of each kind; no span is inside another.
DOLLARS = ["$x_1$", "$$y^2$$", "$U$", "$\\alpha + 1$", "$ p $", "$5.00", "US$5", "$", "$$"]
BRACKETS = ["\\(a_2\\)", "\\[b^3\\]", "\\(\\alpha\\)"]
ENVIRONMENTS = ["\\begin{align} e &= 1 \\end{align}"]
ELEMENTS = ["<math>c_1</math>", "<math display='block'>d^2</math>", "<math><mi>z</mi></math>"]
SEPARATOR = st.sampled_from([" ", " and ", "&amp;", " word ", "\n"])
BLOCK_BREAK = st.sampled_from(["</p><p>", "<td>", "</td><td>", "</li><li>"])


def chained(spans, between=SEPARATOR):
    """One to five of `spans`, each followed by one of `between`."""
    return st.lists(st.tuples(st.sampled_from(spans), between), min_size=1, max_size=5).map(
        lambda xs: "".join(a + b for a, b in xs))


@relation(HOLDS)
@given(st.one_of(chained(DOLLARS), chained(BRACKETS), chained([*ELEMENTS, *BRACKETS]),
                 chained([*BRACKETS, *ELEMENTS], BLOCK_BREAK), chained(ENVIRONMENTS), chained(ELEMENTS)))
def test_math_the_text_tests_read_the_equation_test_finds(s):
    """On a page of one kind of math span, every span fold reads as math is also found by the equation test (a
    span with the same body or the same rendered symbols). The pages hold dollars alone, `\\(` and `\\[` alone
    or with `<math>`, `\\begin` alone, or `<math>` alone, with prose between; breaks are bare tags (`</p><p>`,
    `<td>`, `</li><li>`) inside one paragraph. [M10a]
    Why it matters for a score: a page's math must count as math for both kinds of test, or neither."""
    # Given spans of one kind ($, \( \[, \begin, or <math>) with prose, entities and block breaks between
    html = f"<p>{s}</p>"
    assume(math_read_by_the_text_tests(html))
    # When fold reads some of them as math; Then the equation test finds each of those
    assert_both_read_the_same_math(html)


@relation(HOLDS)
@pytest.mark.parametrize("entity", ["&#36;", "&dollar;", "&#x24;"])
@example(s="$x$")
@given(st.lists(st.sampled_from(["$", "x", "_1", " and ", "$5", "\\alpha", "7", "$$", "y^2", " "]),
                min_size=1, max_size=8).map("".join))
def test_a_dollar_written_as_an_entity_is_read_as_a_dollar(entity, s):
    """Writing each `$` as `&#36;`, `&dollar;` or `&#x24;` leaves unchanged both the list of spans fold reads
    as math and the list of spans the equation test finds. [M10b]
    Why it matters for a score: an entity is the same character on the rendered page."""
    # Given a paragraph with dollars, and the same with each `$` written as an entity
    literal, written = f"<p>{s}</p>", f"<p>{s.replace('$', entity)}</p>"
    # When each kind of test reads both; Then each reads the same math in both
    assert math_read_by_the_text_tests(written) == math_read_by_the_text_tests(literal)
    assert equations.spans(written) == equations.spans(literal)


@relation(HOLDS, domain="12 combinations: 3 alt texts x 4 following texts")
@example(alt="$q_1$", after="\\($")
@given(st.sampled_from(["$q_1$", "$x", "a$"]), st.sampled_from(["\\($", "$", " $y$ z$", "b$"]))
def test_a_span_starting_in_an_images_alt_text_is_read_the_same(alt, after):
    """When a span starts in an image's alt text and ends after it, every span fold reads as math is also
    found by the equation test (a span with the same body or the same rendered symbols). [M10c]
    Why it matters for a score: as for M10a, around images."""
    # Given an image whose alt text opens a span that the text after it closes
    # When both kinds of test read the page; Then the equation test finds each span fold reads as math
    assert_both_read_the_same_math(f"<p><img alt='{alt}'>{after}</p>")


MATH_TOKEN = st.sampled_from(
    ["$", "$$", "\\(", "\\)", "\\[", "\\]", "x", "_1", "^2", "\\alpha", " ", " and ", "<math>x_1</math>",
     "<math display='block'>y^2</math>", "<math><mi>z</mi></math>", "$5", "US$", "\\$", "&amp;", "&lt;",
     "word", "<br>", "</p><p>", "<b>", "</b>", "\\frac{a}{b}", "7", "$$x$$", "$a$", "\\(b\\)",
     "<sup>2</sup>"])


@relation(HOLDS)
@example(s="$$x$<b>$$")
@given(st.lists(st.one_of(MATH_TOKEN, st.sampled_from(["<b>", "</b>", "<mark>", "<i>", "<span>"])),
                min_size=1, max_size=9).map("".join))
def test_an_inline_tag_between_dollars_changes_neither_reading(s):
    """On a page of math tokens with inline tags (`<b>`, `<i>`, `<span>`, `<mark>`) anywhere, even between
    dollars, every span fold reads as math is also found by the equation test (a span with the same body or
    the same rendered symbols). Left out, as M10e: pages with `\\(` together with `$`, `<math` or `\\[`, and
    pages with `$` together with `\\[`. [M10d]
    Why it matters for a score: as for M10a, for styled math."""
    # Given math tokens and inline tags in any order, with no mix of delimiters (that is M10e)
    assume(not (("$" in s or "<math" in s or "\\[" in s) and "\\(" in s or "$" in s and "\\[" in s))
    # When both kinds of test read the page; Then the equation test finds each span fold reads as math
    assert_both_read_the_same_math(f"<p>{s}</p>")


@relation(BUG)
@deviation("M10e")
@example(s="$5.00 \\(a_2\\)&amp;$ ")
@given(st.lists(st.tuples(st.sampled_from([*DOLLARS, *BRACKETS, *ENVIRONMENTS, *ELEMENTS]), SEPARATOR),
                min_size=1, max_size=5).map(lambda xs: "".join(a + b for a, b in xs)))
def test_spans_of_mixed_kinds_are_read_the_same(s):
    """On a page that mixes span kinds freely (dollars, `\\(`, `\\[`, `\\begin`, `<math>`), including the
    mixes M10d leaves out (`\\(` with `$`, `<math>` or `\\[`; `$` with `\\[`), every span fold reads as math
    is also found by the equation test (a span with the same body or the same rendered symbols). [M10e]
    Why it matters for a score: as for M10a, on pages that mix math notations."""
    # Given spans of every kind side by side; When both kinds of test read the page
    # Then the equation test finds each span fold reads as math
    assert_both_read_the_same_math(f"<p>{s}</p>")


@relation(HOLDS)
@example(s="$5.00<br>$U$<br>$5.00")
@given(st.lists(st.tuples(st.sampled_from(DOLLARS), st.sampled_from(["<br>", "<br/>", "<br> "])),
                min_size=1, max_size=5).map(lambda xs: "".join(a + b for a, b in xs)))
def test_a_line_break_between_dollars_is_read_the_same(s):
    """With `<br>` between dollar spans and stray dollars, every span fold reads as math is also found by the
    equation test (a span with the same body or the same rendered symbols). [M10f]
    Why it matters for a score: as for M10a, across line breaks."""
    # Given dollar spans and stray dollars with <br> between; When both kinds of test read the page
    # Then the equation test finds each span fold reads as math
    assert_both_read_the_same_math(f"<p>{s}</p>")


@relation(HOLDS)
@example(s="$$ $x_1$ $$</p><p>$$ ")
@given(chained(DOLLARS, BLOCK_BREAK))
def test_dollars_across_a_block_break_are_paired_the_same(s):
    """With bare block tags (`</p><p>`, `<td>`, `</td><td>`, `</li><li>`, inside one paragraph, not a built
    table or list) between dollar spans and stray dollars, every span fold reads as math is also found by the
    equation test (a span with the same body or the same rendered symbols). [M10g]
    Why it matters for a score: as for M10a, across blocks."""
    # Given dollar spans and stray dollars with block breaks between; When both kinds of test read the page
    # Then the equation test finds each span fold reads as math
    assert_both_read_the_same_math(f"<p>{s}</p>")

# ----------------------------------------------------------------------------------- equation forms


# The 8 equations, each with a near miss that must fail: another exponent, swapped arguments, another number.
NEAR_MISS = {"x^2": "x^3", "x^{2}": "x^{3}", "a_1 + b_2": "a_2 + b_1", "\\frac{a}{b}": "\\frac{b}{a}",
             "\\dfrac{a+1}{b}": "\\dfrac{b}{a+1}", "\\alpha = 0.05": "\\alpha = 0.5",
             "\\sqrt{x}": "\\sqrt{y}", "n_{i}^{2}": "n_{i}^{3}"}


@relation(HOLDS, domain="8 equations, each in 6-8 distinct forms, 1 near miss, 1 other")
@given(st.sampled_from(list(NEAR_MISS)))
def test_an_equation_in_an_equivalent_form_passes_its_test(tex):
    """An equation test for each of 8 equations passes on its equation in 6 to 8 distinct written forms (6
    delimiters, braces added or dropped on one-character scripts, `\\frac`, `\\dfrac` or `\\tfrac`), and fails
    on a near miss (`x^3` for `x^2`, swapped arguments, `0.5` for `0.05`, `\\sqrt{y}`) and on another
    equation. [M17]
    Why it matters for a score: these forms render the same; the test grades the rendered equation."""
    # Given an equation test, and pages that write its equation in each equivalent form
    p = runners.Present(runners.Latex(tex))
    braced, unbraced = re.sub(r"([\^_])(\w)", r"\1{\2}", tex), re.sub(r"([\^_])\{(\w)\}", r"\1\2", tex)
    swapped = [tex.replace("\\frac", "\\dfrac"), tex.replace("\\dfrac", "\\frac"),
               tex.replace("\\frac", "\\tfrac")]
    forms = [f"${tex}$", f"$${tex}$$", f"\\({tex}\\)", f"\\[{tex}\\]", f"<math>{tex}</math>",
             f"<math display='block'>{tex}</math>", *(f"${x}$" for x in (braced, unbraced, *swapped))]
    # When the test runs on each page; Then it passes
    assert 6 <= len(set(forms)) <= 8, len(set(forms))    # the distinct forms the promise counts
    for page in (f"<p>{x}</p>" for x in forms):
        assert passes(p, page), page
    # And it fails on a near miss and on a different equation (so the relation is not vacuous)
    assert not passes(p, f"<p>${NEAR_MISS[tex]}$</p>"), NEAR_MISS[tex]
    assert not passes(p, "<p>$q + z$</p>")


@relation(HOLDS)
@given(st.text(string.ascii_lowercase, min_size=1, max_size=5),
       st.text(string.ascii_lowercase, min_size=1, max_size=5),
       st.sampled_from(["${}$", "$${}$$", "\\({}\\)"]))
def test_a_middle_dot_inside_text_in_math_is_kept(left, right, wrapper):
    """A middle dot inside `\\text{}` in math is read as text: text and equation tests for `a·b` pass; the
    text test fails on a page without the dot and on `\\text{ab}` in math, and the equation test fails on
    `\\text{ab}` in math. [M21]
    Why it matters for a score: the dot is printed on the page; dropping it would pass a page that lost it."""
    # Given a math span holding \text{left·right}
    tex = f"\\text{{{left}·{right}}}"
    page = f"<p>{wrapper.replace('{}', tex)}</p>"
    # When fold, a text test and an equation test read it; Then all keep the dot
    assert fold(views.text(page)) == f"{left}·{right}"
    assert passes(runners.Present(runners.Text(f"{left}·{right}", 0)), page)
    assert passes(runners.Present(runners.Latex(tex)), page)
    # And the text test fails on a page that dropped the dot (so the relation is not vacuous)
    assert not passes(runners.Present(runners.Text(f"{left}·{right}", 0)), f"<p>{left}{right}</p>")
    without_dot = wrapper.replace("{}", f"\\text{{{left}{right}}}")
    assert not passes(runners.Present(runners.Text(f"{left}·{right}", 0)), f"<p>{without_dot}</p>")
    assert not passes(runners.Present(runners.Latex(tex)), f"<p>{without_dot}</p>")
