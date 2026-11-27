# ruff: noqa: E501
"""Relations of the reader (M199 to M204): text a page hides or writes only as alt text is not read; a window stops at a table
cell; two writings of one page read as the same tokens; tokens cover the text; case and footnote marks change no token's
boundaries. Each rule runs with its switch on (`switches.using`); the loaded strings are the gold's own."""
from __future__ import annotations

import re

from hypothesis import assume, given
from hypothesis import strategies as st

from metamorphic.common import HOLDS, TESTS, escaped, every_real_test, relation, text_strings
from omni_parse_bench import normalize, reader, score, switches
from omni_parse_bench.scorers.unit_tests import runners
from omni_parse_bench.scorers.unit_tests import tests as gold

RESERVED = re.compile("[\\ufdd0-\\ufdd2\\u2029\\n]")      # the reader's own sentinels and the line breaks of a string
STRINGS = sorted({x for t in TESTS for x in text_strings(t.params) if x.strip() and not RESERVED.search(x)})
LONG = [x for x in STRINGS if len(normalize.fold(x)) >= runners.ABSENT_MIN_CHARS]
SPLITTABLE = [x for x in STRINGS if len(x.split()) >= 2]
HIDERS = ['<span style="display:none">{}</span>', '<span style="visibility:hidden">{}</span>', "<span hidden>{}</span>",
          "<template>{}</template>", "<noscript>{}</noscript>", '<input type="hidden" value="{}">',
          '<div style="display: none"><p>{}</p></div>']


def STEP1():
    """The reader's rules of step 1 on, and none of the later ones (the text fold changes what a token holds)."""
    return switches.using(**{r: r not in ("text_fold", "leading_dot", "math_spans") for r in reader.RULES})


def raw_test(kind: str, x: str) -> dict:
    base = {"id": "a", "derivation": "authored", "tags": [], "output_type": "html"}
    if kind == "present":
        return base | {"test_type": "present", "args": {"content": {"text": x, "max_diffs": 0}}, "settings": {}}
    return base | {"test_type": "present", "args": {"content": {"text": x, "max_diffs": 0}}, "settings": {"absent": True}}


def passes(kind: str, x: str, html: str) -> bool:
    """The verdict of one present (or absent) test of `x` on `html`, with the reader's rules on."""
    with STEP1():
        r = score({"html": html, "blocks": []}, gold.parse("p", {"tests": [raw_test(kind, x)]}))[0]
    return r.result == "pass"


def loadable(kind: str, x: str) -> bool:
    try:
        gold.parse("p", {"tests": [raw_test(kind, x)]})
    except ValueError:
        return False
    return True


def tokens(html: str) -> list[tuple[str, str]]:
    with STEP1():
        return [(t.cls, t.text) for t in reader.read(html).tokens]


@relation(HOLDS, domain="every loaded text string x 7 ways to hide it (display:none, visibility:hidden, hidden, "
                        "template, noscript, a hidden input, a hidden block) x present and absent",
          pool="text, order, repeat, table_cell")
@given(st.sampled_from(LONG), st.sampled_from(HIDERS))
def test_text_the_page_hides_is_not_read(x, hider):
    """A string written only inside hidden markup (`display:none`, `visibility:hidden`, `hidden`, `<template>`,
    `<noscript>`, a hidden input) is not on the page: its `present` test fails and its `absent` test passes, while the
    same string written in view passes `present` and fails `absent`. [M199]
    Why it matters for a score: a system cannot earn a text test by writing the answer where no reader sees it, and a
    page does not fail a test of what it must not print for text it never shows."""
    assume(loadable("absent", x))
    hidden = f"<p>Other text on the page.</p>{hider.format(escaped(x))}"
    shown = f"<p>Other text on the page.</p><p>{escaped(x)}</p>"
    assert not passes("present", x, hidden), hidden
    assert passes("absent", x, hidden), hidden
    assert passes("present", x, shown) and not passes("absent", x, shown), shown


@relation(HOLDS, domain="every loaded text string x 3 ways to write it as an image's alt text (an `alt` attribute, "
                        "a markdown image, both) x present and absent",
          pool="text, order, repeat, table_cell")
@given(st.sampled_from(LONG), st.integers(0, 2))
def test_alt_text_is_not_page_text(x, how):
    """A string written only as an image's alt text is not on the page: `present` fails, `absent` passes; written as the
    figure's caption it passes `present`. [M200]
    Why it matters for a score: a description of a figure is not text the page prints (provisional: the alt-text rule is
    reported on its own by the side-by-side run)."""
    assume(loadable("absent", x))
    e = escaped(x).replace('"', "&quot;")
    html = [f'<img src="a.png" alt="{e}"><p>Other text.</p>', f"<p>Other text. ![{x}](a.png)</p>",
            f'<img alt="{e}">![{x}](b.png)<p>Other text.</p>'][how]
    assume("]" not in x and "[" not in x and "(" not in x and ")" not in x or how == 0)
    assert not passes("present", x, html), html
    assert passes("absent", x, html), html
    assert passes("present", x, f'<figure><img alt="{e}"><figcaption>{escaped(x)}</figcaption></figure>')


@relation(HOLDS, domain="every loaded text string of two or more words x the split after each word x two adjacent "
                        "table cells or two paragraphs",
          pool="text, order, repeat, table_cell")
@given(st.sampled_from(SPLITTABLE), st.data())
def test_a_window_stops_at_a_cell_and_not_at_a_paragraph(x, data):
    """A string written across two adjacent table cells has no window of tokens that holds all of it: a window crosses
    the cell boundary. Written across two paragraphs, a window holds it. [M201]
    Why it matters for a score: a gold phrase is not found by gluing the neighbouring cells of a table."""
    words = x.split()
    k = data.draw(st.integers(1, len(words) - 1))
    a, b = " ".join(words[:k]), " ".join(words[k:])
    with STEP1():
        cells = reader.read(f"<table><tr><td>{escaped(a)}</td><td>{escaped(b)}</td></tr></table>")
        paras = reader.read(f"<p>{escaped(a)}</p><p>{escaped(b)}</p>")
    for d, crosses in ((cells, True), (paras, False)):
        content = [i for i, t in enumerate(d.tokens) if t.cls in reader.CONTENT]
        assume(len(content) >= 2)
        with STEP1():
            assert d.crosses_cell(content[0], content[-1]) is crosses, (a, b)


@relation(HOLDS, domain="every loaded text string x 4 rewrites that leave the document unchanged (entities, wrapper "
                        "tags, attributes, a markup-free span)",
          pool="text, order, repeat, table_cell")
@given(st.sampled_from(STRINGS), st.integers(0, 3))
def test_two_writings_of_one_page_read_as_the_same_tokens(x, how):
    """Writing the same text with its characters as entities, in a `div` with attributes in place of a `p`, inside a
    `span`, or with extra white space between tags gives the same tokens. [M202]
    Why it matters for a score: the reader is a function of the document, so a verdict cannot depend on how a system
    writes the markup around its text."""
    assume(not RESERVED.search(x))
    e = escaped(x)
    ent = "".join(f"&#{ord(c)};" if c.isalnum() or c in ".,;:-" else escaped(c) for c in x)
    page = [f"<p>{e}</p>", f"<p>{ent}</p>", f"<div class='a' id='b'><span style='color:red'>{e}</span></div>",
            f"\n <p>\n{e}\n</p> \n"][how]
    assert tokens(page) == tokens(f"<p>{e}</p>"), page


@relation(HOLDS, domain="every loaded text string x the same string as gold and as the text of a page",
          pool="text, order, repeat, table_cell")
@given(st.sampled_from(STRINGS))
def test_tokens_cover_the_text(x):
    """The tokens of a string, joined, are the string (a space between two Han or kana characters aside), and each
    token's offsets cut its own text out of the joined text. [M203]
    Why it matters for a score: tokens are fixed for an output and nothing is lost between the reader and a verdict, so
    a reason can quote the text it points at."""
    assume(not RESERVED.search(x))
    with STEP1():
        toks = reader.tokenize(x)
    joined = "".join(t.text for t in toks)
    squeezed = re.sub(r"(?<=[぀-ヿ一-鿿])\s+(?=[぀-ヿ一-鿿])", "", x)
    assert re.sub(r"\s+", "", joined) == re.sub(r"\s+", "", squeezed), (x, joined)
    assert all(joined[t.start:t.end] == t.text for t in toks)


@relation(HOLDS, domain="every loaded text string x each Word of it: its case swapped, or a footnote mark after it",
          pool="text, order, repeat, table_cell")
@given(st.sampled_from(STRINGS), st.data())
def test_case_and_a_footnote_mark_change_no_token_boundary(x, data):
    """Swapping the case of one Word (letters only: `Kb` and `kB` are a Word and a quantity), or writing a footnote mark (`<sup>1</sup>`) right after a Word that ends in a
    letter, leaves every other token as it was: the same classes in order, and, once marks are set aside, the same
    texts. [M204]
    Why it matters for a score: the tokens of the rest of the output do not move, so case and marks can be folded
    without changing what a window is."""
    assume(not RESERVED.search(x))

    def read(text: str) -> list[reader.Token]:
        with STEP1():
            return list(reader.read(f"<p>{escaped(text)}</p>").tokens)

    base = read(x)
    ws = [i for i, t in enumerate(base) if t.cls == "Word" and t.text.isalpha() and t.text.swapcase() != t.text]
    assume(ws)
    i = data.draw(st.sampled_from(ws))
    w = base[i]
    at = x.find(w.text)                      # the Word's first spelling in the string (one paragraph: offsets agree)
    assume(at >= 0 and w.start == at)
    cased = read(x[:at] + w.text.swapcase() + x[at + len(w.text):])
    assume(len(cased) == len(base))
    assert [t.cls for t in cased] == [t.cls for t in base]
    assert [t.text for j, t in enumerate(cased) if j != i] == [t.text for j, t in enumerate(base) if j != i]
    with STEP1():
        marked = [t for t in reader.read(
            f"<p>{escaped(x[:w.end])}<sup>1</sup>{escaped(x[w.end:])}</p>").tokens if t.cls != "Mark"]
    assert [(t.cls, t.text) for t in marked] == [(t.cls, t.text) for t in base if t.cls != "Mark"], (x, w.text)


@every_real_test("text strings", note="each as gold hidden, written as alt text, split across cells, and tokenized")
def test_every_real_text_string_is_hidden_by_markup_and_is_covered_by_its_tokens():
    """Every real text string, hidden in `display:none` markup, fails its `present` test and passes its `absent` test;
    tokenized, it is covered by its tokens. [M199, M203]
    Why it matters for a score: as for M199 and M203, over the dataset's own strings."""
    n = 0
    for x in sorted({x for t in TESTS for x in text_strings(t.params)}):
        if not x.strip() or RESERVED.search(x): continue
        with STEP1():
            toks = reader.tokenize(x)
        assert re.sub(r"\s+", "", "".join(t.text for t in toks)) == re.sub(r"\s+", "", re.sub(
            r"(?<=[぀-ヿ一-鿿])\s+(?=[぀-ヿ一-鿿])", "", x)), x
        if len(normalize.fold(x)) >= runners.ABSENT_MIN_CHARS and loadable("absent", x):
            hidden = f'<p>Other text on the page.</p><span style="display:none">{escaped(x)}</span>'
            assert not passes("present", x, hidden) and passes("absent", x, hidden), x
            n += 1
    assert n, "no real string: the check is empty"
