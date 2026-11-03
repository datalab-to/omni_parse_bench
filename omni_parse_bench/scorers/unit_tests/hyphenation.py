"""Exact continuation matches that retain the interpretation with a genuine hyphen.

Only a hyphen followed by whitespace inside a word is optional. Unspaced compound
hyphens remain required. This is a fallback, not a new comparison normal form or an
additional fuzzy edit allowance. Only text presence uses this fallback.
"""
from __future__ import annotations

import functools
import unicodedata

from omni_parse_bench import normalize


def _word_end(s: str, i: int) -> bool:
    # A combining mark qualifies only when its cluster has a preceding letter.
    while i >= 0 and unicodedata.category(s[i]).startswith("M"):
        i -= 1
    return i >= 0 and unicodedata.category(s[i]).startswith("L")


@functools.lru_cache(maxsize=128)
def _prepare(s: str) -> tuple[str, frozenset[int]]:
    cased = normalize._cased(s, preserve_dashes=True, preserve_line_hyphens=True)
    optional = set()
    offset = 0
    for i, c in enumerate(cased):
        if c in "-‐‑" and _word_end(cased, i - 1):
            j = i + 1
            while j < len(cased) and cased[j].isspace():
                j += 1
            if (j > i + 1 and j < len(cased)
                    and unicodedata.category(cased[j]).startswith("L")
                    and not cased[j].isupper() and not cased[j].istitle()):
                optional.add(offset)
        offset += len(c.lower())
    # Case conversion can expand a character; map optional indices before squeezing.
    folded = normalize._DASH.sub("-", cased.lower())
    chars, squeezed_optional = [], set()
    for i, c in enumerate(folded):
        if c.isspace():
            continue
        if i in optional:
            squeezed_optional.add(len(chars))
        chars.append(c)
    return "".join(chars), frozenset(squeezed_optional)


def matches(needle: str, text: str) -> bool:
    """An exact substring match that uses an evidenced continuation hyphen inside the match.

    A small nondeterministic automaton consumes equal characters, or skips optional
    hyphens on either side. Equivalent states are merged at each text position: at
    most 2 * (len(needle) + 1) states, O(len(needle) * len(text)) work, no backtracking.
    Each state records whether a continuation hyphen was retained or skipped inside the match.
    """
    want, want_optional = _prepare(needle)
    hay, hay_optional = _prepare(text)
    if not want_optional and not hay_optional:
        return False
    if not want:
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
