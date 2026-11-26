# ruff: noqa: E501
"""Relations of `no_excess_repeats` tests (M160 to M167): a page written as printed passes however its blocks
are laid out or ordered, and with text left out; a run of 16 or more of its words written once more fails, a
shorter one does not; what the test does not read (math, figures, image descriptions) keeps the verdict; a
table counts as text however it is written; and a passage the page prints m times may be written m times, not
m + 1."""
from __future__ import annotations

import math
import re

from hypothesis import given
from hypothesis import strategies as st

from metamorphic.common import HOLDS, TESTS, escaped, passes, relation, text_strings
from omni_parse_bench.scorers.unit_tests import runners

RUN = 16    # the documented run (docs/scoring/no_excess_repeats.md), not read from the scorer
# Distinct words, so that a word's count is the number of times its passage is written.
VOCAB = [f"w{i}" for i in range(200)]


def page_words(n: int) -> list[str]:
    return VOCAB[:n]


def blocks_of(words: list[str], cuts: list[int]) -> list[str]:
    edges = [0, *sorted(set(c for c in cuts if 0 < c < len(words))), len(words)]
    return [" ".join(words[a:b]) for a, b in zip(edges, edges[1:], strict=False)]


LAYOUTS = {
    "paragraphs": lambda bs: "".join(f"<p>{b}</p>" for b in bs),
    "one paragraph": lambda bs: "<p>" + " ".join(bs) + "</p>",
    "heading and list": lambda bs: f"<h2>{bs[0]}</h2><ul>" + "".join(f"<li>{b}</li>" for b in bs[1:]) + "</ul>",
    "divs and breaks": lambda bs: "<div>" + "<br>".join(bs) + "</div>",
    "upper case": lambda bs: "".join(f"<p>{b.upper()}</p>" for b in bs),
    "table": lambda bs: "<table>" + "".join(f"<tr><td>{b}</td></tr>" for b in bs) + "</table>",
    "markdown table": lambda bs: "<p>" + "\n".join(f"| {b} |" for b in bs) + "</p>",
}
LAYOUT = st.sampled_from(list(LAYOUTS))
PAGE = st.integers(RUN, 80)


@st.composite
def a_page(draw):
    words = page_words(draw(PAGE))
    bs = blocks_of(words, draw(st.lists(st.integers(1, len(words) - 1), max_size=4)))
    return words, bs


def gold_of(words: list[str], times: int = 1) -> runners.NoExcessRepeats:
    return runners.NoExcessRepeats(" ".join(words * times))


# ------------------------------------------------------------------------------------------ what passes


@relation(HOLDS, domain="pages of 16 to 80 distinct words x 1 to 5 blocks x every order of the blocks x 7 layouts; "
                        "and each with any of its blocks left out")
@given(a_page(), st.randoms(use_true_random=False), LAYOUT, st.data())
def test_a_page_written_as_printed_passes_in_any_order_and_layout_and_with_text_left_out(page, rnd, layout, data):
    """The page's text, cut into blocks, written in any order of the blocks, as paragraphs, as one paragraph, as
    a heading and a list, as lines of one block, in upper case, as rows of a table or of a markdown table,
    passes; so does the same with any blocks left out. [M160]
    Why it matters for a score: the test counts words, not their order or markup, so a faithful output in
    another reading order, and one that drops text, never fail it (other tests see dropped text)."""
    words, bs = page
    rnd.shuffle(bs)
    assert passes(gold_of(words), LAYOUTS[layout](bs)), (layout, bs)
    kept = data.draw(st.lists(st.sampled_from(bs), min_size=1, unique=True))
    assert passes(gold_of(words), LAYOUTS[layout](kept)), (layout, kept)


@relation(HOLDS, domain="pages of 16 to 80 distinct words x every run of 1 to 40 consecutive words x 3 places "
                        "(before, after, in the middle of the page) x 7 layouts")
@given(a_page(), st.integers(1, 40), st.integers(0, 79), st.sampled_from(["before", "after", "middle"]), LAYOUT)
def test_a_run_of_its_words_written_once_more_fails_exactly_when_it_holds_16(page, k, at, where, layout):
    """A run of k consecutive words of the page written once more, as a block of its own before, after or in
    the middle of the page (between two blocks, not inside the run's own copy), fails the test when k is 16 or more and passes when k is less than 16. [M161]
    Why it matters for a score: the run length is the rule's one threshold; a duplicate passage of 16 words or
    more is caught wherever it is written, and a shorter phrase written twice is not."""
    words, bs = page
    k = min(k, len(words))
    at = min(at, len(words) - k)
    extra = " ".join(words[at:at + k])
    # Note: in the middle means at a block edge outside the run's own copy, which an insert inside would cut
    edges = [sum(len(b.split()) for b in bs[:j]) for j in range(len(bs) + 1)]
    inner = [j for j, e in enumerate(edges) if 0 < j < len(bs) and not at < e < at + k]
    i = {"before": 0, "after": len(bs), "middle": inner[len(inner) // 2] if inner else len(bs)}[where]
    out = LAYOUTS[layout]([*bs[:i], extra, *bs[i:]])
    assert passes(gold_of(words), out) is (k < RUN), (k, where, layout, out)


@relation(HOLDS, domain="pages of 16 to 80 distinct words x 2 states (as printed, a block of 16+ words written "
                        "twice) x 6 places the test does not read, each holding the whole page three times")
@given(a_page(), st.booleans(), st.sampled_from(["$$ math $$", "\\( math \\)", "\\[ math \\]", "<math>",
                                                 "image description", "figure"]))
def test_text_in_math_a_figure_or_an_image_description_keeps_the_verdict(page, doubled, where):
    """A math span (`$$..$$`, `\\(..\\)`, `\\[..\\]`, `<math>`), a figure's text or an image description holding the
    whole page three times, added to an output, keeps its verdict: the page as printed passes, the page with a
    passage of 16 or more words written twice fails. [M162]
    Why it matters for a score: math and image descriptions are left to `present` and no test; they neither
    raise nor hide a repeat in the text."""
    words, bs = page
    out = "".join(f"<p>{b}</p>" for b in bs) + (f"<p>{' '.join(words[:RUN])}</p>" if doubled else "")
    loop = " ".join(words * 3)
    added = {"$$ math $$": f"<p>$${loop}$$</p>", "\\( math \\)": f"<p>\\({loop}\\)</p>",
             "\\[ math \\]": f"<p>\\[{loop}\\]</p>", "<math>": f"<math>{loop}</math>",
             "image description": f"<img alt='{loop}'>",
             "figure": f"<figure><p>{loop}</p><figcaption>Figure 1.</figcaption></figure>"}[where]
    assert passes(gold_of(words), out) is not doubled
    assert passes(gold_of(words), out + added) is not doubled, (where, doubled)


TABLE_FORMS = {
    "table": lambda rows: "<table>" + "".join(f"<tr><td>{r}</td></tr>" for r in rows) + "</table>",
    "cells": lambda rows: "<table><tr>" + "".join(f"<td>{r}</td>" for r in rows) + "</tr></table>",
    "nested table": lambda rows: "<table><tr><td><table>" + "".join(f"<tr><td>{r}</td></tr>" for r in rows)
                                 + "</table></td></tr></table>",
    "markdown table": lambda rows: "<p>" + "\n".join(f"| {r} |" for r in rows) + "</p>",
    "markdown rows": lambda rows: "".join(f"<p>| {r} |</p>" for r in rows),
    "paragraphs": lambda rows: "".join(f"<p>{r}</p>" for r in rows),
}


@relation(HOLDS, domain="pages of 16 to 80 distinct words x a table of 1 to 3 rows of 16 to 24 distinct words, "
                        "printed 1 or 2 times x 6 ways to write it (a table, cells of one row, a nested table, a "
                        "markdown table, markdown rows, paragraphs) x 3 states (as printed, a row written once "
                        "more, the table written once more)")
@given(a_page(), st.lists(st.integers(16, 24), min_size=1, max_size=3), st.integers(1, 2),
       st.sampled_from(list(TABLE_FORMS)), st.sampled_from(["as printed", "a row more", "the table more"]))
def test_a_table_counts_as_text_however_it_is_written(page, sizes, times, form, state):
    """A page with a table, its cells in the gold: the output that writes the table as printed passes, in a
    `<table>`, as cells of one row, nested, as a markdown table or rows, or flattened to paragraphs; one that
    writes a row or the whole table once more fails, in each form. [M167]
    Why it matters for a score: a faithful table never fails however a system writes it, and a loop or a
    duplicated row inside a table is caught as in the text."""
    words, bs = page
    tail = [f"t{i}" for i in range(sum(sizes))]
    rows, at = [], 0
    for n in sizes:
        rows.append(" ".join(tail[at:at + n]))
        at += n
    rows = rows * times
    gold = runners.NoExcessRepeats(" ".join(words + rows))
    extra = {"as printed": [], "a row more": rows[:1], "the table more": rows}[state]
    out = "".join(f"<p>{b}</p>" for b in bs) + TABLE_FORMS[form](rows + extra)
    assert passes(gold, out) is (state == "as printed"), (form, state, times, sizes)


LETTERS = [f"{a}{b}{c}" for a in "bdfg" for b in "aeiou" for c in "klmnprst"]    # 160 distinct words
HTML_LOOKALIKES = ["<!-- <table> -->", "<p title='<table>'>a note</p>", "<p>a &lt;table&gt; tag</p>",
                   "<p>Cost $5 and $6</p>", "<p>$5</p>"]


@relation(HOLDS, domain="pages of 32 to 80 distinct letter words, pairs of them joined by a hyphen (at random, "
                        "or every pair) x 3 spellings of every compound in the output (kept, broken at a line end, "
                        "joined) x 3 states (as printed; a page printing its text twice, written twice; written "
                        "twice) x 6 befores (nothing, or a text lookalike of a table or math: a table tag in a "
                        "comment, in an attribute, as escaped text; prices)")
@given(st.integers(2 * RUN, 80), st.one_of(st.just("every pair"), st.just("random")), st.data())
def test_compounds_and_text_lookalikes_keep_the_verdict(n, how, data):
    """A page whose words are joined in pairs by hyphens (`self-aware`), written with every compound kept,
    broken at a line end (`self-<br>aware`) or joined (`selfaware`), passes as printed, passes written twice
    where the page prints its text twice, and fails written twice where it prints it once; so does the same
    output after a table tag written as text (in a comment, an attribute, or escaped) or a price, which hide
    nothing. [M166]
    Why it matters for a score: a faithful output's line breaks and the page's text that looks like markup
    never move the verdict either way."""
    words = LETTERS[:n]
    joins = ([i % 2 == 0 for i in range(n - 1)] if how == "every pair"
             else data.draw(st.lists(st.booleans(), min_size=n - 1, max_size=n - 1)))
    joins = [j and not (i and joins[i - 1]) for i, j in enumerate(joins)]    # pairs, never a chain
    bad = []
    for spelling, sep in (("kept", "-"), ("broken", "-<br>"), ("joined", "")):
        gold_text, out_text = words[0], words[0]
        for w, j in zip(words[1:], joins, strict=True):
            gold_text += ("-" if j else " ") + w
            out_text += (sep if j else " ") + w
        for before in ["", *HTML_LOOKALIKES]:
            for state, times, gold_times, ok in (("as printed", 1, 1, True), ("printed twice", 2, 2, True),
                                                 ("written twice", 2, 1, False)):
                out = before + f"<p>{out_text}</p>" * times
                if passes(runners.NoExcessRepeats(" ".join([gold_text] * gold_times)), out) is not ok:
                    bad.append((spelling, before, state))
    assert not bad, f"{len(bad)} cases break, e.g. {bad[:5]}"


# ------------------------------------------------------------------------------------------ what fails


@relation(HOLDS, domain="pages of 16 to 80 distinct words x a page printed 1 to 4 times x 7 layouts")
@given(a_page(), st.integers(1, 4), LAYOUT)
def test_a_page_printed_m_times_may_be_written_m_times_not_m_plus_one(page, m, layout):
    """A page whose text holds its passage m times (a form printed twice, a repeated notice) passes an output
    that writes it m times, and fails one that writes it m + 1 times. [M163]
    Why it matters for a score: the bound is the page's own count, so a passage the page repeats is no error,
    and one written more often than the page prints it is."""
    words, bs = page
    assert passes(gold_of(words, m), LAYOUTS[layout](bs * m))
    assert not passes(gold_of(words, m), LAYOUTS[layout](bs * (m + 1))), (m, layout)


@relation(HOLDS, domain="pages of 16 to 80 distinct words x a loop of a 1- to 8-word phrase of the page, "
                        "written 17 to 40 times, after the page or in its middle")
@given(a_page(), st.integers(1, 8), st.integers(0, 72), st.integers(RUN + 1, 40), st.booleans())
def test_a_loop_of_any_phrase_fails(page, k, at, times, middle):
    """A phrase of 1 to 8 consecutive words of the page written over and over (17 to 40 times) fails, written
    after the page or in its middle. [M164]
    Why it matters for a score: a model that loops on a short phrase repeats a run of 16 words many times, and
    every word of the loop is in excess."""
    words, bs = page
    k = min(k, len(words))
    at = min(at, len(words) - k)
    loop = " ".join(words[at:at + k] * times)
    i = len(bs) // 2 if middle else len(bs)
    assert not passes(gold_of(words), "".join(f"<p>{b}</p>" for b in [*bs[:i], loop, *bs[i:]]))


MATH = ("$", "\\(", "\\[")
BROKEN_END = re.compile(r"[^\W\d_][-\u2010\u2011]\s*$")     # a word broken at the string's end


@relation(HOLDS, domain="every text string of the loaded tests with a word, no math delimiter and no word broken "
                        "at its end x 3 outputs "
                        "(the string, the string m times, m + 1 times) x 2 golds (the string, the string m times)",
          pool="text, order, repeat, table_cell")
def test_every_loaded_text_string_passes_written_as_often_as_the_page_prints_it():
    """Each text string of the loaded text, order, repeat and table_cell tests, as a page's full text, passes
    an output that writes it once, and fails one that writes it m times, as separate paragraphs, where m is
    the fewest copies that hold a run of 16 of its words twice; with the string m times as the page's text, m
    copies pass and m + 1 fail. A string that ends in a word broken at a line end (`measure-`) is left out: its
    copies join that word to the next copy's first word, as the reading joins a line hyphen
    (test_no_excess_repeats.py pins it). [M165]
    Why it matters for a score: the word count meets the dataset's own strings (its scripts, marks, numbers
    and punctuation), not only generated words."""
    n, bad = 0, []
    for t in TESTS:
        for x in text_strings(t.params):
            w = runners._words(x)
            if not w or any(d in x for d in MATH) or BROKEN_END.search(x):
                continue
            n += 1
            m = math.ceil(RUN / len(w)) + 1
            once, many = runners.NoExcessRepeats(x), runners.NoExcessRepeats(" ".join([x] * m))
            out = lambda c, x=x: "".join(f"<p>{escaped(x)}</p>" for _ in range(c))  # noqa: E731
            for test, c, ok in ((once, 1, True), (once, m, False), (many, m, True), (many, m + 1, False)):
                if passes(test, out(c)) is not ok:
                    bad.append((t.id, x[:40], c, ok))
    assert n, "no loaded text string"
    assert not bad, f"{len(bad)} of {n * 4} cases break, e.g. {bad[:5]}"
