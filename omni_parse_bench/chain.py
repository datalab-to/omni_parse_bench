"""The normalizer chain Id < Text < Cased < Words and the one distance.

A claim is read at one point of the chain. The point fixes how the gold and the output are read (the same for
both) and which edits are free:

    Id      every character the reader holds
    Text    typography folded (the reader's Id -> Text fold); footnote marks kept; a wrapped hyphen of the
            output free
    Cased   footnote marks deleted; a space of the gold free; a space between two Hangul syllables or two
            phrase-spaced clusters free on both sides; a line or block break free
    Words   case of words folded (`lower()`, with `İ` as `i` first); a quantity keeps its case

`windows` is the one search: the output's windows, at token edges, within `k` edits of the gold under the OSA
distance over grapheme clusters. A quantity is one atomic symbol: it matches its own spelling for nothing and
any other edit touching one costs more than any budget. Every rule here is a named switch (`switches.py`) so a
regrade can say which rule moved a verdict; with `chain` on and the rules off, the search is a plain
Levenshtein substring search over characters.

Tokens are fixed per output (the reader), so a window at one point is a window at every coarser one: the
raw candidates only grow along the chain (law L1). A candidate is identified by the content tokens it covers.
"""

from __future__ import annotations

import dataclasses
import functools
from collections.abc import Iterable
from typing import NamedTuple

import regex

from . import reader, switches, work
from .reader import BREAK, CONTENT, MARK, MATH, QTY, SPACE, SYM, WORD, WRAP, Token  # noqa: F401

ID, TEXT, CASED, WORDS = "Id", "Text", "Cased", "Words"
POINTS = (ID, TEXT, CASED, WORDS)
RANK = {p: i for i, p in enumerate(POINTS)}

# The chain's own rules: each a switch of the same name.
CHAIN_RULES = (
    "word_edges",
    "space_one_sided",
    "osa",
    "qty_atomic",
    "marks_free",
    "wrap_free",
    "break_free",
    "cell_windows",
)
INF = 1 << 30
_CLUSTER = regex.compile(r"\X")


def rules_now() -> frozenset[str]:
    """The chain rules in force, as the switches stand."""
    return frozenset(r for r in CHAIN_RULES if switches.on(r))


class Cell(NamedTuple):
    """One symbol of the distance: a grapheme cluster, an atomic quantity, a space, a break or a wrap."""

    sym: str
    kind: str  # c: cluster, q: quantity, s: space, b: break, w: wrap
    tok: int  # index of its token in the token list
    start: bool  # a window may start before it
    end: bool  # a window may end after it
    free: bool  # deleting it (as the gold's cell or as the output's) costs nothing
    group: int  # the cell group of its token: a window stays in one group


def _lower(c: str) -> str:
    if c == "İ":
        return "i"
    low = c.lower()
    return low if len(low) == len(c) else c


def cells(
    tokens: list[Token],
    point: str,
    *,
    gold: bool,
    rules: frozenset[str] | None = None,
    keep_marks: bool = False,
) -> list[Cell]:
    """The cells of `tokens` read at `point`, as the gold (`gold`) or as the output."""
    if point not in RANK:
        raise ValueError(f"unknown point {point!r}; known: {POINTS}")
    rules = rules_now() if rules is None else rules
    r = RANK[point]
    cased, text = r >= RANK[CASED], r >= RANK[TEXT]
    out: list[Cell] = []
    group, seen = 0, None  # the cell group changes where content moves from one table cell to another
    for i, t in _expanded(tokens):
        if t.cls in CONTENT:
            if "cell_windows" in rules:
                if seen is not None and t.cell != seen[0]:
                    group += 1
                seen = (t.cell,)
        if t.cls == MARK and cased and "marks_free" in rules and not keep_marks:
            continue
        if t.cls == SPACE:
            if gold:
                free = cased  # a space of the gold is free from Cased on (one-sided, or squeezed)
            else:
                joined = tokens[i].cls == SPACE and _script_free(tokens, i)
                free = cased and (joined or "space_one_sided" not in rules)
            out.append(Cell(" ", "s", i, True, True, free, group))
        elif t.cls == BREAK:
            free = cased and "break_free" in rules
            out.append(Cell(" ", "b", i, True, True, free, group))
        elif t.cls == WRAP:
            if text and not gold and "wrap_free" in rules:
                out.append(Cell("-", "w", i, True, True, True, group))
            else:
                out.append(Cell("-", "c", i, True, False, False, group))
                out.append(Cell(" ", "b", i, False, True, False, group))
        elif t.cls == QTY and "qty_atomic" in rules:
            out.append(Cell(t.canon, "q", i, True, True, False, group))
        else:
            word = t.cls == WORD
            body = t.canon if t.cls in (QTY, MATH) else t.text
            parts = _CLUSTER.findall(body)
            edges = "word_edges" in rules
            kind = "m" if t.cls == MARK else "c"  # a mark equals only a mark, never a letter or a quantity
            for j, c in enumerate(parts):
                if r >= RANK[WORDS] and word:
                    c = "".join(_lower(x) for x in c) if len(c) > 1 else _lower(c)
                out.append(
                    Cell(c, kind, i, j == 0 or not edges, j == len(parts) - 1 or not edges, False, group)
                )
    return out


def _expanded(tokens: list[Token]):
    """(index, token) pairs, a `Math` token replaced by the tokens of its text reading, each with the math
    token's index: math reads as words, quantities and symbols as the text around it does."""
    for i, t in enumerate(tokens):
        if t.cls == MATH:
            for u in reader.tokenize(t.canon, rules=reader_rules()):
                yield i, dataclasses.replace(u, cell=t.cell)
        else:
            yield i, t


def _script_free(tokens: list[Token], i: int) -> bool:
    """A space between two Hangul syllables or two phrase-spaced clusters."""
    j, k = i - 1, i + 1
    if j < 0 or k >= len(tokens):
        return False
    a, b = tokens[j], tokens[k]
    return a.cls == WORD and b.cls == WORD and a.script == b.script and a.script in ("hangul", "phrase")


class Window(NamedTuple):
    first: int  # the first content token it covers (index in the token list)
    last: int  # the last content token it covers
    cost: int
    lo: int  # cell offsets in the output's cells
    hi: int


def _sub(g: Cell, o: Cell) -> int:
    if g.kind == "m" or o.kind == "m":
        return 0 if g.kind == o.kind and g.sym == o.sym else INF
    if g.kind == "q" or o.kind == "q":
        return 0 if g.kind == o.kind and g.sym == o.sym else INF
    return 0 if g.sym == o.sym else 1


def _search(a: list[Cell], b: list[Cell], k: int, *, whole: bool, osa: bool) -> list[tuple[int, int, int]]:
    """(start, end, cost) of each window of `b` (cell offsets) within `k` of `a`: starting at a cell a
    window may start before, ending after one it may end after; `whole` takes `b` entire. One row per cell of
    `a`, kept sparse: for each offset of `b`, the starts whose cost is at most `k`."""
    m, n = len(a), len(b)
    Row = dict[int, dict[int, int]]
    states = 0  # relaxations: the deterministic measure of the search's work

    def relax(row: Row, j: int, c: int, st: int) -> None:
        nonlocal states
        states += 1
        d = row.setdefault(j, {})
        if c < d.get(st, INF):
            d[st] = c

    def close(row: Row) -> None:
        """Insertions of the output's cells along the row."""
        nonlocal states
        for j0 in sorted(row):
            for st, c0 in list(row[j0].items()):
                j, c = j0, c0
                while j < n:
                    c += INF if b[j].kind == "q" else (0 if b[j].free else 1)
                    if c > k:
                        break
                    j += 1
                    states += 1
                    d = row.setdefault(j, {})
                    if d.get(st, INF) <= c:
                        break
                    d[st] = c

    row: Row = {}
    if whole:
        row[0] = {0: 0}
    else:
        for j in range(n):
            if b[j].start:
                row[j] = {j: 0}
    close(row)
    prev2: Row = {}
    for i in range(1, m + 1):
        g = a[i - 1]
        dg = INF if g.kind == "q" else (0 if g.free else 1)
        new: Row = {}
        for j, d in row.items():
            for st, c in d.items():
                if c + dg <= k:
                    relax(new, j, c + dg, st)
                if j < n and (cs := c + _sub(g, b[j])) <= k:
                    relax(new, j + 1, cs, st)
        if osa and i >= 2 and g.kind == "c" and a[i - 2].kind == "c" and g.sym != a[i - 2].sym:
            for j, d in prev2.items():
                if (
                    j + 1 < n
                    and b[j].kind == "c"
                    and b[j + 1].kind == "c"
                    and b[j].sym == g.sym
                    and b[j + 1].sym == a[i - 2].sym
                ):
                    for st, c in d.items():
                        if c + 1 <= k:
                            relax(new, j + 2, c + 1, st)
        close(new)
        prev2, row = row, new
        if not row:
            work.add("search_states", states)
            return []
    work.add("search_states", states)
    work.check_search(m, n, states)
    if whole:
        return [(0, n, row[n][0])] if n in row and 0 in row[n] else []
    return [(st, j, c) for j, d in row.items() if j == 0 or b[j - 1].end for st, c in d.items()]


def windows(
    gold: list[Token],
    out: list[Token],
    point: str,
    k: int = 0,
    *,
    whole: bool = False,
    rules: Iterable[str] | None = None,
) -> list[Window]:
    """Every window of `out` within `k` edits of `gold`, read at `point`: the raw candidates. Identified by
    the content tokens they cover, the cheapest per identity."""
    rules = rules_now() if rules is None else frozenset(rules)
    if point == CASED and k:
        raise ValueError(
            "a Cased claim keeps its budget at 0 (case-protected edits with a budget are defeated by "
            "deleting then inserting)"
        )
    # a gold that is nothing but footnote marks keeps them, and so does the output it is read against
    keep = not any(t.cls in CONTENT for t in gold) and any(t.cls == MARK for t in gold)
    a = cells(gold, point, gold=True, rules=rules, keep_marks=keep)
    b = cells(out, point, gold=False, rules=rules, keep_marks=keep)
    if whole:
        # the whole supplied unit: one cell group (a unit across table cells is refused), and an empty gold
        # equals an empty unit (free spaces and breaks aside)
        if len({c.group for c in b if out[c.tok].cls in CONTENT}) > 1:
            return []
        return [Window(-1, -1, c, 0, len(b)) for _, _, c in _search(a, b, k, whole=True, osa="osa" in rules)]
    if not any(c.kind != "s" and c.kind != "b" for c in a):
        return []
    found: dict[tuple[int, int], Window] = {}
    osa = "osa" in rules
    bounds = [0]
    for x in range(1, len(b)):
        if b[x].group != b[x - 1].group:
            bounds.append(x)
    bounds.append(len(b))
    for lo, hi in zip(bounds, bounds[1:], strict=False):
        for s, e, cost in _search(a, b[lo:hi], k, whole=whole, osa=osa):
            toks = [b[x].tok for x in range(lo + s, lo + e) if out[b[x].tok].cls in CONTENT]
            toks = toks or [b[x].tok for x in range(lo + s, lo + e) if out[b[x].tok].cls == MARK]
            if not toks:
                continue
            w = Window(toks[0], toks[-1], cost, lo + s, lo + e)
            old = found.get((w.first, w.last))
            if old is None or w.cost < old.cost:
                found[(w.first, w.last)] = w
    return sorted(found.values(), key=lambda w: (w.first, -w.last))


def match(
    gold: list[Token], out: list[Token], point: str, k: int = 0, *, rules: Iterable[str] | None = None
) -> bool:
    """Whether some window of `out` is within `k` edits of `gold` at `point`."""
    return bool(windows(gold, out, point, k, rules=rules))


def equal(
    gold: list[Token], other: list[Token], point: str, k: int = 0, *, rules: Iterable[str] | None = None
) -> bool:
    """The whole-mode relation: `other` as a whole is within `k` edits of `gold` at `point`."""
    return bool(windows(gold, other, point, k, whole=True, rules=rules))


def blame(gold: list[Token], out: list[Token], point: str, k: int = 0) -> list[str]:
    """The rules whose switching off alone makes a failed match pass: the rules that decided the verdict."""
    on = rules_now()
    return [r for r in sorted(on) if match(gold, out, point, k, rules=on - {r})]


@functools.lru_cache(maxsize=256)
def _read_output(html: str, rules: frozenset[str]) -> tuple[Token, ...]:
    return tuple(reader.read(html, rules=rules).tokens)


@functools.lru_cache(maxsize=1024)
def _read_gold(text: str, rules: frozenset[str]) -> tuple[Token, ...]:
    return tuple(reader.tokenize(text, rules=rules))


def reader_rules() -> frozenset[str]:
    return frozenset(r for r in reader.RULES if switches.on(r))


def tokens_of_output(html: str) -> list[Token]:
    return list(_read_output(html, reader_rules()))


def tokens_of_gold(text: str) -> list[Token]:
    return list(_read_gold(text, reader_rules()))
