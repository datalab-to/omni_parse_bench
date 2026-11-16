"""The single-dollar math span reader (`mathspans`), the one both the text path and the equation path use."""
from __future__ import annotations

import html as _html
from unittest import mock

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
    # `\( b$ c \)` is no math to the text path (padded, no LaTeX), so it stays `$ b$ c $` and its dollars are
    # no delimiters of the text around it; the dollar in its body still pairs with the first, and that span,
    # starting first, holds the `\(..\)`
    assert equations.spans(r"<p>$a \( b$ c \)</p>") == [("a $ b", False)]


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


# 12. A display holding math of its own in `\text{...}` is one display, not the spans inside it.
def test_a_display_holding_inline_math_in_its_text_is_one_display():
    tex = r"W(a,b)=\begin{cases} 1 & \text{if $b\neq 0$,} \\ 0 & \text{if $a=0$, $b=0$.} \end{cases}"
    spans = mathspans.find(f"$${tex}$$")
    assert [(x.display, x.body) for x in spans] == [(True, tex)]


def test_a_display_does_not_swallow_the_inline_spans_after_it():
    html = "$$ a=b $$ then $ x_1 $ and $ y_2 $ and $$ c=d"
    assert [(x.display, x.body.strip()) for x in mathspans.find(html)][:1] == [(True, "a=b")]
    assert "x_1" in [x.body.strip() for x in mathspans.find(html) if not x.display]


# 13. The two paths read one text: the equation path pairs the dollars of the text the text path pairs
# (`views.reading`, then `normalize.read_math`), so the spans the text path reads as math are the spans
# `equations.spans` returns.
@pytest.mark.parametrize("html, found", [
    # an escaped dollar is the dollar it names
    ("<p>&#36;x&#36;</p>", [("x", False)]),
    ("<p>&dollar;x&dollar;</p>", [("x", False)]),
    ("<p>&#x24;x&#x24;</p>", [("x", False)]),
    # a tag's remnant does not leak into a span that starts in an image's alt text
    ("<p><img alt='$q_1$'>\\($</p>", [(" \\(", False)]),
    # an inline tag between dollars is not a character of the text
    ("<p>$$x$<b>$$</p>", [("x", True)]),
    ("<p>$\\(b\\)$</p>", [("b", False)]),
    # \( \) is rewritten before the dollars are paired
    ("<p>$$y^2$$ \\(a_2\\) and $5.00 </p>", [("y^2", True), ("a_2", False)]),
    ("<p>$$y^2$$ <math>c_1</math> and $5.00 </p>", [("y^2", True), ("c_1", False)]),
    ("<p>$5 <math>x_1</math> $6</p>", [("x_1", False)]),
    # <br> is a space, not a character that is none
    ("<p>$5.00<br>$U$<br>$5.00</p>", [("U", False)]),
    # a block ends the line
    ("<p>$$ $x_1$ $$</p><p>$$ </p>", [(" $x_1$ ", True)]),
])
def test_the_equation_path_reads_the_spans_the_text_path_reads(html, found):
    assert equations.spans(html) == found
    assert sorted(text_path_math(html)) == sorted(found)


def text_path_math(html: str) -> list[tuple[str, bool]]:
    """The math spans the text path (`normalize.fold` of `views.text`) reads, as (body, display): each span
    `mathspans.find` returns on the text it is given (also those it does not convert: math too long to read),
    and each `\\(..\\)` it reads as text, placed in that text where it replaced the `\\(..\\)`. As for any two
    spans, where two overlap the one that starts first is the span, so a `\\(..\\)` inside a span `find`
    returns is a part of that span's body."""
    spans, calls, placed = [], [], []
    find, display, sub = mathspans.find, normalize._display_or_paren, views.Seq.sub

    def spy_find(s, pads=None):
        out = find(s, pads)
        if pads is not None: return out    # a \\(..\\) left as `$..$`, read alone: the paren is its span
        spans.append([(x.start, x.end, x.body.replace(normalize._HELD_DOLLAR, "$"), x.display) for x in out])
        return out

    def spy_display(whole, body, *, inline):
        out = display(whole, body, inline=inline)
        if inline: calls.append((body, out))
        return out

    def spy_sub(self, pattern, repl, where=None):
        where = [] if where is None else where
        out = sub(self, pattern, repl, where)
        if pattern is normalize._PAREN_MATH: placed.extend(where)
        return out

    mathspans.find, normalize._display_or_paren, views.Seq.sub = spy_find, spy_display, spy_sub
    try:
        normalize.fold(views.text(html))
    finally:
        mathspans.find, normalize._display_or_paren, views.Seq.sub = find, display, sub
    assert len(spans) <= 1
    # Note: a `\\(..\\)` that is not math (`out` is None) is written as `$..$`, which `find` decides on.
    both = [(a, b, body, False) for (a, b), (body, out) in zip(placed, calls, strict=True)
            if out is not None or body.strip()]
    out, end = [], 0
    for a, b, body, display in sorted([*both, *(spans[0] if spans else [])], key=lambda x: x[0]):
        if a >= end:
            out.append((body, display))
            end = b
    return out


# Note: the text path writes a line of nothing but LaTeX as it is; it is math only to the equation path.
TOKEN = st.sampled_from(
    ["$", "$$", "\\$", "&#36;", "&dollar;", "\\(", "\\)", "\\[", "\\]", "x_1", "\\alpha", "<br>", "</p><p>",
     "word", "five words here", "5.00", " ", " ", "<math>x_1</math>", "<math display='block'>y^2</math>"])


@given(st.lists(TOKEN, min_size=1, max_size=12).map("".join))
def test_the_text_path_and_the_equation_path_read_the_same_spans(s):
    html = f"<p>{s}</p>"
    with mock.patch.object(equations, "_bare", lambda tex: False):
        assert sorted(equations.spans(html)) == sorted(text_path_math(html)), html


@given(st.text(st.sampled_from(list("$\\()[]x_1 <>&#;brp/")), max_size=14))
def test_the_text_view_that_tracks_its_source_is_the_text_view(s):
    q = views.reading(views.Seq.tracking(s))
    assert q.s == views.text(s)
    assert all(0 <= a <= b <= len(s) for a, b in zip(q.lo, q.hi, strict=True))


# 14. Linear in the size of the page, whatever the delimiters.
@pytest.mark.parametrize("s", ["$" * 20000, "$ " + "_a" * 10000 + "$", "&#36;" * 5000, "<br>$x$" * 3000])
def test_both_paths_are_linear_on_adversarial_pages(s):
    import time
    html = f"<p>{s}</p>"
    start = time.perf_counter()
    normalize.fold(views.text(html))
    equations.spans(html)
    assert time.perf_counter() - start < 2


# 15. A page with no dollar: `\[..\]` displays between paragraphs holding `\( .. \)`. A `\(..\)` the text path
# leaves as `$..$` (padded plain text) must not pair with the dollars of a display and swallow the paragraphs
# between them.
def test_displays_between_paragraphs_with_padded_plain_inline_math_are_found():
    html = ("<p>a nontrivial  \\( (k,g,s) \\) -multipole with  \\( s \\leq (k-2)g \\) , then</p>\n"
            "<p>\\[|G|\\geq b_{2}(k,g,s)\\geq\\frac{1}{2}M(k,g).\\]</p>\n"
            "<p>Proof. Note that  \\( b_{2}(k,g,s) \\geq 1 \\) . It is easy to check.</p>\n"
            "<p>\\[b_{2}(3,g-1,g-1)>b_{1}(3,g,g)\\]</p>")
    found = equations.spans(html)
    assert [t for t, d in found if d] == [
        "|G|\\geq b_{2}(k,g,s)\\geq\\frac{1}{2}M(k,g).", "b_{2}(3,g-1,g-1)>b_{1}(3,g,g)"]
    assert [t.strip() for t, d in found if not d] == ["(k,g,s)", "s \\leq (k-2)g", "b_{2}(k,g,s) \\geq 1"]
    assert equations.appears("b_2(3, g - 1, g - 1) > b_1(3, g, g)", html)[0]


# 16. A span's place is where its delimiters are in `_blocks(html)`, which `appears` and `in_text` slice: also
# after block tags (each gets a "\n" in `_blocks`) and a `\(..\)` too long to read, which the text path leaves
# as it is.
def test_a_spans_place_starts_and_ends_at_its_delimiters():
    long = "\\( \\in t$ " + "$x_1$ " * 30 + "q \\)"
    for html in (f"<p>a $b$ c</p><p>$s {long} $d$</p>\n<div>\\[e\\] and \\(f\\)</p><p>$$g$$ $h$</p>",
                 f"<p>$s {long} $d$ and $h$</p>"):
        s = equations._blocks(html)
        found = equations._spans(html)
        assert found
        for tex, _, start, stop in found:
            ends = (s[start:start + 2], s[stop - 2:stop])
            assert ends in {("\\(", "\\)"), ("\\[", "\\]"), ("$$", "$$")} or (
                s[start] == "$" and s[stop - 1] == "$"), (tex, s[start:stop])


# 17. A "<" that starts no tag is text, to both paths: a display with "p'<q<3p'" and "r<p ... )>0" in it (the
# "<p" and its "\\leq q ... )>" are not a tag), then inline spans.
def test_a_raw_less_than_in_math_is_no_tag_to_either_path():
    html = ("<p>$$\\begin{cases}a,&\\text{for }p'<q<3p';\\\\ b,&\\text{for }q\\leq p'.\\end{cases}$$</p>\n"
            "<p>If $1\\leq r<p\\leq q\\leq\\infty$ and $1+(1+\\omega)(\\frac{1}{q}-\\frac{1}{p})>0$ then</p>")
    assert [t for t, d in equations.spans(html) if not d] == [
        "1\\leq r<p\\leq q\\leq\\infty", "1+(1+\\omega)(\\frac{1}{q}-\\frac{1}{p})>0"]
    assert "<p\\leq q" in views.text(html)
