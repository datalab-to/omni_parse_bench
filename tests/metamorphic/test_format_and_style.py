"""Relations of the form of a page: markdown against HTML (M6), inline styling and footnote marks (M7), an
added paragraph (M22a, M22b) and the text view (M24)."""
from __future__ import annotations

import re
from itertools import zip_longest

from hypothesis import assume, example, given
from hypothesis import strategies as st
from test_properties import MARK, WORD

from metamorphic.common import (HOLDS, INTENDED, NUMBER, TEXT, deviation, escaped, more_evidence, passes,
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
                .map(str.strip).filter(bool), min_size=1, max_size=3))
def test_paragraphs_as_markdown_or_html_get_the_same_text_verdicts(paragraphs):
    """Paragraphs of words and marks (`$5.00`, `x_1`, `[1]`, `...`, `—`, ...) get the same text verdicts
    written as markdown or as HTML. A paragraph of only words also passes on both; one with marks has no such
    anchor. [M6b]
    Why it matters for a score: as for M6a, for running text."""
    # Given paragraphs of words and marks as markdown and as HTML
    # When each paragraph's text test runs on both; Then the verdicts agree
    md, html = as_markdown_and_html(paragraphs)
    for x in paragraphs:
        p = runners.Present(runners.Text(x, 0))
        if re.fullmatch(r"[A-Za-z0-9 ]+", x):    # only words: the answer itself passes on both
            assert passes(p, html) and passes(p, md), (md, html, x)
        assert passes(p, md) == passes(p, html), (md, html, x)


@relation(HOLDS, domain="lists of 2-3 paragraphs from 5 choices (150 lists)")
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
def test_a_trailing_underscore_beside_a_bullet_blank_passes_as_markdown_and_as_html():
    """'lorem _' before '• ____' passes as markdown and as HTML: markdown removes the bullet that opens a line
    and HTML keeps it, but either way the block break stops the '_' joining '____'. It passes on both before
    '• dolor' or '• x ____', and 'lorem' passes on both before '• ____'. [M6c]
    Why it matters for a score: the case M6c once failed in markdown only stays fixed."""
    # Given 'lorem _' (or 'lorem') before a bullet paragraph, as markdown and as HTML
    def verdicts(first, second):
        md, html = as_markdown_and_html([first, second])
        p = runners.Present(runners.Text(first, 0))
        return passes(p, md), passes(p, html)
    # When the bullet paragraph is a blank of '_', has no blank, or a word stops the run; Then both pass
    for first, second in (("lorem _", "\u2022 ____"), ("lorem _", "\u2022 dolor"),
                          ("lorem _", "\u2022 x ____"), ("lorem", "\u2022 ____")):
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


@relation(HOLDS, pool="text, number")
@example(p=runners.Present(runners.Number("1,240.00")))
@given(st.sampled_from(ANSWERS))
def test_a_footnote_mark_before_the_answer_does_not_change_a_present_verdict(p):
    """A text or number test passes on its answer preceded by a mark `<sup>1</sup>`. [M7c]
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


@relation(HOLDS)
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


@relation(HOLDS)
@example(text="a _", extra="__")
@given(PARAGRAPH, PARAGRAPH)
def test_adding_a_paragraph_does_not_fail_a_passing_text_test(text, extra):
    """A text test of words and marks that passes on a page of its own paragraph still passes when another
    paragraph is added before or after it: a leader run does not span the paragraph break. [M22a]
    Why it matters for a score: a test grades its own text, not what the page prints next to it."""
    # Given a text test that passes on its own paragraph
    p = runners.Present(runners.Text(text, 0))
    assume(passes(p, f"<p>{escaped(text)}</p>"))
    # When another paragraph is added after it, or before it; Then the test still passes
    a, b = escaped(text), escaped(extra)
    for page in (f"<p>{a}</p><p>{b}</p>", f"<p>{b}</p><p>{a}</p>"):
        assert passes(p, page), page


@more_evidence()
def test_an_added_paragraph_does_not_join_a_leader_run():
    """A block break stops a leader run: 'a _' passes beside '__' (no run of three across the break). Inside
    a paragraph, a run of three '_' still folds away and two do not. [M22a]
    Why it matters for a score: a test grades its own text, and the leader rule still holds inside a
    paragraph."""
    def text(x):
        return runners.Present(runners.Text(x, 0))
    # Given a text test that ends in one '_'; When the next paragraph holds '__'; Then it passes
    assert passes(text("a _"), "<p>a _</p><p>__</p>") and passes(text("a _"), "<p>__</p><p>a _</p>")
    # When the run is inside one paragraph; Then three '_' are a leader and two are not
    assert passes(text("a b"), "<p>a ___ b</p>") and not passes(text("a b"), "<p>a __ b</p>")


@relation(INTENDED, domain="3 words ending in a hyphen, 3 lowercase words (9 pairs)")
@deviation("M22b")
@example(text="well-", extra="known")
@given(st.sampled_from(["well-", "Head-", "re-"]), st.sampled_from(["known", "quarters", "done"]))
def test_adding_a_paragraph_does_not_join_a_text_tests_line_end_hyphen(text, extra):
    """A text test that ends in a hyphen and passes on its own paragraph still passes when a paragraph that
    starts with a lowercase letter is added after it. [M22b]
    Why it matters for a score: a block break is a line break for a hyphen, so outputs that write one
    paragraph per printed line keep their broken words; the price is a text that ends in a hyphen there."""
    # Given a text test that ends in a hyphen and passes on its own paragraph
    p = runners.Present(runners.Text(text, 0))
    assert passes(p, f"<p>{text}</p>")
    # When a paragraph that starts lowercase is added after it; Then the test still passes
    assert passes(p, f"<p>{text}</p><p>{extra}</p>")


NOTHING = ["", " ", "\n", " ", "​", "﻿", "­", "<br>", "<!-- c -->", "<p> </p>", "<math></math>",
           "<img alt='stamp'>", "<input type=hidden value=v>", "<ol><li></li></ol>"]


@relation(HOLDS, domain="a page of 0-6 letters with 0-4 things that show nothing added, limits 0-6")
@given(st.text("abc ", max_size=6), st.lists(st.sampled_from(NOTHING), max_size=4), st.integers(0, 6))
def test_adding_what_shows_nothing_does_not_change_a_near_empty_verdict(letters, extras, limit):
    """A page_near_empty verdict does not change when the page gains blanks, line breaks, comments, invisible
    format characters, an image with a description, an empty element or a hidden input, in any place. [M28]
    Why it matters for a score: a page is faulted for what a reader would see on it, and a blank page with an
    empty element on it is still blank."""
    # Given a page of letters, and the verdict at one limit
    test = runners.PageNearEmpty(limit)
    base = f"<p>{letters}</p>"
    # When things that show nothing are added before, inside and after it; Then the verdict is the same
    inside = "".join(x for pair in zip_longest(letters, extras, fillvalue="") for x in pair)
    for page in ("".join(extras) + base, base + "".join(extras), f"<p>{inside}</p>"):
        assert passes(test, page) == passes(test, base)
