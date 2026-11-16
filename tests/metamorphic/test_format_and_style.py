"""Relations of the form of a page: markdown against HTML (M6), inline styling and footnote marks (M7), an
added paragraph (M22) and the text view (M24)."""
from __future__ import annotations

import re

from hypothesis import assume, example, given
from hypothesis import strategies as st
from test_properties import MARK, WORD

from metamorphic.common import (HOLDS, LIMITATION, NUMBER, TEXT, deviation, escaped, more_evidence, passes,
                                relation)
from omni_parse_bench import markdown, views
from omni_parse_bench.normalize import fold
from omni_parse_bench.scorers.unit_tests import runners

CELL_TEXT = st.one_of(WORD, MARK).map(str.strip).filter(bool)
GRID = st.integers(2, 3).flatmap(
    lambda w: st.lists(st.lists(CELL_TEXT, min_size=w, max_size=w), min_size=2, max_size=4))


def as_markdown_and_html(paragraphs) -> tuple[str, str]:
    """The paragraphs as markdown (blank lines between, through markdown.to_html) and as HTML (a <p> each)."""
    return markdown.to_html("\n\n".join(paragraphs)), "".join(f"<p>{escaped(x)}</p>" for x in paragraphs)


@relation(HOLDS)
@example(rows=[["a", "b", "c"], ["$5", "x_1", "US$6"]])
@given(GRID)
def test_a_table_as_markdown_or_html_gets_the_same_cell_verdicts(rows):
    """Each body cell's table_cell test (cell, neighbours, column heading) passes on a table of words and
    marks written in HTML, and gets the same verdict when the table is a markdown pipe table. [M6a]
    Why it matters for a score: a system that answers in markdown is graded like one that answers in HTML."""
    # Given a grid of cells, as a markdown table and as the HTML table it stands for (header row of <th>)
    line = lambda r: "| " + " | ".join(r) + " |"  # noqa: E731
    md = markdown.to_html("\n".join([line(rows[0]), "|" + "---|" * len(rows[0]), *map(line, rows[1:])]))
    head = "<thead><tr>" + "".join(f"<th>{escaped(x)}</th>" for x in rows[0]) + "</tr></thead>"
    body = "".join("<tr>" + "".join(f"<td>{escaped(x)}</td>" for x in r) + "</tr>" for r in rows[1:])
    html = f"<table>{head}<tbody>{body}</tbody></table>"
    # When each body cell is tested with its neighbours and its column heading; Then both tables agree
    for i, row in enumerate(rows[1:], 1):
        for j, x in enumerate(row):
            near = {"top_heading": rows[0][j], "up": rows[i - 1][j], "left": row[j - 1] if j else None,
                    "right": row[j + 1] if j + 1 < len(row) else None,
                    "down": rows[i + 1][j] if i + 1 < len(rows) else None}
            p = runners.TableCell(x, {k: v for k, v in near.items() if v is not None}, 0)
            assert passes(p, html), (html, p)    # the answer itself passes, so agreement is not two failures
            assert passes(p, md) == passes(p, html), (md, html, p)


@relation(HOLDS)
@given(st.lists(st.lists(st.one_of(WORD, MARK), min_size=1, max_size=6).map(" ".join)
                .map(str.strip).filter(lambda x: x and not set(x) <= set("_- ")), min_size=1, max_size=3))
def test_paragraphs_as_markdown_or_html_get_the_same_text_verdicts(paragraphs):
    """Paragraphs of words and marks (`$5.00`, `x_1`, `[1]`, `...`, `—`, ...) get the same text verdicts
    written as markdown or as HTML. Left out: paragraphs with a bullet glyph (M6c), and paragraphs of only
    `_`, `-` and spaces, which can join a neighbour's leader run across the paragraph break (M22). A paragraph
    of only words also passes on both; one with marks has no such anchor. [M6b]
    Why it matters for a score: as for M6a, for running text."""
    # Given paragraphs of words and marks as markdown and as HTML: none with a bullet glyph (that is M6c), and
    # none of only `_`, `-` and spaces (that is M22; the strategy filters them out)
    # When each paragraph's text test runs on both; Then the verdicts agree
    assume(not any("•" in x for x in paragraphs))    # a bullet glyph opening a paragraph: M6c
    md, html = as_markdown_and_html(paragraphs)
    for x in paragraphs:
        p = runners.Present(runners.Text(x, 0))
        if re.fullmatch(r"[A-Za-z0-9 ]+", x):    # only words: the answer itself passes on both
            assert passes(p, html) and passes(p, md), (md, html, x)
        assert passes(p, md) == passes(p, html), (md, html, x)


@relation(LIMITATION, domain="lists of 2-3 paragraphs from 5 choices (150 lists)")
@deviation("M6c")
@example(paragraphs=["lorem _", "• ____"])
@given(st.lists(st.sampled_from(["lorem _", "• ____", "ipsum", "• dolor", "• ___"]), min_size=2, max_size=3))
def test_a_paragraph_opening_with_a_bullet_gets_the_same_verdict_as_markdown_or_html(paragraphs):
    """Paragraphs drawn from 'lorem _', 'ipsum' and bullet paragraphs ('• ____', '• dolor', '• ___') get the
    same text verdicts as markdown or as HTML; the paragraphs with no blank ('ipsum', '• dolor') pass on both.
    [M6c]
    Why it matters for a score: as for M6b, for lists a system writes with bullet glyphs."""
    # Given paragraphs, some opening with a bullet glyph, as markdown and as HTML
    # When each paragraph's text test runs on both; Then the verdicts agree
    md, html = as_markdown_and_html(paragraphs)
    for x in paragraphs:
        p = runners.Present(runners.Text(x, 0))
        if x in ("ipsum", "\u2022 dolor"):    # the answer itself passes, so agreement is not two failures
            assert passes(p, md) and passes(p, html), (md, html, x)
    for x in paragraphs:
        p = runners.Present(runners.Text(x, 0))
        assert passes(p, md) == passes(p, html), (md, html, x)


@relation(HOLDS)
@example(words=["Revenue", "12"], marker="-", at=1)
@given(st.lists(st.sampled_from(["Revenue", "lorem", "ipsum", "12", "x9"]), min_size=1, max_size=3),
       st.sampled_from("-*+"), st.integers(0, 3))
def test_a_paragraph_that_is_only_a_list_marker_keeps_it_in_markdown(words, marker, at):
    """A paragraph that is only `-`, `*` or `+`, among paragraphs of words, passes its text test written as
    markdown and as HTML; so does each paragraph of words. [M6d]
    Why it matters for a score: a lone '-' is often an empty value in a table or form; markdown must not
    turn it into an empty list item and lose it."""
    # Given paragraphs of words with one paragraph that is only a list marker, as markdown and as HTML
    paragraphs = [*words[:at], marker, *words[at:]]
    md, html = as_markdown_and_html(paragraphs)
    # When each paragraph's text test runs on both; Then it passes on both
    for x in paragraphs:
        p = runners.Present(runners.Text(x, 0))
        assert passes(p, md) and passes(p, html), (md, html, x)

@more_evidence()
def test_markdown_and_html_disagree_only_where_a_trailing_underscore_meets_a_bullet_blank():
    """The cause M6c names, pinned: 'lorem _' before '• ____' fails as markdown and passes as HTML; it passes
    on both before '• dolor' (a bullet, no blank) or '• x ____' (a word stops the run), and 'lorem' (no '_')
    passes on both before '• ____'. [M6c]
    Why it matters for a score: M6c's test accepts any failure; this check breaks if the cause changes."""
    # Given 'lorem _' (or 'lorem') before a bullet paragraph, as markdown and as HTML
    def verdicts(first, second):
        md, html = as_markdown_and_html([first, second])
        p = runners.Present(runners.Text(first, 0))
        return passes(p, md), passes(p, html)
    # When the bullet paragraph is a blank of '_'; Then markdown fails and HTML passes
    assert verdicts("lorem _", "\u2022 ____") == (False, True)
    # When there is no blank, a word stops the run, or the text has no '_'; Then both pass
    for first, second in (("lorem _", "\u2022 dolor"), ("lorem _", "\u2022 x ____"),
                          ("lorem", "\u2022 ____")):
        assert verdicts(first, second) == (True, True), (first, second)

# ------------------------------------------------------------------------------------- inline style

ANSWERS = [t.params for t in [*TEXT, *NUMBER]]


def answer_text(p) -> str:
    return p.content.text if isinstance(p.content, runners.Text) else p.content.number


@relation(HOLDS, pool="text, number")
@given(st.sampled_from(ANSWERS), st.sampled_from(["b", "i", "span", "em", "strong", "u", "small", "a"]),
       st.sampled_from(["all", "head", "tail"]), st.integers(0, 500))
def test_inline_styling_does_not_change_a_present_verdict(p, tag, where, cut):
    """A text or number test passes with all, a head or a tail of its answer in `<b>`, `<i>`, `<span>`,
    `<em>`, `<strong>`, `<u>`, `<small>` or `<a>`. [M7a]
    Why it matters for a score: bold or italic is styling, not content; it must not cost a test."""
    # Given a text or number test, and its answer cut in two at `cut`
    s = answer_text(p)
    cut = cut % (len(s) + 1)
    a, b = escaped(s[:cut]), escaped(s[cut:])
    styled = {"all": f"<{tag}>{escaped(s)}</{tag}>", "head": f"<{tag}>{a}</{tag}>{b}",
              "tail": f"{a}<{tag}>{b}</{tag}>"}
    # When all of it, the head or the tail is wrapped in an inline tag; Then the test passes
    assert passes(p, f"<p>{styled[where]}</p>")


@relation(HOLDS, pool="text, number")
@given(st.sampled_from(ANSWERS))
def test_a_footnote_mark_after_the_answer_does_not_change_a_present_verdict(p):
    """A text or number test passes on its answer followed by a footnote mark `<sup>1</sup>`. [M7b]
    Why it matters for a score: `1,240<sup>1</sup>` is the number 1,240 with a footnote, not 1,2401."""
    # Given a text or number test; When the page holds its answer, then `<sup>1</sup>`; Then it passes
    assert passes(p, f"<p>{escaped(answer_text(p))}<sup>1</sup></p>")


@relation(LIMITATION, pool="text, number")
@deviation("M7c")
@example(p=runners.Present(runners.Number("1,240.00")))
@given(st.sampled_from(ANSWERS))
def test_a_footnote_mark_before_the_answer_does_not_change_a_present_verdict(p):
    """A text or number test passes on its answer preceded by a mark `<sup>1</sup>`. The deviation is shown
    for answers that start with a digit (the mark joins them); other answers are not shown to fail. [M7c]
    Why it matters for a score: as for M7b, for a mark set before the text."""
    # Given a text or number test; When the page holds `<sup>1</sup>`, then its answer; Then it passes
    assert passes(p, f"<p><sup>1</sup>{escaped(answer_text(p))}</p>")


PHRASE = st.lists(st.sampled_from(["Smith", "and", "Jones", "Probiotic", "strains", "lorem", "ipsum"]),
                  min_size=2, max_size=4)


@relation(HOLDS)
@example(words=["Smith", "and", "Jones"], at=0, n=1, spaced=False, a=12, b=4)
@given(PHRASE, st.integers(0, 2), st.integers(1, 99), st.booleans(), st.integers(1, 999), st.integers(0, 999))
def test_a_bracketed_footnote_marker_inside_a_phrase_is_ignored(words, at, n, spaced, a, b):
    """A text test for a phrase passes on the phrase with a marker `[n]` after one of its inner words, glued
    or spaced. A marker between two numbers is not removed: a text test for the two numbers joined fails on
    `12[3]4`. [M7d]
    Why it matters for a score: 'Smith[1] and Jones' is the phrase 'Smith and Jones' with a footnote, and
    '12[3]4' must not read as '124'."""
    # Given a phrase, and the page with a marker [n] after an inner word
    at = at % (len(words) - 1)
    marked = [f"{w}{' ' * spaced}[{n}]" if i == at else w for i, w in enumerate(words)]
    # When the text test runs; Then it passes
    assert passes(runners.Present(runners.Text(" ".join(words), 0)), f"<p>{' '.join(marked)}</p>")
    # And a marker between two numbers keeps them apart (where the marker's digits do not spell them)
    assume(f"{a}{b}" not in f"{a}{n}{b}")
    assert not passes(runners.Present(runners.Text(f"{a}{b}", 0)), f"<p>{a}[{n}]{b}</p>")


@relation(LIMITATION)
@deviation("M7e")
@example(words=["Probiotic", "strains"], at=0, n=1)
@given(PHRASE, st.integers(0, 2), st.integers(1, 99))
def test_a_superscript_footnote_mark_inside_a_phrase_is_ignored(words, at, n):
    """A text test for a phrase passes on the phrase with a mark `<sup>n</sup>` after one of its inner words.
    [M7e]
    Why it matters for a score: as for M7d, for a mark set as a superscript."""
    # Given a phrase, and the page with <sup>n</sup> after an inner word
    at = at % (len(words) - 1)
    marked = [f"{w}<sup>{n}</sup>" if i == at else w for i, w in enumerate(words)]
    # When the text test runs; Then it passes
    assert passes(runners.Present(runners.Text(" ".join(words), 0)), f"<p>{' '.join(marked)}</p>")

# ------------------------------------------------------------------------------------- the text view

LETTERS = st.text("abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=4)
ANSWER = st.lists(st.sampled_from(["Total", "due", "lorem", "ipsum", "12", "x9"]), min_size=1, max_size=3) \
    .map(" ".join)


@relation(HOLDS)
@example(name="q", middle=["Total due"])
@given(LETTERS, st.lists(ANSWER, min_size=1, max_size=3))
def test_a_stray_less_than_sign_stays_text_and_keeps_the_blocks_after_it(name, middle):
    """A `<` before a letter that starts no tag (`p <q`) stays as text, and a later `>` (`r> s`) does not
    erase the paragraphs between them: each one's text test passes, and so does the text test of `p <q`.
    [M24a]
    Why it matters for a score: an inequality in prose or math must not wipe out the rest of the page."""
    # Given paragraphs between one that ends in '<' + letters and one that holds a '>'
    page = f"<p>p <{name}</p>" + "".join(f"<p>{x}</p>" for x in middle) + "<p>r> s</p>"
    # When each paragraph's text test runs; Then each passes
    for x in [f"p <{name}", *middle, "r> s"]:
        assert passes(runners.Present(runners.Text(x, 0)), page), (page, x)


@relation(HOLDS)
@example(n=125, cut=2, comment=" x ")
@given(st.integers(10, 99999), st.integers(1, 4), st.text("abc -", max_size=5))
def test_a_comment_inside_a_number_leaves_no_space(n, cut, comment):
    """A number test passes on its number with an HTML comment between two of its digits
    (`12<!-- x -->5`). [M24b]
    Why it matters for a score: a browser draws nothing for a comment, so the page shows '125'."""
    # Given a number, and the page with a comment between two of its digits
    s = str(n)
    cut = 1 + cut % (len(s) - 1)
    # When its number test runs; Then it passes
    assert passes(runners.Present(runners.Number(s)), f"<p>{s[:cut]}<!--{comment}-->{s[cut:]}</p>")


@relation(HOLDS)
@example(answer="Total due", tag="o:p", at=1)
@given(ANSWER, st.sampled_from(["o:p", "w:sdt", "st1:place", "v:shape"]), st.integers(0, 5))
def test_a_namespaced_tag_is_dropped_like_any_tag(answer, tag, at):
    """A text test passes on its answer with an empty namespaced tag (`<o:p></o:p>`, `<w:sdt>`, `<st1:place>`,
    `<v:shape>`, as Word writes them) right after one of its words. [M24c]
    Why it matters for a score: such tags are markup, not text the page shows."""
    # Given an answer, and the page with an empty namespaced tag after one of its words
    words = answer.split(" ")
    at = at % len(words)
    tagged = " ".join(f"{w}<{tag}></{tag}>" if i == at else w for i, w in enumerate(words))
    # When its text test runs; Then it passes
    assert passes(runners.Present(runners.Text(answer, 0)), f"<p>{tagged}</p>")


@relation(HOLDS)
@example(answer="Total", tag="span", value="a>b", quote='"')
@given(ANSWER, st.sampled_from(["span", "a", "p", "div", "td"]), st.text("ab> =", max_size=6),
       st.sampled_from(["'", '"']))
def test_a_greater_than_sign_inside_a_quoted_attribute_does_not_end_the_tag(answer, tag, value, quote):
    """A page whose answer sits in a tag with a quoted attribute holding `>` (`<span title="a>b">`) reads the
    same as the answer alone. [M24d]
    Why it matters for a score: an attribute's value is not text on the page."""
    # Given an answer inside a tag whose quoted attribute value holds '>'
    body = f"<{tag} title={quote}{value}{quote}>{escaped(answer)}</{tag}>"
    page = f"<table><tr>{body}</tr></table>" if tag == "td" else f"<p>{body}</p>"
    # When the page is read; Then it reads as the answer alone, and the answer's text test passes
    assert fold(views.text(page)) == fold(answer), views.text(page)
    assert passes(runners.Present(runners.Text(answer, 0)), page)


# ---------------------------------------------------------------------------------- an added paragraph

PARAGRAPH = st.lists(st.one_of(WORD, MARK), min_size=1, max_size=6).map(" ".join).map(str.strip).filter(bool)


@relation(LIMITATION)
@deviation("M22")
@example(text="a _", extra="__")
@given(PARAGRAPH, PARAGRAPH)
def test_adding_a_paragraph_does_not_fail_a_passing_text_test(text, extra):
    """A text test that passes on a page of its own paragraph still passes when another paragraph is added
    before or after it. [M22]
    Why it matters for a score: a test grades its own text, not what the page prints next to it."""
    # Given a text test that passes on its own paragraph
    p = runners.Present(runners.Text(text, 0))
    assume(passes(p, f"<p>{escaped(text)}</p>"))
    # When another paragraph is added after it, or before it; Then the test still passes
    a, b = escaped(text), escaped(extra)
    for page in (f"<p>{a}</p><p>{b}</p>", f"<p>{b}</p><p>{a}</p>"):
        assert passes(p, page), page


@more_evidence()
def test_an_added_paragraph_fails_a_text_test_only_by_the_joins_m22_names():
    """The two causes M22 names, pinned. 'a _' fails beside '__' (three '_' across the break) and passes
    beside '_' (two in all) or 'x __' (a letter stops the run). 'well-' fails before 'known' (the hyphen joins
    a lowercase word) and passes before 'Known' and after 'known'. [M22]
    Why it matters for a score: M22's test accepts any failure; this check breaks if a cause changes."""
    def text(x):
        return runners.Present(runners.Text(x, 0))
    # Given a text test that ends in one '_'; When the next paragraph makes a run of 3; Then it fails
    assert not passes(text("a _"), "<p>a _</p><p>__</p>")
    # When the paragraph makes no run of 3; Then it passes
    assert passes(text("a _"), "<p>a _</p><p>_</p>") and passes(text("a _"), "<p>a _</p><p>x __</p>")
    # Given a text test that ends in a hyphen; When the next paragraph starts lowercase; Then it fails
    assert not passes(text("well-"), "<p>well-</p><p>known</p>")
    # When it starts with a capital, or comes before; Then it passes
    assert passes(text("well-"), "<p>well-</p><p>Known</p>")
    assert passes(text("well-"), "<p>known</p><p>well-</p>")
