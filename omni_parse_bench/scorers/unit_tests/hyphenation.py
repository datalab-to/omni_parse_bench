"""Exact continuation matches that retain the interpretation with a genuine hyphen.

Only a hyphen followed by whitespace inside a word is optional. Unspaced compound
hyphens remain required. This is a fallback, not a new comparison normal form or an
additional fuzzy edit allowance: each test type tries it only where its own comparison
fails (`present` for its text, `order` for its two strings, `repeat` for its count and
`table_cell` for each cell it compares).
"""
from __future__ import annotations

from collections.abc import Callable
from typing import NamedTuple

from omni_parse_bench import normalize


# Note: broadening fold's deletion rule to uncased letters would erase genuine Korean compound
# hyphens across wraps (test_published_korean_compound_regression); keep both readings here.


class Copy(NamedTuple):
    """An exact match ending at `end` of the text read without spaces (`normalize.continuations`): the
    earliest and latest start of a match ending there, and whether it retained or skipped a continuation
    hyphen."""
    first: int
    last: int
    end: int
    continued: bool


Cut = Callable[[str, int], bool]


def matches(needle: str, text: str, cut_before: Cut | None = None, cut_after: Cut | None = None,
            cased: bool = False) -> bool:
    """An exact substring match that uses an evidenced continuation hyphen inside the match.
    `cut_before(s, i)` and `cut_after(s, j)`, if given, reject a match starting at i or ending at j
    of the text with its spaces. With `cased` both sides keep their case."""
    if not optional(needle, text, cased=cased):
        return False
    return any(c.continued for c in copies(needle, text, cut_before, cut_after, cased))


def optional(*strings: str, cased: bool = False) -> bool:
    """Whether any of `strings` holds a continuation hyphen, the only thing the fallback can change."""
    return any(normalize.continuations(s, cased=cased)[1] for s in strings)


def copies(needle: str, text: str, cut_before: Cut | None = None, cut_after: Cut | None = None,
           cased: bool = False) -> list[Copy]:
    """Every exact match of `needle` in `text`, each hyphen of either side that a line broke after read kept
    or dropped, one `Copy` for each place a match ends and for each of: with or without such a hyphen.
    `cut_before`, `cut_after` and `cased` are as for `matches`.

    A small nondeterministic automaton consumes equal characters, or skips optional
    hyphens on either side. Equivalent states are merged at each text position: at
    most 2 * (len(needle) + 1) states, O(len(needle) * len(text)) work, no backtracking.
    Each state records whether a continuation hyphen was retained or skipped inside the match,
    and the earliest and latest place a match reaching it started.
    """
    want, want_optional = normalize.continuations(needle, cased=cased)
    hay, hay_optional = normalize.continuations(text, cased=cased)
    if not want:
        return []
    # Dropping every hyphen is a necessary condition, never an acceptance rule.
    # Let native substring search reject unrelated text before scanning Python states.
    if want.replace("-", "") not in hay.replace("-", ""):
        return []
    optional_at = sorted(want_optional)
    # Note: the main path judges a match's edges, so this exact match must too (a space is not glued).
    spaced = normalize.continuations(text, spaced=True, cased=cased)[0] if cut_before or cut_after else ""
    kept = [k for k, c in enumerate(spaced) if c != " "]
    found: list[Copy] = []
    # (state, continued) -> (earliest start, latest start)
    active: dict[tuple[int, bool], tuple[int, int]] = {}

    def reach(states: dict, key: tuple[int, bool], span: tuple[int, int]) -> None:
        old = states.get(key)
        states[key] = span if old is None else (min(old[0], span[0]), max(old[1], span[1]))

    for j, c in enumerate(hay):
        if not (cut_before and cut_before(spaced, kept[j])):
            reach(active, (0, False), (j, j))  # A substring may start at each character.
        following: dict[tuple[int, bool], tuple[int, int]] = {}
        for (i, continued), span in active.items():
            if i < len(want) and want[i] == c:
                inner = 0 < i < len(want) - 1 and (i in want_optional or j in hay_optional)
                reach(following, (i + 1, continued or inner), span)
            if j in hay_optional and 0 < i < len(want):
                reach(following, (i, True), span)
        # Epsilon closure: omit optional needle hyphens without consuming text.
        for i in optional_at:
            for continued in (False, True):
                if (i, continued) in following:
                    reach(following, (i + 1, True), following[i, continued])
        if not (cut_after and cut_after(spaced, kept[j] + 1)):
            found += [Copy(*following[len(want), u], j + 1, u)
                      for u in (False, True) if (len(want), u) in following]
        active = following
    return found
