# ruff: noqa: E501
"""Relations of the `format` test: bold, italic, underline, strikethrough, superscript and subscript. A format test
reads the output's markup (`marks.read`), where every other test reads the text view and is certified not to see
styling (M7a). The relations say when the two readers must agree on a page (M64), and what a mark is and is not."""
from __future__ import annotations

import string

from hypothesis import assume, example, given
from hypothesis import strategies as st
from test_invariants import answer, fixture_tests
from test_properties import MARK, TESTS, WORD

from metamorphic.common import (HOLDS, LIMITATION, deviation, escaped, every_real_test, is_exact, passes, relation,
                                text_strings)
from omni_parse_bench import markdown, marks, views
from omni_parse_bench.scorers.unit_tests import runners

KINDS = marks.KINDS
# The elements and styles that make each mark, as the page writes them
SPELLINGS = {
    "bold": ["<b>{}</b>", "<strong>{}</strong>", '<span style="font-weight:bold">{}</span>',
             '<span style="font-weight: 700">{}</span>'],
    "italic": ["<i>{}</i>", "<em>{}</em>", '<span style="font-style:italic">{}</span>'],
    "underline": ["<u>{}</u>", "<ins>{}</ins>", '<span style="text-decoration:underline">{}</span>'],
    "strike": ["<s>{}</s>", "<strike>{}</strike>", "<del>{}</del>", '<span style="text-decoration: line-through">{}</span>'],
    "sup": ["<sup>{}</sup>", '<span style="vertical-align:super">{}</span>'],
    "sub": ["<sub>{}</sub>", '<span style="vertical-align:sub">{}</span>'],
}
N_SPELLINGS = sum(len(v) for v in SPELLINGS.values())
KIND = st.sampled_from(KINDS)
LETTERS = st.text(string.ascii_lowercase, min_size=3, max_size=7)
# Distinct words, so a context never occurs twice by chance: before, span and after
PHRASE = st.lists(LETTERS, min_size=3, max_size=9, unique=True).flatmap(
    lambda ws: st.tuples(st.integers(1, len(ws) - 2), st.integers(1, 3)).map(
        lambda ij: (" ".join(ws[:ij[0]]) + " ", " ".join(ws[ij[0]:ij[0] + ij[1]]), " " + " ".join(ws[ij[0] + ij[1]:]))
    ).filter(lambda t: t[2].strip()))


def fmt(before: str, span: str, after: str, kind: str | None = None, absent: str | None = None):
    """A format test: `kind` on the span (positive), or `absent` on it (negative)."""
    return runners.Format(before, span, after, 0, (kind,) if kind else (), (absent,) if absent else ())


def elsewhere(kind: str) -> str:
    """A paragraph with a mark of another kind: a page that has some mark, which a negative test needs."""
    tag = "b" if kind != "bold" else "i"
    # Note: digits, which no phrase has, so the text after a context never completes one a character short of it
    return f"<p><{tag}>9999</{tag}></p>"


def page(before: str, span: str, after: str, wrap: str = "{}") -> str:
    return f"<p>{escaped(before)}{wrap.format(escaped(span))}{escaped(after)}</p>"


@relation(HOLDS, domain="any 3-9 distinct words split into before, span and after (1-3 words), x 6 marks")
@given(PHRASE, KIND)
@example(("the ", "total", " due"), "bold")
def test_removing_the_mark_from_the_span_fails_a_positive_test_and_passes_a_negative_one(phrase, kind):
    """A positive format test passes on a page that marks its span and fails on the same words unmarked; a
    negative one (the span carries none of the listed marks) does the opposite. [M53]
    Why it matters for a score: a system that drops the marks of a page is told so, and one that keeps them is not
    penalised for the plain words around them."""
    # Given a phrase with its span marked in one of the 6 ways a page can mark text
    before, span, after = phrase
    marked, plain = page(*phrase, SPELLINGS[kind][0]), page(*phrase) + elsewhere(kind)
    # When the positive and the negative test run on the marked page and on the plain one (with a mark elsewhere)
    # Then the positive passes only on the marked page and the negative only on the plain one
    assert passes(fmt(*phrase, kind=kind), marked) and not passes(fmt(*phrase, kind=kind), plain)
    assert passes(fmt(*phrase, absent=kind), plain) and not passes(fmt(*phrase, absent=kind), marked)


@relation(HOLDS, domain=f"{N_SPELLINGS} (mark, spelling) pairs, phrases drawn by Hypothesis")
@given(PHRASE, st.sampled_from([(k, s) for k, ss in SPELLINGS.items() for s in ss]))
def test_every_element_and_style_that_marks_text_gives_the_same_verdict(phrase, kind_and_spelling):
    """`<b>`, `<strong>` and `font-weight: bold` or 700 are one mark; so are `<i>`, `<em>` and `font-style:
    italic`; `<s>`, `<strike>`, `<del>` and `line-through`; `<u>`, `<ins>` and `underline`; `<sup>` and
    `vertical-align: super`; `<sub>` and `sub`. A test for the mark passes on each spelling. [M52]
    Why it matters for a score: a system is not asked to guess which element the gold's author had in mind."""
    # Given a phrase marked with one spelling of a mark; When its positive test runs; Then it passes
    kind, spelling = kind_and_spelling
    assert passes(fmt(*phrase, kind=kind), page(*phrase, spelling))


@relation(HOLDS, domain="bold, italic and strikethrough, as markdown and as HTML")
@given(PHRASE, st.sampled_from([("bold", "**{}**", "<strong>{}</strong>"), ("italic", "*{}*", "<em>{}</em>"),
                                ("strike", "~~{}~~", "<del>{}</del>")]))
def test_markdown_and_html_give_the_same_format_verdicts(phrase, spelling):
    """A phrase with its span in `**bold**`, `*italic*` or `~~strikethrough~~`, turned to HTML by the markdown
    converter, gets the same verdicts, positive and negative, as the same phrase in `<strong>`, `<em>` or `<del>`.
    Markdown text without the markers gets the verdict of the plain page. [M51]
    Why it matters for a score: as for M6a, a system that answers in markdown is graded like one that answers in HTML."""
    # Given the phrase as markdown and as HTML; When the tests run on both; Then they agree
    kind, md_mark, html_mark = spelling
    before, span, after = phrase
    md = markdown.to_html(f"{before}{md_mark.format(span)}{after}")
    html = page(*phrase, html_mark)
    plain_md = markdown.to_html(f"{before}{span}{after}")
    for p in (fmt(*phrase, kind=kind), fmt(*phrase, absent=kind)):
        assert passes(p, md) == passes(p, html)
        assert passes(p, plain_md) == passes(p, page(*phrase))
    assert passes(fmt(*phrase, kind=kind), md)


@relation(HOLDS, domain="phrases x 6 marks, the whole page marked")
@given(PHRASE, KIND)
def test_marking_the_whole_page_fails_a_positive_test_and_a_negative_one(phrase, kind):
    """A positive test fails on a page that marks its span and every word around it, since the mark is not the span's;
    a negative test fails there too, since the span carries the mark. [M54]
    Why it matters for a score: a system cannot pass every mark test by marking everything."""
    # Given the whole paragraph marked; When the positive and the negative test run; Then both fail
    html = f"<p>{SPELLINGS[kind][0].format(escaped(''.join(phrase)))}</p>"
    assert not passes(fmt(*phrase, kind=kind), html) and not passes(fmt(*phrase, absent=kind), html)


@relation(HOLDS, domain="phrases x 6 marks x paragraphs of words and marks around the answer")
@given(PHRASE, KIND, st.lists(st.lists(st.one_of(WORD, MARK), max_size=6).map(" ".join), max_size=3), KIND)
def test_marks_elsewhere_and_other_marks_on_the_span_change_no_format_verdict(phrase, kind, others, other):
    """Paragraphs around the answer, each wholly in some mark, and a different mark on the span, change no verdict:
    a positive test still passes, a negative one for another mark still passes. [M55]
    Why it matters for a score: the verdict depends on the span and the words next to it, not the rest of the page."""
    # Given the answer for a positive and a negative test, with marked paragraphs around it
    assume(other != kind)
    around = "".join(f"<p>{SPELLINGS[kind][0].format(escaped(x))}{SPELLINGS[other][0].format(escaped(x))}</p>" for x in others)
    html = around + page(*phrase, SPELLINGS[other][0].format(SPELLINGS[kind][0])) + around
    # When the tests run; Then the positive passes (the span carries both) and a negative for a third mark passes
    assert passes(fmt(*phrase, kind=kind), html) and passes(fmt(*phrase, kind=other), html)
    third = next(k for k in KINDS if k not in (kind, other))
    assert passes(fmt(*phrase, absent=third), html)


@relation(HOLDS, domain="phrases x 6 marks x runs written in 5 ways")
@given(PHRASE, KIND, st.sampled_from(["split", "spaced", "nested-out", "nested-in", "paragraphs"]))
def test_a_run_of_a_mark_is_one_run_however_the_page_splits_or_nests_it(phrase, kind, how):
    """A span of several words marked as adjacent runs (`<b>a</b><b>b</b>`), as runs with a space between, with
    the tags nested in either order, or across a paragraph break, is one run: its positive test passes, and a
    span marked only in its first half fails. [M56]
    Why it matters for a score: one system writes a mark per word, another per line; the page looks the same."""
    before, span, after = phrase
    assume(len(span.split()) > 1)
    words = [escaped(w) for w in span.split()]
    wrap = SPELLINGS[kind][0].format
    other = SPELLINGS["bold" if kind != "bold" else "italic"][0].format
    inner = {"split": "".join(wrap(w) for w in words), "spaced": " ".join(wrap(w) for w in words),
             "nested-out": wrap(other(" ".join(words))), "nested-in": other(wrap(" ".join(words))),
             "paragraphs": "</p><p>".join(wrap(w) for w in words)}[how]
    html = f"<p>{escaped(before)}{inner}{escaped(after)}</p>"
    assert passes(fmt(*phrase, kind=kind), html), html
    half = f"<p>{escaped(before)}{wrap(words[0])} {' '.join(words[1:])}{escaped(after)}</p>"
    assert not passes(fmt(*phrase, kind=kind), half), half


@relation(HOLDS, domain="phrases with a variant of the page's characters: case, spaces, entities, dashes, quotes, fullwidth")
@given(PHRASE, KIND, st.sampled_from(["upper", "nbsp", "newlines", "entities", "curly", "dashes", "fullwidth"]))
def test_the_page_in_another_case_spacing_or_typography_gives_the_same_format_verdict(phrase, kind, change):
    """A marked page folds the way a text test's page does (case, white space, entities, dashes, quotes, the
    fullwidth compatibility forms), and the marks of its characters stay where they were: the verdict is the same. [M57a]
    Why it matters for a score: the words are compared as the other tests compare them, so a format test fails for the
    mark, not for the typography."""
    before, span, after = phrase
    # Given a span with a hyphen and an apostrophe, written in the page in one of 7 variants
    span = span.replace(" ", "-", 1) if " " in span else span + "'s"
    ph = (before, span, after)
    variants = {"upper": lambda s: s.upper(), "nbsp": lambda s: s.replace(" ", " "),
                "newlines": lambda s: s.replace(" ", "\n"), "entities": lambda s: s.replace(" ", "&#32;"),
                "curly": lambda s: s.replace("'", "’"), "dashes": lambda s: s.replace("-", "–"),
                "fullwidth": lambda s: "".join(chr(ord(c) + 0xFEE0) if c.isascii() and c.isalpha() else c for c in s)}
    html = "<p>" + variants[change](escaped(before)) + SPELLINGS[kind][0].format(variants[change](escaped(span))) \
        + variants[change](escaped(after)) + "</p>"
    assert passes(fmt(*ph, kind=kind), html) and not passes(fmt(*ph, absent=kind), html), html


@relation(LIMITATION)
@deviation("M57b")
def test_a_letter_and_its_combining_accent_marked_differently_still_fold_together():
    """A page that marks a base letter and writes its combining accent outside the mark is read as the accented letter
    marked. [M57b]
    Why it matters for a score: the accent belongs to its letter."""
    # Given the span 'café' where the page marks 'cafe' and leaves the combining acute plain
    html = "<p>the <b>cafe</b>́ near</p>"
    # When a bold test for 'café' runs; Then it passes
    assert passes(fmt("the ", "café", " near", kind="bold"), html)


@relation(HOLDS, domain="phrases x 6 marks x one wrong, missing or added character in the words before or after the span")
@given(PHRASE, KIND, st.sampled_from(["wrong", "missing", "added"]), st.booleans(), st.data())
def test_a_context_with_a_wrong_missing_or_added_character_is_not_found(phrase, kind, change, in_before, data):
    """A format test has no edit budget: a page whose context has one character wrong, missing or added does not hold
    the context, so a positive test and a negative one both fail, with the page otherwise right. [M58]
    Why it matters for a score: the context is what anchors the span, and a context that is not as the gold has it is
    not a place to read a mark from; a misread word is the text tests' business."""
    # Given a page whose words before (or after) the span have one letter changed, and a mark elsewhere
    before, span, after = phrase
    part = before if in_before else after
    # Note: a character added before the context's first character is outside it, so the context is still there
    spots = [i for i, c in enumerate(part) if c.isalpha() and (change != "added" or not in_before or i > 0)]
    assume(spots)
    i = data.draw(st.sampled_from(spots))
    edited = part[:i] + {"wrong": "0", "missing": "", "added": "0" + part[i]}[change] + part[i + 1:]
    html = page(edited if in_before else before, span, after if in_before else edited, SPELLINGS[kind][0])
    html += elsewhere(kind)
    # When the positive and the negative test run; Then neither finds its context
    assert not passes(fmt(before, span, after, kind=kind), html), html
    assert not passes(fmt(before, span, after, absent=kind), html), html


@relation(HOLDS, domain="phrases x 6 marks x 3 places: maths (read, no mark), a script and a comment (not read)")
@given(PHRASE, KIND, st.sampled_from([("<math>{}</math>", True), ("<script>{}</script>", False), ("<!--{}-->", False)]))
def test_a_mark_inside_maths_a_script_or_a_comment_is_not_a_mark(phrase, kind, region):
    """A page that marks the span only inside `<math>` fails the positive test and passes the negative one (the
    text is there, without a mark); inside a `<script>` or a comment the text is not on the page at all, so both
    fail. [M59a]
    Why it matters for a score: maths is graded by its own tests, and a hidden script is not on the page."""
    # Given the span marked inside one of the places, and a mark elsewhere on the page; When the tests run
    region, shown = region
    before, span, after = phrase
    inner = region.format(SPELLINGS[kind][0].format(escaped(span)))
    html = f"<p>{escaped(before)}{inner}{escaped(after)}</p>" + elsewhere(kind)
    # Then the positive fails; the negative passes where the text is shown and fails where it is not
    assert not passes(fmt(*phrase, kind=kind), html)
    assert passes(fmt(*phrase, absent=kind), html) == shown


@relation(HOLDS, domain="phrases x 6 marks x code, preformatted text and keyboard input")
@given(PHRASE, KIND, st.sampled_from(["<code>{}</code>", "<pre>{}</pre>", "<kbd>{}</kbd>"]))
def test_code_and_preformatted_text_carry_marks_like_any_other_text(phrase, kind, region):
    """A page that marks the span inside `<code>`, `<pre>` or `<kbd>` passes the positive test: the text is read
    and carries the mark that is drawn on it. [M59c]
    Why it matters for a score: code in a document is bolded and italicised as any text is."""
    # Given the span marked inside code; When the positive test runs; Then it passes
    before, span, after = phrase
    html = f"<p>{escaped(before)}{region.format(SPELLINGS[kind][0].format(escaped(span)))}{escaped(after)}</p>"
    assert passes(fmt(*phrase, kind=kind), html)


@relation(HOLDS, domain="8 pages: LaTeX, Unicode scripts, raw markdown and other elements that are not marks")
@given(st.sampled_from([
    ("x", "2", "<p>x$^{2}$ and more</p>", "sup"), ("x", "2", "<p>x² and more</p>", "sup"),
    ("h", "2", "<p>h$_2$o and more</p>", "sub"), ("the ", "total", "<p>the **total** due</p>", "bold"),
    ("the ", "total", "<p>the <mark>total</mark> due</p>", "bold"), ("the ", "total", "<p>the <a href='#'>total</a> due</p>", "underline"),
    ("the ", "total", "<table><tr><th>the total</th></tr></table>", "bold"), ("the ", "total", "<h2>the total</h2>", "bold"),
]))
def test_latex_unicode_scripts_raw_markdown_and_other_elements_are_not_marks(case):
    """`$x^{2}$`, a Unicode superscript, `**x**` written in an HTML output, `<mark>`, `<a>`, a heading and a table
    heading make no mark: their positive format test fails. [M59b]
    Why it matters for a score: a mark is a markup mark; maths is graded by its own tests and a heading is a layout."""
    # Given a page that looks marked but carries no mark; When the positive test runs; Then it fails
    before, span, html, kind = case
    after = " more" if "more" in html else " due" if "due" in html else ""
    assert not passes(fmt(before, span, after, kind=kind), html), html


@relation(HOLDS, domain="phrases x 4 styles: 2 that take a mark off, 2 that a browser ignores")
@given(PHRASE, st.sampled_from([("bold", "b", "font-weight:normal", True), ("italic", "i", "font-style:normal", True),
                                ("underline", "u", "text-decoration:none", False),
                                ("sup", "sup", "vertical-align:baseline", False)]))
def test_a_style_takes_bold_or_italic_off_the_text_but_not_an_underline_or_a_script(phrase, spelling):
    """A span inside `<b>` or `<i>` with `font-weight: normal` or `font-style: normal` carries no mark, and the words
    around it, in the element, do; inside `<u>` or `<sup>`, `text-decoration: none` and `vertical-align: baseline`
    change nothing, as in a browser, so the span stays underlined or superscript. [M60]
    Why it matters for a score: the page's look is what the mark tests ask about, not its element names."""
    # Given a run in the element, with its span in a span that has the style
    kind, tag, style, cancels = spelling
    before, span, after = phrase
    html = f"<p><{tag}>{escaped(before)}<span style=\"{style}\">{escaped(span)}</span>{escaped(after)}</{tag}></p>"
    if cancels:
        assert not passes(fmt(*phrase, kind=kind), html) and passes(fmt(*phrase, absent=kind), html)
    else:
        only = f"<p><{tag}><span style=\"{style}\">{escaped(span)}</span></{tag}></p>"
        assert passes(runners.Format(None, span, None, 0, (kind,), ()), only)


@relation(HOLDS, domain="phrases x 6 marks: the context twice, one place marked")
@given(PHRASE, KIND)
def test_a_context_that_occurs_twice_passes_a_positive_test_if_either_place_does_and_a_negative_if_neither_does(phrase, kind):
    """When the page holds the context twice, a positive format test passes if either place carries the mark on the
    span (and nothing around it), and a negative one passes only when neither does. [M61]
    Why it matters for a score: a repeated phrase is judged by where it is marked, and no test passes on a single
    unmarked copy while another is marked, or the reverse."""
    # Given a page with the phrase plain, then marked, and the two orders
    plain, marked = page(*phrase), page(*phrase, SPELLINGS[kind][0])
    # When the tests run on the pair; Then the positive passes on either order, the negative on neither
    for html in (plain + marked, marked + plain):
        assert passes(fmt(*phrase, kind=kind), html) and not passes(fmt(*phrase, absent=kind), html)
    assert passes(fmt(*phrase, absent=kind), plain + plain + elsewhere(kind))


@relation(HOLDS, domain="every fixture format test")
def test_a_format_tests_own_answer_passes_and_its_plain_page_gets_the_opposite_verdict():
    """A format test's own answer passes it; the same words unmarked fail a positive test, and pass a negative one only
    when the page has a mark elsewhere; an empty page passes none. [M62]
    Why it matters for a score: the two sides of every format test are checked, not only its own answer."""
    # Note: the fixtures, always: the published dataset holds no format test
    formats = [t for t in fixture_tests() if isinstance(t.params, runners.Format)]
    assert formats, "no format tests: check tests/fixtures/invariants/"
    for t in formats:
        p = t.params
        own = answer(t)["html"]
        plain = f"<p>{escaped((p.before or '') + p.span + (p.after or ''))}</p>"
        assert passes(p, own) and not passes(p, ""), t.id
        assert passes(p, plain + elsewhere("sub")) == bool(p.absent), t.id
        assert not passes(p, plain), t.id       # no mark anywhere: a negative test has nothing to be scored on


@relation(HOLDS, domain="strings of tags, entities, markdown and marks")
@given(st.text(alphabet="<>/&;=\"' !-abisupbdlm\n", max_size=60), PHRASE, KIND)
def test_no_output_makes_the_format_reader_raise_or_a_format_test_error(soup, phrase, kind):
    """Any string, however broken its tags, is read and graded: a verdict, never an error. [M63]
    Why it matters for a score: one odd page must not stop a run."""
    # Given an arbitrary string as the output; When positive and negative tests run on it; Then each gives a verdict
    for p in (fmt(*phrase, kind=kind), fmt(*phrase, absent=kind)):
        assert passes(p, soup) in (True, False)


@relation(HOLDS, domain="phrases x 6 marks x answers of every other test type, wholly marked")
@given(st.sampled_from([t for t in TESTS if "html" in answer(t) and not isinstance(t.params, runners.Format)]),
       st.lists(st.sampled_from(["b", "i", "u", "s", "sup", "sub", "strong", "em"]), min_size=1, max_size=4))
def test_marking_every_word_of_the_page_changes_no_verdict_of_any_other_test(t, tags):
    """The answer of a text, number, order, repeat or table_cell test with its whole page inside any stack of the
    mark elements passes as it did without them. [M64]
    Why it matters for a score: adding the format reader must not change a single verdict of a test that does not ask
    about marks (as M7a, for the whole page and every mark)."""
    html = answer(t)["html"]
    wrapped = "".join(f"<{x}>" for x in tags) + html + "".join(f"</{x}>" for x in reversed(tags))
    exact = is_exact(t.params)
    assert passes(t.params, wrapped, exact=exact) == passes(t.params, html, exact=exact), wrapped


@every_real_test("text strings")
def test_every_real_text_string_as_a_bold_span_passes_when_bold_and_fails_when_plain():
    """Each text string of the real tests, written alone as a bold span, passes a bold test on a page that sets it
    bold, fails that test on the plain string, and passes the negative one there (with a mark elsewhere). [M53]
    Why it matters for a score: the reader and the fold agree on every string the dataset has, not only on the
    generated ones."""
    # Given every real text string with a letter or digit left after folding
    bad, n = [], 0
    for t in TESTS:
        for x in text_strings(t.params):
            if not marks.fold(x):
                continue
            n += 1
            p = runners.Format(None, x, None, 0, ("bold",), ())
            if not (passes(p, f"<p><b>{escaped(x)}</b></p>") and not passes(p, f"<p>{escaped(x)}</p>")
                    and passes(p._replace(marks=(), absent=("bold",)), f"<p>{escaped(x)}</p>" + elsewhere("bold"))):
                bad.append(x[:40])
    assert n and not bad, f"{len(bad)}/{n} real strings: {bad[:6]}"


def _tree(depth: int):
    """A word, or an element (a mark element, a plain `span`, a style that makes or cancels a mark) of trees."""
    word = LETTERS.map(lambda w: ("w", w))
    if depth == 0:
        return word
    inner = st.deferred(lambda: _tree(depth - 1))
    elements = st.sampled_from([(f.split(">")[0][1:].split(" ")[0], f) for fs in SPELLINGS.values() for f in fs]
                               + [("span", '<span style="font-weight:normal">{}</span>'),
                                  ("span", '<span style="font-style:normal">{}</span>'), ("span", "<span>{}</span>")])
    return st.one_of(word, st.tuples(st.just("e"), elements, st.lists(inner, min_size=1, max_size=3)))


def _expected(tree, above=frozenset()):
    """The (word, marks) pairs of a tree, from its elements alone: the model the reader is checked against."""
    if tree[0] == "w":
        return [(tree[1], above)]
    (_, spelling), children = tree[1], tree[2]
    here = set(above)
    for kind, forms in SPELLINGS.items():
        if spelling in forms:
            here.add(kind)
    for style, kind in (("font-weight:normal", "bold"), ("font-style:normal", "italic")):
        if style in spelling:
            here.discard(kind)
    # Note: a script style replaces the other script, as in a browser
    if "vertical-align:super" in spelling:
        here.discard("sub")
    if "vertical-align:sub" in spelling:
        here.discard("sup")
    return [x for c in children for x in _expected(c, frozenset(here))]


def _html(tree) -> str:
    if tree[0] == "w":
        return tree[1] + " "
    return tree[1][1].format("".join(_html(c) for c in tree[2]))


@relation(HOLDS, domain="trees of up to 3 levels of mark elements, plain spans and cancelling styles, 3 words wide")
@given(st.lists(_tree(3), min_size=1, max_size=4))
def test_each_character_carries_the_marks_of_the_elements_around_it_and_no_others(trees):
    """On a page built from nested mark elements, plain spans and styles that cancel a mark, every character of
    every word carries exactly the marks the elements and styles around it make, read from the tree itself and not
    from the reader. [M65]
    Why it matters for a score: the reader is checked against a model of what a page's markup means, not only
    against the cases the other relations draw."""
    # Given a page built from a tree; When it is read; Then each word's characters carry the model's marks
    html = "<p>" + "".join(_html(t) for t in trees) + "</p>"
    words = [x for t in trees for x in _expected(t)]
    read = marks.read(html)
    at = 0
    for word, expected in words:
        for i in range(at, at + len(word)):
            assert read.marks[i] == expected, (html, word, set(read.marks[i]), set(expected))
        at += len(word)
    assert at == len(read.text)


@relation(HOLDS, domain="3 pages of 20,000 start tags: never closed, closed by another tag, and nested 30,000 deep")
@given(st.sampled_from(["<b>x" * 20000 + "</i>" * 20000, "<i><b>x</i>" * 8000, "<b>" * 30000 + "x"]))
def test_a_page_of_tens_of_thousands_of_unclosed_or_crossed_tags_is_read_in_bounded_time(html):
    """A page of tens of thousands of start tags that are never closed, are closed by the wrong end tag or nest
    thirty thousand deep is read in under five seconds, and its format tests give a verdict. [M66]
    Why it matters for a score: one broken output must not hold up a run (the first reader took 43 seconds on
    the first of these)."""
    import time

    # Given the page; When a format test reads it; Then a verdict comes within 5 seconds
    start = time.monotonic()
    assert passes(fmt("", "x", "", kind="bold"), html) in (True, False)
    assert time.monotonic() - start < 5


@relation(HOLDS, domain="words ending in a letter, a span repeating that letter 2-4 times, x 6 marks")
@given(LETTERS, st.integers(2, 4), KIND)
@example("vrbg", 3, "bold")
def test_a_span_whose_letters_repeat_the_end_of_the_context_before_it_is_found_where_it_sits(word, repeats, kind):
    """A span of one letter repeated (`ggg`) after a context word ending in that letter (`vrbg`) is found where the page
    puts it, and its mark is read there, not on the letters before it. [M67]
    Why it matters for a score: the span sits one character from where a search for its letters alone would find it,
    and a verdict must not depend on which of the two is looked at."""
    # Given a context word ending in the span's letter, and the span marked
    span = word[-1] * repeats
    before, after = f"{word} ", " tail words"
    html = f"<p>{before}{SPELLINGS[kind][0].format(span)}{after}</p>"
    # When the positive test runs; Then it passes
    assert passes(fmt(before, span, after, kind=kind), html), html


@relation(HOLDS, domain="phrases x 6 marks: an output with no mark, and the same with one mark elsewhere")
@given(PHRASE, KIND)
def test_a_negative_test_is_scored_only_on_an_output_that_has_a_mark_somewhere(phrase, kind):
    """A negative format test fails on an output that has no mark on any of its text, whatever it says (empty mark
    elements do not count), and passes on the same words with a mark of another kind somewhere else on the page; a
    positive test is not changed by it. [M68]
    Why it matters for a score: a system that writes no marks at all is not given credit for 'not marking' text it
    could not have marked."""
    # Given the plain page, and the plain page with a mark elsewhere
    plain = page(*phrase)
    # When a negative and a positive test run on both; Then the negative needs the mark elsewhere
    assert not passes(fmt(*phrase, absent=kind), plain)
    assert passes(fmt(*phrase, absent=kind), plain + elsewhere(kind))
    # an element that marks no text does not count as a mark: empty, whitespace only, or an icon
    for empty in ("<b></b>", "<i> </i>", "<i class=fa></i>", "<p><u><span></span></u></p>"):
        assert not passes(fmt(*phrase, absent=kind), plain + empty), empty
    assert not passes(fmt(*phrase, kind=kind), plain) and not passes(fmt(*phrase, kind=kind), plain + elsewhere(kind))


@relation(HOLDS, domain="words repeated inside the context, the real span plain or marked, x 6 marks")
@given(LETTERS, LETTERS, KIND)
def test_the_contexts_own_place_decides_which_copy_of_the_span_is_read(word, other, kind):
    """When the span's words occur again inside the context (`before` or `after`), only the copy at the span's place
    is the span: marking the other copy does not pass a positive test and does not fail a negative one. [M69]
    Why it matters for a score: a repeated word must not let a mark on one copy stand for the other."""
    assume(word != other and "tail" not in word + other)
    before, span, after = f"{word} {other} ", word, f" {other} tail"
    # Given the page with the copy in `before` marked and the span plain, or the reverse
    wrap = SPELLINGS[kind][0]
    copy_marked = f"<p>{wrap.format(word)} {other} {word}{after}</p>" + elsewhere(kind)
    span_marked = f"<p>{word} {other} {wrap.format(word)}{after}</p>"
    # When the tests run; Then the span is read at its own place
    assert not passes(fmt(before, span, after, kind=kind), copy_marked)
    assert passes(fmt(before, span, after, absent=kind), copy_marked)
    assert passes(fmt(before, span, after, kind=kind), span_marked)


@relation(HOLDS, domain="phrases x 6 unclosed starts of a page (head, head and title, title, bare text, a div)")
@given(PHRASE, KIND, st.sampled_from(["<html><head>", "<html><head><title>t", "<title>t<body>", "<head>intro ",
                                      "<head><meta><div>", "<head><noscript>n</noscript> "]))
def test_an_unclosed_head_or_title_does_not_hide_the_page_from_the_format_reader(phrase, kind, start):
    """A page whose `<head>` or `<title>` is never closed is read as the text test reads it: nothing is hidden,
    so its text is read and its marks are there. [M70]
    Why it matters for a score: one odd page must not turn every format test on it into a failure while the other
    tests of the page pass."""
    # Given the answer after an unclosed head; When the positive format test and a text test run
    before, span, after = phrase
    html = start + page(*phrase, SPELLINGS[kind][0])
    # Then both pass
    assert passes(fmt(*phrase, kind=kind), html), html
    assert passes(runners.Present(runners.Text(f"{before}{span}{after}".strip(), 0)), html), html


@relation(HOLDS, domain="phrases x 2 crossed pairs of marks")
@given(PHRASE, st.sampled_from([("<b><i>", "</b>", "</i>", "italic", "bold"), ("<i><b>", "</i>", "</b>", "bold", "italic")]))
def test_a_mark_that_an_end_tag_crosses_goes_on_after_it(phrase, crossed):
    """In `<b><i>a</b> b</i>` the first word is bold and italic and the second only italic, as a browser draws it:
    the italic that the end tag of the bold crossed goes on after it. [M71]
    Why it matters for a score: untidy tags are common in model output, and the page looks the same either way."""
    # Given two words, the first inside both marks and the second inside only the one that closes last
    before, span, after = phrase
    open_, first_end, second_end, kept, dropped = crossed
    assume(len(span.split()) == 1)
    html = f"<p>{escaped(before)}{open_}x{first_end} {escaped(span)}{second_end}{escaped(after)}</p>"
    # When the second word is tested for the mark that goes on, and for the one that ended
    # Then it has the first and not the second
    assert passes(runners.Format(None, span, None, 0, (kept,), ()), html), html
    assert passes(fmt(before + "x ", span, after, absent=dropped), html), html
    assert not passes(runners.Format(None, span, None, 0, (dropped,), ()), html), html


@relation(HOLDS, domain="phrases x 6 marks x a mark that takes in the punctuation next to the span or stops before it")
@given(PHRASE, KIND, st.sampled_from([",", ".", ":", ";", ")", "?"]), st.booleans())
def test_a_mark_that_takes_in_or_leaves_out_the_punctuation_next_to_the_span_is_the_same_mark(phrase, kind, punct, inside):
    """A span followed by a punctuation mark passes its positive test whether the page's mark covers the punctuation
    (`<b>total,</b>`) or stops before it (`<b>total</b>,`); only letters and digits are looked at, and the words
    around the span are the letter or digit on each side of it. [M72]
    Why it matters for a score: where a vendor ends a mark next to a comma is not a reading difference."""
    # Given the span followed by a punctuation mark in the context, the mark covering it or not
    before, span, after = phrase
    after = punct + after
    wrap = SPELLINGS[kind][0]
    html = (f"<p>{escaped(before)}{wrap.format(escaped(span + punct) if inside else escaped(span))}"
            f"{'' if inside else escaped(punct)}{escaped(after[1:])}</p>")
    # When the positive test runs; Then it passes
    assert passes(fmt(before, span, after, kind=kind), html), html


@relation(HOLDS, domain="phrases x 4 elements with a style that takes off their own mark, and a font shorthand")
@given(PHRASE, st.sampled_from([("underline", "u", "text-decoration:none"), ("strike", "s", "text-decoration:none"),
                                ("sup", "sup", "vertical-align:baseline"), ("sub", "sub", "vertical-align:baseline"),
                                ("bold", "b", "font: 12px serif"), ("italic", "i", "font: 12px serif")]))
def test_an_elements_own_style_takes_off_its_own_default_mark_but_not_an_ancestors(phrase, element):
    """`<u>`, `<s>`, `<sup>` and `<sub>` with `text-decoration: none` or `vertical-align: baseline`, and `<b>` or `<i>`
    with a `font` shorthand that names no weight or style, carry no mark of their own; inside an ancestor that makes the
    same mark, the text keeps it. [M73]
    Why it matters for a score: the page's look is what the mark tests ask about; a style that makes the text plain
    makes it plain, and one that cannot undo an ancestor's underline does not."""
    # Given the element with the style around the span, alone and inside the ancestor that makes the same mark
    kind, tag, style = element
    before, span, after = phrase
    alone = f'<p>{escaped(before)}<{tag} style="{style}">{escaped(span)}</{tag}>{escaped(after)}</p>' + elsewhere(kind)
    # When the positive and the negative tests run; Then it has no mark of its own
    assert not passes(fmt(*phrase, kind=kind), alone) and passes(fmt(*phrase, absent=kind), alone)
    ancestor = SPELLINGS[kind][0].format(f'<{tag} style="{style}">{escaped(span)}</{tag}>')
    inside = f"<p>{escaped(before)}{ancestor}{escaped(after)}</p>"
    if kind in ("bold", "italic"):
        # Note: a style that makes the text plain takes the ancestor's bold or italic off too
        assert not passes(fmt(*phrase, kind=kind), inside)
    else:
        assert passes(fmt(*phrase, kind=kind), inside), inside


PIECES = ["<p>{w}</p>", "<b>{w}</b>", "<head>{w}</head>", "<head>{w}", "<title>{w}</title>", "<title>{w}",
          "<script>{w}</script>", "<style>{w}</style>", "<!--{w}-->", "<!DOCTYPE html>{w}",
          "<head><title>{w} <b>{w}</b></title></head>", "<i>{w}", "<script>{w}"]


@relation(HOLDS, domain="pages of up to 6 pieces from 13: closed and unclosed head, title, script, style, comments")
@given(st.lists(st.tuples(st.sampled_from(PIECES), LETTERS), min_size=1, max_size=6))
def test_the_format_reader_hides_what_the_text_view_hides_and_reads_what_it_reads(pieces):
    """On a page of paragraphs, marks, comments, a doctype and head, title, script and style elements, closed or
    not, the text the format reader finds is the text `views.html` shows, once folded: an element hidden when an end
    tag closes it, and read as text when none does. [M74]
    Why it matters for a score: the format and the text tests see the same page, so a test cannot fail on text the
    other tests never saw, or pass on text they ignore."""
    # Given a page built from the pieces; When both readers read it; Then they find the same text
    html = "".join(piece.format(w=w) for piece, w in pieces)
    assert marks.read(html).text == marks.fold(views.html(html).text), html


@relation(HOLDS, domain="3 pages: marks only inside a closed head and title, a closed script, and punctuation")
@given(PHRASE, KIND)
def test_marks_on_hidden_text_or_on_no_letter_do_not_make_a_page_have_marks(phrase, kind):
    """A page whose only marks are inside a closed `<head>`, `<title>` or `<script>`, or are on punctuation alone,
    has no marks: a negative test fails on it. [M75]
    Why it matters for a score: a negative test needs a mark somewhere on the text the page shows."""
    # Given the plain answer with a mark only where it does not count
    plain = page(*phrase)
    hidden = f"<head><title>The <b>Report</b></title></head>{plain}<script><b>x</b></script>"
    # When a negative test runs; Then it fails on each
    assert not passes(fmt(*phrase, absent=kind), hidden)
    assert not passes(fmt(*phrase, absent=kind), plain + "<b>.</b><i> — </i>")
