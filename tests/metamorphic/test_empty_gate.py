# ruff: noqa: E501
"""Relations of the negative tests on an empty output (M196 to M198): `present` with `{"absent": true}`, `no_excess_repeats` and
`layout_absent` fail an output that writes nothing, unless the page's gold holds a `page_near_empty` test; an output that writes
something gets the verdict the test's own runner gives it."""
from __future__ import annotations

from hypothesis import assume, given
from hypothesis import strategies as st

from metamorphic.common import HOLDS, TESTS, escaped, every_real_test, relation, text_strings
from omni_parse_bench import normalize, score, views
from omni_parse_bench.scorers.unit_tests import runners
from omni_parse_bench.scorers.unit_tests import tests as gold

STRINGS = sorted({x for t in TESTS for x in text_strings(t.params) if len(normalize.fold(x)) >= runners.ABSENT_MIN_CHARS})
KINDS = [k for k in views.LABELS if k != "text"]
# What an output that writes nothing looks like: no html, white space, invisible format characters, markup with
# no text, an image alone (its description is not read).
EMPTY_HTML = ["", " \n ", "<p> </p><br>", "​﻿­", "<div></div>", "<img src='a.png' alt='a long description of the scan'>"]
BLANK = {"id": "blank", "test_type": "page_near_empty", "output_type": "html", "derivation": "authored", "tags": [],
         "args": {}, "settings": {"max_chars": 20}}


def raw(kind: str, x: str, i: str = "a") -> dict:
    """One negative test of the string `x` (a layout_absent test of `x`'s first kind, for the third kind)."""
    base = {"id": i, "derivation": "authored", "tags": [], "output_type": "html"}
    if kind == "absent":
        return base | {"test_type": "present", "args": {"content": {"text": x, "max_diffs": 0}}, "settings": {"absent": True}}
    if kind == "no_excess_repeats":
        return base | {"test_type": "no_excess_repeats", "args": {"content": {"text": x, "max_diffs": 0}}, "settings": {}}
    return base | {"test_type": "layout_absent", "output_type": "blocks", "args": {}, "settings": {"kinds": [KINDS[len(x) % len(KINDS)]]}}


def loadable(kind: str, x: str) -> bool:
    """Whether the loader takes `x` as the text of this negative test (no_excess_repeats refuses a script written
    without spaces, or text with no word)."""
    try:
        gold.parse("p", {"tests": [raw(kind, x)]})
    except ValueError:
        return False
    return True


def verdict(kind: str, x: str, pred: dict, blank: bool = False, limit: int = 20) -> tuple[bool, str]:
    near = BLANK | {"settings": {"max_chars": limit}}
    r = {r.id: r for r in score(pred, gold.parse("p", {"tests": [raw(kind, x), *([near] if blank else [])]}))}["a"]
    return r.result == "pass", r.why


def own(kind: str, x: str, pred: dict) -> bool:
    """What the test's own runner says, without the gate."""
    [t] = gold.parse("p", {"tests": [raw(kind, x)]})
    if t.output_type == "blocks":
        return runners.layout_absent(t.params, views.blocks(pred["blocks"]))[0]
    return runners.TYPES[t.test_type][1](t.params, views.html(pred["html"]))[0]


def empty_pred(html: str, kind: str) -> dict:
    return {"html": html, "blocks": []}


@relation(HOLDS, domain="every loaded text string of 20+ folded characters x 3 negative tests (absent, "
                        "no_excess_repeats, layout_absent) x 6 empty outputs (no html, white space, invisible "
                        "characters, no text, an image alone; no blocks)",
          pool="text, order, repeat, table_cell")
@given(st.sampled_from(STRINGS), st.sampled_from(["absent", "no_excess_repeats", "layout_absent"]), st.sampled_from(EMPTY_HTML))
def test_an_empty_output_fails_a_negative_test_on_a_normal_page(x, kind, html):
    """An output that writes nothing (no html, or html with nothing a reader sees; no blocks) fails a
    `present` test with `{"absent": true}`, a `no_excess_repeats` test and a `layout_absent` test, on a page
    whose gold holds no `page_near_empty` test. [M196]
    Why it matters for a score: silence earns nothing on a test of what a page does not hold; before, an
    empty output passed all three."""
    assume(loadable(kind, x))
    ok, why = verdict(kind, x, empty_pred(html, kind))
    assert not ok and why.startswith("no output"), (kind, html, why)


@relation(HOLDS, domain="every loaded text string of 20+ folded characters x 3 negative tests x 6 empty outputs "
                        "x a page_near_empty limit of 0 to 500",
          pool="text, order, repeat, table_cell")
@given(st.sampled_from(STRINGS), st.sampled_from(["absent", "no_excess_repeats", "layout_absent"]), st.sampled_from(EMPTY_HTML),
       st.integers(0, 500))
def test_an_empty_output_passes_a_negative_test_on_a_blank_page(x, kind, html, limit):
    """On a page whose gold holds a `page_near_empty` test, whatever its limit, the same empty output passes the
    three negative tests: an empty output is the right answer there. [M197]
    Why it matters for a score: a model that writes nothing on a blank page is not marked wrong for the banned
    strings, the repeat check or the blocks check of that page."""
    assume(loadable(kind, x))
    assert verdict(kind, x, empty_pred(html, kind), blank=True, limit=limit)[0], (kind, html, limit)


@relation(HOLDS, domain="every loaded text string of 20+ folded characters x 3 negative tests x 5 outputs (the "
                        "string written, a character dropped, other text, the string as an image description, "
                        "the string in a block) x a blank page or not",
          pool="text, order, repeat, table_cell")
@given(st.sampled_from(STRINGS), st.sampled_from(["absent", "no_excess_repeats", "layout_absent"]), st.integers(0, 4), st.booleans())
def test_an_output_that_writes_something_gets_its_runners_verdict(x, kind, which, blank):
    """For an output that writes something, `score` gives a negative test the verdict of its own runner (the
    reading found, a loop, a forbidden block fails; an output that avoids it passes), on a blank page or not.
    [M198]
    Why it matters for a score: the gate for an empty output moves no verdict of an output that wrote
    something."""
    assume(loadable(kind, x))
    e = escaped(x)
    html = [f"<p>{e}</p>", f"<p>{escaped(x[:5] + x[6:])}</p>", "<p>Some other text, unrelated.</p>",
            f"<img src='a.png' alt='{e}'><p>Other text.</p>", f"<p>{e} {e}</p>"][which]
    blocks = [{"label": "table", "bbox": [0, 0, 1, 1], "text": x}, {"label": "text", "bbox": [0, 0, 1, 1], "text": x},
              {"label": "heading", "bbox": [0, 0, 1, 1], "text": ""}, {"label": "text", "bbox": [0, 0, 1, 1], "text": ""},
              {"label": "table", "bbox": [0, 0, 1, 1], "text": ""}][which]
    pred = {"html": html, "blocks": [blocks]}
    assert verdict(kind, x, pred, blank)[0] == own(kind, x, pred), (kind, html, blocks, blank)


@every_real_test("text strings", note="each as the text of a negative test, on a normal page and a blank one, empty output")
def test_every_real_text_string_fails_an_empty_output_as_a_negative_test_and_passes_it_on_a_blank_page():
    """Every real text string (20 or more folded characters for absent) as the text of an absent test, of a
    `no_excess_repeats` test and (for its length) of a `layout_absent` test fails an empty output on a normal
    page and passes it on a page with a `page_near_empty` test. [M196, M197]
    Why it matters for a score: as for M196 and M197, over the dataset's own strings."""
    n = 0
    for x in sorted({x for t in TESTS for x in text_strings(t.params)}):
        for kind in ("absent", "no_excess_repeats", "layout_absent"):
            if kind == "absent" and len(normalize.fold(x)) < runners.ABSENT_MIN_CHARS:
                continue
            if not loadable(kind, x):
                continue
            pred = empty_pred("", kind)
            assert not verdict(kind, x, pred)[0], (kind, x)
            assert verdict(kind, x, pred, blank=True)[0], (kind, x)
            n += 1
    assert n, "no real string: the check is empty"
