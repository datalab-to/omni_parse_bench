"""`marks.style_marks`: what an inline style does to marks, declaration by declaration."""
from __future__ import annotations

import pytest

from omni_parse_bench import marks

F = frozenset


@pytest.mark.parametrize("style, add, drop, own", [
    ("font-weight: bold", {"bold"}, set(), set()),
    ("font-weight: 650", {"bold"}, set(), set()),
    ("font-weight: 500", set(), {"bold"}, set()),
    ("font-weight: bold; font-weight: normal", set(), {"bold"}, set()),      # the later declaration wins
    ("font-weight: normal; font-weight: bold", {"bold"}, set(), set()),
    ("font: bold 12px serif", {"bold"}, {"italic"}, set()),
    ("font: italic bold 12px serif", {"bold", "italic"}, set(), set()),
    ("font: 12px serif", set(), {"bold", "italic"}, set()),                   # names neither: plain
    ("font: inherit", set(), set(), set()),                                  # no change
    ("font: var(--font)", set(), set(), set()),
    ("font-weight: inherit", set(), set(), set()),
    ("text-decoration: underline", {"underline"}, set(), set()),
    ("text-decoration: underline; text-decoration: none", set(), set(), {"underline", "strike"}),
    ("text-decoration: line-through underline", {"underline", "strike"}, set(), set()),
    ("vertical-align: super", {"sup"}, {"sub"}, set()),
    ("vertical-align: sub", {"sub"}, {"sup"}, set()),
    ("vertical-align: baseline", set(), set(), {"sup", "sub"}),
    ("color: red; vertical-align: top", set(), set(), set()),
])
def test_what_a_style_does_to_marks(style, add, drop, own):
    assert marks.style_marks(style) == (F(add), F(drop), F(own))
