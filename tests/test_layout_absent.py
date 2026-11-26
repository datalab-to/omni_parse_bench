# ruff: noqa: E501
"""`layout_absent`: what a gold file may say, and the verdicts it gives on block lists with and without a block
of a forbidden kind (docs/scoring/layout_absent.md)."""
from __future__ import annotations

import pytest

from omni_parse_bench import score, views
from omni_parse_bench.scorers.unit_tests import runners as R
from omni_parse_bench.scorers.unit_tests import tests as gold

BLANK = ["heading", "table", "caption", "equation", "footnote", "list", "code"]
ALLOWED = [k for k in views.LABELS if k not in BLANK]      # text, page_furniture, figure, form


def gold_of(settings, args=None) -> tuple[gold.Test, ...]:
    return gold.parse("p", {"tests": [{"id": "a", "test_type": "layout_absent", "output_type": "blocks",
                                       "derivation": "model_panel", "tags": [], "args": args or {},
                                       "settings": settings}]})


def block(label, box=(0.2, 0.4, 0.8, 0.5), text=""):
    return {"label": label, "bbox": list(box), "text": text}


def verdict(blocks, kinds=BLANK) -> tuple[bool, str]:
    r = score({"blocks": blocks}, gold_of({"kinds": list(kinds)}))[0]
    return r.result == "pass", r.why


# ------------------------------------------------------------------------------------------- the loader


def test_the_loader_takes_the_kinds():
    [t] = gold_of({"kinds": BLANK})
    assert t.params == R.LayoutAbsent(tuple(BLANK))
    assert set(ALLOWED) == {"text", "page_furniture", "figure", "form"}


@pytest.mark.parametrize("settings, args, why", [
    ({"kinds": ["heading"]}, {"content": {"text": "x", "max_diffs": 0}}, "has no role"),
    ({}, None, "exactly"),
    ({"kinds": ["heading"], "kind": "table"}, None, "exactly"),
    ({"kinds": []}, None, "non-empty list"),
    ({"kinds": "heading"}, None, "non-empty list"),
    ({"kinds": ["heading", 3]}, None, "non-empty list"),
    ({"kinds": ["headline"]}, None, "not block labels"),
    ({"kinds": ["heading", "heading"]}, None, "repeat"),
    ({"kinds": ["heading", "text"]}, None, "cannot forbid text"),
])
def test_the_loader_refuses(settings, args, why):
    with pytest.raises(ValueError, match=why):
        gold_of(settings, args)


# ------------------------------------------------------------------------------------------- verdicts


@pytest.mark.parametrize("blocks", [
    [], [block("text", text="7")], [block("page_furniture", (0.4, 0.02, 0.6, 0.05), "- 7 -")],
    [block("figure", (0, 0, 1, 1))], [block(k) for k in ALLOWED] * 3,
])
def test_allowed_blocks_pass(blocks):
    assert verdict(blocks) == (True, "")


@pytest.mark.parametrize("kind", BLANK)
def test_each_forbidden_kind_fails_alone_and_among_allowed_ones(kind):
    assert not verdict([block(kind)])[0]
    assert not verdict([block("text"), block("figure"), block(kind, (0.5, 0.5, 0.51, 0.51))])[0]


def test_only_the_listed_kinds_are_forbidden():
    assert verdict([block("heading")], kinds=["table"])[0]
    assert not verdict([block("table")], kinds=["table"])[0]


def test_labels_are_compared_as_written():
    # Note: to layout_kind a list or form block is text; here a list is a list, and a text block is never forbidden
    assert not verdict([block("list")], kinds=["list"])[0]
    assert verdict([block("text")], kinds=["list", "form"])[0]


def test_the_why_names_the_first_forbidden_block_and_counts_the_rest():
    blocks = [block("text", text="7"), block("equation", (0.1, 0.2, 0.3, 0.4), "x = 1"), block("heading"), block("code")]
    assert verdict(blocks) == (False, "an equation block at [0.10, 0.20, 0.30, 0.40]: 'x = 1' (and 2 more)")
    assert verdict([block("heading", text="SAMPLE HEADING")]) == (False, "a heading block at [0.20, 0.40, 0.80, 0.50]: 'SAMPLE HEADING'")


def test_text_and_boxes_of_allowed_blocks_are_not_read():
    assert verdict([block("text", (0, 0, 1, 1), "SAMPLE TITLE " * 50)])[0]


def test_without_a_blocks_output_the_test_fails_as_every_layout_test_does():
    r = score({"html": "<p></p>"}, gold_of({"kinds": BLANK}))[0]
    assert (r.result, r.why) == ("fail", "no blocks output")


def test_a_page_with_a_layout_absent_test_is_asked_for_blocks():
    # Note: the harness asks a page for the output types its tests read; a blank page's html test and its
    # layout_absent test ask for both
    ts = gold.parse("p", {"tests": [
        {"id": "a", "test_type": "layout_absent", "output_type": "blocks", "derivation": "model_panel", "tags": [],
         "args": {}, "settings": {"kinds": BLANK}},
        {"id": "b", "test_type": "page_near_empty", "output_type": "html", "derivation": "model_panel", "tags": [],
         "args": {}, "settings": {"max_chars": 20}}]})
    assert gold.wants(ts) == {"blocks", "html"}
    assert gold.wants(ts[:1]) == {"blocks"}
