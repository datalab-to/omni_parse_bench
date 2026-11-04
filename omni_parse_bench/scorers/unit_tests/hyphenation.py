"""Exact continuation matches that retain the interpretation with a genuine hyphen.

Only a hyphen followed by whitespace inside a word is optional. Unspaced compound
hyphens remain required. This is a fallback, not a new comparison normal form or an
additional fuzzy edit allowance. Only text presence uses this fallback.
"""
from __future__ import annotations

from omni_parse_bench import normalize


# Note: broadening fold's deletion rule to uncased letters would erase genuine Korean compound
# hyphens across wraps (test_published_korean_compound_regression); keep both readings here.


def matches(needle: str, text: str) -> bool:
    """An exact substring match that uses an evidenced continuation hyphen inside the match.

    A small nondeterministic automaton consumes equal characters, or skips optional
    hyphens on either side. Equivalent states are merged at each text position: at
    most 2 * (len(needle) + 1) states, O(len(needle) * len(text)) work, no backtracking.
    Each state records whether a continuation hyphen was retained or skipped inside the match.
    """
    want, want_optional = normalize.continuations(needle)
    hay, hay_optional = normalize.continuations(text)
    if not want_optional and not hay_optional:
        return False
    if not want:
        return False
    # Dropping every hyphen is a necessary condition, never an acceptance rule.
    # Let native substring search reject unrelated text before scanning Python states.
    if want.replace("-", "") not in hay.replace("-", ""):
        return False
    # Bit 1: no continuation used; bit 2: a continuation hyphen was retained or skipped.
    active = {}
    optional = sorted(want_optional)
    for j, c in enumerate(hay):
        active[0] = active.get(0, 0) | 1  # A substring may start at each character.
        following = {}
        for i, flags in active.items():
            if i < len(want) and want[i] == c:
                if 0 < i < len(want) - 1 and (i in want_optional or j in hay_optional):
                    flags |= 2
                following[i + 1] = following.get(i + 1, 0) | flags
            if j in hay_optional and 0 < i < len(want):
                following[i] = following.get(i, 0) | 2
        # Epsilon closure: omit optional needle hyphens without consuming text.
        for i in optional:
            if i in following:
                following[i + 1] = following.get(i + 1, 0) | 2
        if following.get(len(want), 0) & 2:
            return True
        active = following
    return False
