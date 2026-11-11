"""What the scorer promises for any output, checked on generated ones (Hypothesis): on the tests of
tests/fixtures/invariants/, and on the published dataset's when OPB_DATASET is set to its root.

    surroundings  a test's own answer (`test_invariants.answer`) passes with unrelated text around it,
                  in blocks of its own or in the answer's block
    symmetry      text folds the same as a test's string and as an output's text view, however the
                  output splits it into blocks
    digits        a number is found as written, and never with one digit changed
    edits         text within its `max_diffs` edits (substituted, inserted or dropped characters) is found
    no error      no HTML built from tags, entities, math, markdown and page marks is graded `error`

    HYPOTHESIS_PROFILE=deep pytest tests/test_properties.py    # 5,000 examples each, not 300
"""
from __future__ import annotations

import html as _html
import os

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st
from test_invariants import DATASET, answer, fixture_tests

from omni_parse_bench import data, normalize, views
from omni_parse_bench.scorers import unit_tests as scorer
from omni_parse_bench.scorers.unit_tests import runners

LIVE = bool(os.environ.get("OPB_DATASET")) and (DATASET / data.MANIFEST).exists()
TESTS = scorer.check(data.read_manifest(DATASET)[1]) if LIVE else fixture_tests()
HTML_TESTS = [t for t in TESTS if "html" in answer(t)]
INLINE_TESTS = [t for t in HTML_TESTS if answer(t)["html"].startswith("<p>")]
assert HTML_TESTS and INLINE_TESTS, "no html tests found: check tests/fixtures/invariants/ or OPB_DATASET"

# Filler no test asks for, and the marks a page prints around its text. Note: no bare "$": two of them
# around LaTeX-like text ("$ _ P < 0.05 $") read as math, as an OCR model's spaced "$ x_1 $" must.
WORD = st.sampled_from(["lorem", "ipsum", "dolor", "amet", "sed", "ut", "Vel", "QUIS", "A7", "x9"])
MARK = st.sampled_from(["$5.00", "$1,000", "US$5", "%", "____", "_", "x_1", "[1]", "...", "•", "—", "-",
                        "(", ")", "e.g.", "1,000", "12", "0.5", "&", "<", "¹", "ﬁ", " "])
TOKENS = st.lists(st.one_of(WORD, MARK), max_size=12)
PARAGRAPH = TOKENS.map(" ".join)


def paragraphs(xs: list[str]) -> str:
    return "".join(f"<p>{_html.escape(x, quote=False)}</p>" for x in xs)


@given(st.sampled_from(HTML_TESTS), st.lists(PARAGRAPH, max_size=3), st.lists(PARAGRAPH, max_size=3))
def test_an_answer_passes_with_paragraphs_around_it(t, before, after):
    [v] = scorer.score({"html": paragraphs(before) + answer(t)["html"] + paragraphs(after)}, [t])
    assert v.result == "pass", v.why


@given(st.sampled_from(INLINE_TESTS), PARAGRAPH, PARAGRAPH)
def test_an_answer_passes_with_text_around_it_in_its_paragraph(t, before, after):
    h = answer(t)["html"]
    head, tail = h[:-len("</p>")].replace("<p>", f"<p>{_html.escape(before, quote=False)} ", 1), "</p>"
    [v] = scorer.score({"html": f"{head} {_html.escape(after, quote=False)}{tail}"}, [t])
    assert v.result == "pass", v.why


@given(TOKENS.filter(bool), st.data())
def test_text_folds_the_same_however_an_output_splits_it_into_blocks(tokens, data):
    # Note: a block bounds a math span ("<p>$a</p><p>b$</p>" is not one), so with dollars the split matters.
    assume(not any("$" in x for x in tokens))
    cuts = sorted(data.draw(st.sets(st.integers(1, max(1, len(tokens) - 1)), max_size=len(tokens) - 1)))
    tag = data.draw(st.sampled_from(["p", "td", "li", "div"]))
    lines = [" ".join(tokens[i:j]) for i, j in zip([0, *cuts], [*cuts, len(tokens)], strict=True)]
    html = "".join(f"<{tag}>{_html.escape(x, quote=False)}</{tag}>" for x in lines)
    assert normalize.fold(views.text(html)) == normalize.fold(" ".join(tokens))


def math_test():
    """The first test whose answer holds `$U$`; skips when the set has none."""
    found = [t for t in HTML_TESTS if "$U$" in answer(t)["html"]]
    return found[0] if found else pytest.skip("no math test in this set")


def test_a_long_price_paragraph_before_math_does_not_take_the_maths_dollar():
    t = math_test()
    [v] = scorer.score({"html": f"<p>$5.00 {'a' * 100}</p>" + answer(t)["html"]}, [t])
    assert v.result == "pass", v.why


def written(digits: str, sep: str, frac: str, negative: bool, percent: bool) -> str:
    """`digits` as a page prints them: thousands marked by `sep`, a decimal part, a sign, a percent."""
    groups = [digits[max(0, i - 3):i] for i in range(len(digits), 0, -3)][::-1]
    return f"{'-' if negative else ''}{sep.join(groups)}{'.' + frac if frac else ''}{'%' if percent else ''}"


@given(st.integers(1_000, 10**9).map(str), st.sampled_from([",", " ", ""]), st.sampled_from(["", "5", "25"]),
       st.booleans(), st.booleans(), st.integers(0, 9), PARAGRAPH)
def test_a_number_is_found_as_written_and_never_with_a_digit_changed(digits, sep, frac, neg, pct, i, before):
    i %= len(digits)
    changed = digits[:i] + str((int(digits[i]) + 1) % 10) + digits[i + 1:]
    assume(changed[0] != "0")
    s, other = written(digits, sep, frac, neg, pct), written(changed, sep, frac, neg, pct)

    def page(x):
        return views.html(f"<p>{_html.escape(before, quote=False)}</p><p>{x}</p>")

    assume(runners.number(s) is not None and not runners.found(runners.Number(s), page(""))[0])
    assert runners.found(runners.Number(s), page(s))[0]
    assert not runners.found(runners.Number(s), page(other))[0]


@given(st.lists(WORD, min_size=2, max_size=8).map(" ".join), st.data())
def test_text_within_its_edits_is_found(text, data):
    k = data.draw(st.integers(1, max(1, len(text) // 5)))
    edits = data.draw(st.lists(st.tuples(st.integers(0, len(text) - 1), st.sampled_from("sid")),
                               min_size=k, max_size=k, unique_by=lambda e: e[0]))
    out = list(text)
    for i, kind in sorted(edits, reverse=True):
        if kind == "s":
            out[i] = "#"
        elif kind == "i":
            out.insert(i, "#")
        else:
            del out[i]
    assert runners.found(runners.Text(text, k), views.html(f"<p>{''.join(out)}</p>"))[0]


TAG = st.sampled_from([
    "<table>", "</table>", "<tr>", "</tr>", "<td>", "</td>", "<th>", "</th>", "<td rowspan='3'>",
    "<td colspan='0'>", "<td colspan='999'>", "<td rowspan='x'>", "<p>", "</p>", "<br>", "<ol start='0'>",
    "<li>", "</ol>", "<sup>", "<img alt='a'>", "<input type=checkbox checked>", "<math>", "</math>",
    "<math display='block'><mi>x</mi></math>", "$$", "\\[", "\\]", "\\(", "\\)", "{", "}", "^", "\\frac",
    "&#0;", "&amp;", "&#x1F600;", "\x00", "| a |", "|---|", "**", "# ", "\n", "​", "٣", "汉",
])


@given(st.sampled_from(HTML_TESTS), st.lists(st.one_of(WORD, MARK, TAG), max_size=40).map("".join))
def test_no_html_is_graded_an_error(t, html):
    [v] = scorer.score({"html": html}, [t])
    assert v.result != "error", v.why
