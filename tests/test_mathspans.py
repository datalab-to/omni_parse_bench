"""The single-dollar math span reader (`mathspans`), the one both the text path and the equation path use."""
from __future__ import annotations

import html as _html

import pytest
from hypothesis import given
from hypothesis import strategies as st

from omni_parse_bench import equations, mathspans, normalize, views


def bodies(s: str) -> list[str]:
    """The single-dollar spans' bodies."""
    return [x.body for x in mathspans.find(s) if not x.display]


# 1. Spans pair adjacent dollars, so the words between two spans are never a span of their own.
@pytest.mark.parametrize("text, found", [
    ("$a$ and $b$", ["a", "b"]),
    ("$a$ and $b__c$ and $d$", ["a", "d"]),             # a blank is no math, and it still holds its dollars
    # a page that pads its math ("$ x_1 $"): padded plain math reads too
    ("$ P=0.0074 $ and $ P=0.0089 $ ok $ x_1 $", ["P=0.0074", "P=0.0089", "x_1"]),
    ("$x^2$ and $y$", ["x^2", "y"]),
])
def test_spans_pair_adjacent_dollars(text, found):
    assert [b.strip() for b in bodies(text)] == found


# 2. A dollar with no partner is a stray (currency); a price before math does not take the math's dollar.
@pytest.mark.parametrize("text, found", [
    ("Cost $ and $x$", ["x"]),
    ("$5.00 for $U$", ["U"]),
    ("US$5 and the $U$ test", ["U"]),
    ("$92,000; Net +$60,000", []),                       # two prices
    ("$5$6", []),
    ("$100-$200", []),
    ("Cost $ and $ x $ now", [" x "]),                   # on a tie the earlier dollar is the stray
    ("in $ and $ out", []),                              # two lowercase letters padded are a word
])
def test_a_dollar_without_a_partner_is_a_stray(text, found):
    assert bodies(text) == found


# 3. Escaped dollars and runs of two or more are not single dollars.
@pytest.mark.parametrize("text, found", [
    (r"x \$5 and \$6", []),
    (r"x \$5 and \$6 and $y$", ["y"]),
    ("$$x$$ and $y$", ["y"]),
])
def test_escaped_dollars_and_dollar_runs_are_not_delimiters(text, found):
    assert bodies(text) == found


# 4. A block ends a line: a span never crosses one, in either path.
@pytest.mark.parametrize("html", ["<p>$a</p><p>b$</p>", "<table><tr><td>$x</td><td>y$</td></tr></table>"])
def test_a_span_never_crosses_a_block(html):
    assert equations.spans(html) == []
    assert "$" in normalize.fold(views.text(html))


def test_a_break_or_an_image_may_sit_inside_a_span():
    assert equations.spans("<p>$x<br>_1$</p>") == [("x _1", False)]


# 5. Padding is the producer's style: on a page that pads its math, a padded lowercase word reads too.
def test_padding_is_the_producers_style():
    lone = "in $ and $ out"
    padded_page = lone + " and $ x_1 $"
    assert bodies(lone) == []
    assert " and " in bodies(padded_page)


@pytest.mark.parametrize("text", ["$ p $", "$ x $", "($ n $)", "$ FeS $", "$ ΔG $", "$ OR $"])
def test_a_padded_variable_reads_as_its_letters(text):
    assert len(mathspans.find(text)) == 1


# 6. The two paths read the same spans: what the text path converts, the equation path finds.
TOKEN = st.sampled_from(
    ["$", "$5", "US$", "x", " and ", " ", "_", "x_1", "\\alpha", "^2", "$$", "word", "\\$", "7"])


@given(st.lists(TOKEN, min_size=1, max_size=10).map("".join))
def test_the_text_path_reads_only_spans_the_equation_path_finds(s):
    html = _html.escape(s, quote=False)
    text_path = [x.body for x in mathspans.find(html) if x.read]
    eq_path = [tex for tex, _ in equations.spans(f"<p>{html}</p>")]
    for body in text_path:
        assert _html.unescape(body) in eq_path


# 7. A display may hold single dollars (a \tag with its own math), and an unpaired `$$` is a stray.
def test_a_display_may_hold_single_dollars():
    spans = mathspans.find(r"$$ x \tag{ $\dagger$ } $$")
    assert [(x.display, x.body.strip().startswith("x")) for x in spans] == [(True, True)]


def test_an_unpaired_display_delimiter_is_a_stray():
    spans = mathspans.find("$$ 1+x)\\left(1-3 x\\right.\n\nDividend.\n\n$$ \\begin{array}{c}a\\end{array} $$")
    assert [x.display for x in spans] == [True]
    assert "begin{array}" in spans[0].body


# 8. Capitals are points and constants, not prose: "AOB = BOC = COD" is math.
def test_a_span_of_capital_words_is_math():
    assert bodies(r"$\angle AOB = \angle BOC = \angle COD = 60^\circ$")


def test_a_span_of_lowercase_words_is_prose():
    assert not bodies(r"$____ Date paid ____ Balance$")


# 9. The equation path reads what the text path reads: a span in an image's alt text, and a delimiter that
# starts first.
def test_math_in_an_images_alt_text_is_read():
    assert equations.spans("<p><img alt='so $a_1$ here'></p>") == [("a_1", False)]


def test_the_span_that_starts_first_is_the_span():
    assert equations.spans(r"<p>$a \( b$ c \)</p>") == [(r"a \( b", False)]


# 10. Found in review: a padded span around LaTeX before a digit is math, a display does not take the dollar
# after it, and a `\begin` that never ends in its block does not swallow the blocks after it.
@pytest.mark.parametrize("text, found", [
    ("0.1 $ \\pm $0.0", [" \\pm "]),
    ("1.73$ \\pm $0.154 mg/mL, 2.17$ \\pm $0.173", [" \\pm ", " \\pm "]),
    ("x $ \\alpha $2 and $ \\beta $ y", [" \\alpha ", " \\beta "]),
    ("$2.7 $2.2", []),
])
def test_a_padded_span_around_latex_before_a_digit_is_math(text, found):
    assert bodies(text) == found


def test_a_display_does_not_take_the_dollar_after_it():
    assert [x.body for x in mathspans.find("$$x$$$5.00") if x.display] == ["x"]


def test_an_unfinished_environment_does_not_swallow_the_next_blocks():
    html = ("<p>[\\left{\\begin{aligned} a &=1</p><p>$$ x = 1 $$</p>"
            "<p>$$ \\begin{aligned} b \\end{aligned} $$</p>")
    assert [tex.strip() for tex, _ in equations.spans(html)] == ["x = 1", "\\begin{aligned} b \\end{aligned}"]


# 11. Found in a second review: a lone later dollar does not turn a display
# into an inline span, and the padding check stays linear.
@pytest.mark.parametrize("text", ["$$x^2$$ and $", "$$x^2$$ cost $"])
def test_a_display_stays_a_display_beside_a_lone_dollar(text):
    assert [(x.body, x.display) for x in mathspans.find(text)] == [("x^2", True)]


def test_math_mode_currency_is_math():
    assert bodies(r"cost = $\$412$. min = $\$178$.") == [r"\$412", r"\$178"]


def test_the_padding_check_is_linear():
    import time
    start = time.perf_counter()
    mathspans.find("$ " + "_a" * 10000 + "$")
    assert time.perf_counter() - start < 0.2
