"""One runner per test type, and the registry that maps a test's `test_type` to it.

A test type is the structure a test checks (`present`: the content is found; `order`: found before;
`table_cell`: found in a cell, under its headings). How content is found depends on its kind, not on
the test type: `found` compares a `Text` within its edits, a `Number` digit for digit, and `Latex` by
what it renders. A test type is a NamedTuple of parameters and a runner, a pure function of the
parameters and one output's view, returning whether the test passed and, if not, why:

    present(Present(Text("Total due", max_diffs=1)), views.html("<p>Total due: 40</p>"))
    # -> (True, "")

HTML test types read a `views.Html`; layout test types read a tuple of `views.Block`s. A test type's
constants (a threshold, a fill ratio) are module constants here, never parameters.

Text is compared only after `normalize.fold`, on both sides. `TYPES` is the registry.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from typing import Any, Literal, NamedTuple

import fuzzysearch
from rapidfuzz import fuzz

from omni_parse_bench import normalize, tables, views

# Note: a test allowing k edits in an n-character string passes at ratio 1 - k/n, and rapidfuzz
# returns exactly that ratio for k edits, which in binary lands a hair under it.
EPS = 1e-9
TABLE_MIN_RATIO = 0.5
MIN_PLACE_COVER = 0.5
# Note: a list item or a key-value field is running text for a `text` test; vendors differ in whether they
# give each such line a block of its own, and the test asks only that it isn't a heading or a table.
AS_TEXT = frozenset({"text", "list", "form"})

Box = views.Box
Block = views.Block
Mark = tuple[bool, str]                            # passed, and why not


# --------------------------------------------------------------------------- text


class Text(NamedTuple):
    text: str
    max_diffs: int      # edits allowed, after `normalize.fold`
    place: tuple[Box, ...] = ()     # where it is printed: a box per line, page fractions; () when not pinned


class Number(NamedTuple):
    number: str         # as printed, e.g. "1,240.00" or "-4.8%"


class Latex(NamedTuple):
    latex: str          # the equation, as LaTeX


# A piece of content a test compares; its kind says how (`found`).
Arg = Text | Number | Latex


def found(a: Arg, v: views.Html) -> Mark:
    """Whether one piece of content is in the output, compared as its kind says: text within its
    `max_diffs` edits; a number digit for digit (`_number_found`); LaTeX by what it renders, or by its
    plain text when plain text writes it without loss (`_latex_found`)."""
    if isinstance(a, Number): return _number_found(a.number, v)
    if isinstance(a, Latex): return _latex_found(a.latex, v)
    ok, r, thr = contains(a.text, v.text, a.max_diffs)
    return _mark(ok, f"{a.text[:60]!r} not found (best {r:.3f} < {thr:.3f})")


class Present(NamedTuple):
    content: Arg


def present(t: Present, v: views.Html) -> Mark:
    return found(t.content, v)


def _number_found(text: str, v: views.Html) -> Mark:
    """Digit-for-digit: strict on digits, decimal point, sign and percent; lenient on thousands
    separators. Bounded by non-digits, so 123 never passes on 1234."""
    n = number(text)
    assert n is not None, text
    written = _NUMBER.match(text.strip())["body"]
    hits = list(_number_pattern(n.core, written).finditer(normalize.fold(v.text).translate(_NUM_CLEAN)))
    if not hits:
        return False, f"{text!r} not found digit-for-digit"
    negative = [(m["pre"] or "").strip() == "-" for m in hits]
    if any(neg == n.negative and (m["pct"] or not n.percent)
           for m, neg in zip(hits, negative, strict=True)):
        return True, ""
    why = [w for w, bad in (("sign lost", n.negative and not any(negative)),
                            ("sign added", not n.negative and all(negative)),
                            ("percent lost", n.percent and not any(m["pct"] for m in hits))) if bad]
    return False, f"{text!r} present but {' / '.join(why) or 'sign or percent differs'}"


class Order(NamedTuple):
    before: str
    after: str
    max_diffs: int


def order(t: Order, v: views.Html) -> Mark:
    """`before` comes before `after`, found as `contains` finds them: after `fold`, then, if either
    is missing, both again after `squeeze`, whose positions keep the folded text's order."""
    for f in (normalize.fold, normalize.squeeze):
        hay = f(v.text)
        a = fuzzysearch.find_near_matches(f(t.before), hay, max_l_dist=t.max_diffs)
        b = fuzzysearch.find_near_matches(f(t.after), hay, max_l_dist=t.max_diffs)
        if a and b: break
    if not a: return False, f"'before' text {t.before[:40]!r} not found"
    if not b: return False, f"'after' text {t.after[:40]!r} not found"
    if any(x.start < y.start for x in a for y in b):
        return True, ""
    return False, f"{t.before[:34]!r} does not appear before {t.after[:34]!r}"


class Repeat(NamedTuple):
    text: str
    expected_count: int


def repeat(t: Repeat, v: views.Html) -> Mark:
    """The line appears exactly N times, as a whole run of words: a longer word doesn't count."""
    chars = [c for c in normalize.fold(t.text) if not c.isspace()]
    pattern = r"(?<![^\W_])" + r"\s*".join(re.escape(c) for c in chars) + r"(?![^\W_])"
    n = len(re.findall(pattern, normalize.fold(v.seen)))
    return _mark(n == t.expected_count, f"{t.text[:50]!r} appears {n}x, not {t.expected_count}x")


# --------------------------------------------------------------------------- tables


class TableCell(NamedTuple):
    cell: str
    relations: dict[Literal["up", "down", "left", "right", "top_heading", "left_heading"], str]
    max_diffs: int
    headings: tuple[str, ...] = ()      # the headings over its column, top to bottom
    section: str | None = None          # the section row nearest above it
    row_groups: tuple[str, ...] = ()    # the cells to its left that span its rows, left to right


def table_cell(t: TableCell, v: views.Html) -> Mark:
    """Some table has a cell matching `cell` whose neighbours and headings match `relations`, and
    which sits under `headings`, in `section` and in `row_groups`.

    `headings` must appear in order among the cells over its column, other cells between them
    allowed: a heading written merged, repeated in each column it covers, or once beside empty cells
    (as a printed table shows a merged heading) is over the column (a row whose only text is in its
    first column is a section label, over every column); one cell may hold two headings the gold
    splits over two rows. `section` is the nearest section row above it (a row of one label, or one
    cell across the table; consecutive ones read together), a cell to its left that spans rows, or
    the first cell of its own row (a long label printed on its own line above, written beside
    instead). `row_groups` must appear in order among the cells to its left in its rows, a label
    written once above empty cells covering them. A cell may be one line of a multi-line cell (dates
    written one per line in one cell rather than one per row)."""
    ts = tables.parse(v.html)
    if not ts:
        return False, "no tables found"
    cell = _fold_cell(t.cell)
    thr = _cell_threshold(cell, t.max_diffs)
    expected = {k: _fold_cell(x) for k, x in t.relations.items() if x}
    reasons = []
    for table in ts:
        for rc in [rc for rc, x in table.text.items() if _one_of(cell, x, thr)]:
            failed = [why for k, want in expected.items()
                      if (why := _relation(table, rc, k, want, t.max_diffs))]
            failed += _structure(t, table, rc)
            if not failed:
                return True, ""
            reasons += failed
    if not reasons:
        return False, f"no cell matching {t.cell!r} in any table"
    return False, f"cells matching {t.cell!r} found, but: {'; '.join(reasons)}"


def _latex_found(latex: str, v: views.Html) -> Mark:
    """The equation is in the output's math, compared by what KaTeX renders (`equations`); or, for an
    equation plain text writes without loss (`plain`), its text reading is in the output's text, as a
    text test would find it."""
    from omni_parse_bench import equations

    ok, why = equations.appears(latex, v.html)
    # Note: "3σ" and "α = 0.05" are faithful transcriptions of $3\sigma$ and $\alpha = 0.05$, as a text
    # test already accepts $3\sigma$ for "3σ"; a fraction or a root written as text loses its structure.
    if ok or not plain(latex): return ok, why
    return (True, "") if contains(f"${latex}$", v.text, 0)[0] else (False, why)


# LaTeX commands whose rendering plain text writes exactly: letters, operators, relations, spacing.
_PLAIN_COMMANDS = frozenset("""
    alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota kappa lambda mu nu xi pi varpi
    rho varrho sigma varsigma tau upsilon phi varphi chi psi omega Gamma Delta Theta Lambda Xi Pi Sigma
    Upsilon Phi Psi Omega
    pm mp times cdot div ast star circ bullet le leq ge geq neq ne approx sim simeq equiv propto ll gg
    in notin subset subseteq supset supseteq cup cap infty partial nabla prime degree ldots cdots dots
    to rightarrow leftarrow leftrightarrow Rightarrow Leftarrow mid
    left right big Big bigl bigr Bigl Bigr quad qquad mathrm text textrm operatorname
""".split())
_COMMAND = re.compile(r"\\([A-Za-z]+)")
# A command-free script or symbol: what makes a span mathematics rather than a plain word or number.
_MATH_MARK = re.compile(r"[\\^_=<>+±×·−]")


def plain(latex: str) -> bool:
    """Whether plain text writes the equation without loss: every command is a symbol (`_PLAIN_COMMANDS`),
    its scripts are single characters or braced plain text, and it is more than a bare word or number."""
    if any(c not in _PLAIN_COMMANDS for c in _COMMAND.findall(latex)): return False
    if re.search(r"[\^_]\{[^{}]*[\\{^_]", latex): return False
    return bool(_MATH_MARK.search(latex)) and len(normalize.squeeze(f"${latex}$")) >= 2


# --------------------------------------------------------------------------- layout


class LayoutKind(NamedTuple):
    content: Text   # its place says where; its text is shown to a reader, never compared
    kind: str       # one of views.LABELS


def layout_kind(t: LayoutKind, blocks: Sequence[Block]) -> Mark:
    """The block that holds the content's place (`holder`) is labelled `kind`; for `text`, a list or
    form block is text too (`AS_TEXT`)."""
    b = holder(t.content.place, blocks)
    if b is None: return _mark(False, f"no block covers {MIN_PLACE_COVER:.0%} of its place")
    ok = b.label in AS_TEXT if t.kind == "text" else b.label == t.kind
    return _mark(ok, f"its block is labelled {b.label!r}, not {t.kind!r}: {b.text[:60]!r}")


def holder(place: Sequence[Box], blocks: Sequence[Block]) -> Block | None:
    """The smallest block covering at least MIN_PLACE_COVER of the place's area, or None.

    Note: coverage of the place, not IoU: a vendor's block may rightly be larger than our place (a
    list for an item, a header line for one of its parts), and the smallest such block is the most
    specific (a cell's text inside a table's block)."""
    total = sum(_area(x) for x in place)
    if total <= 0: return None
    held = [b for b in blocks
            if sum(_area(_intersection(x, b.bbox)) for x in place) / total >= MIN_PLACE_COVER]
    return min(held, key=lambda b: _area(b.bbox), default=None)


# --------------------------------------------------------------------------- registry

Runner = Callable[[Any, Any], Mark]

TYPES: dict[str, tuple[type, Runner]] = {
    "present": (Present, present),
    "order": (Order, order),
    "repeat": (Repeat, repeat),
    "table_cell": (TableCell, table_cell),
    "layout_kind": (LayoutKind, layout_kind),
}


# What a test type's parameters must satisfy beyond their types, checked when a test is loaded.
VALID: dict[str, tuple[Callable[[Any], bool], str]] = {
    "present": (lambda t: not isinstance(t.content, Number) or number(t.content.number) is not None,
                "a number must read as one number, e.g. 1,240.00 or -4.8%"),
    "repeat": (lambda t: t.expected_count > 0, "expected_count must be a positive whole number"),
    "layout_kind": (lambda t: bool(t.content.place) and t.kind in views.LABELS,
                    f"its content needs a place, and its kind must be one of {views.LABELS}"),
}


# --------------------------------------------------------------------------- numbers


class Digits(NamedTuple):
    core: str        # digits, and "." as the decimal point
    negative: bool
    percent: bool


_NUMBER = re.compile(
    r"^(?P<open>\()?(?P<sign>[-−–])?(?P<cur>[$€£¥])?"
    r"(?P<body>\d{1,3}(?:[,.\u202f ]\d{3})*(?:[.,]\d+)?|\d+(?:[.,]\d+)?)"
    r"(?P<pct>%)?(?P<close>\))?[.,;:]?$")
_NUM_CLEAN = str.maketrans({"\u00a0": " ", "\u202f": " ", "−": "-", "–": "-", "—": "-"})


def number(text: str) -> Digits | None:
    """The number a token writes, or None when it isn't one or its separators are ambiguous.

    The decimal point is the last "." or "," followed by 1-2 digits (or any count after a "."), and
    every other separator is a thousands mark. One separator followed by exactly three digits is a
    thousands mark after a ",", and ambiguous after a "."; "16,17" is ambiguous. Parentheses aren't
    a sign.
    """
    m = _NUMBER.match(text.strip())
    if not m: return None
    core = m["body"].replace(" ", "").replace("\u202f", "")
    seps = [i for i, ch in enumerate(core) if ch in ".,"]
    if len(seps) == 1:
        i = seps[0]
        whole, frac = core[:i], core[i + 1:]
        if len(frac) == 3 and whole != "0":
            if core[i] == ".": return None
            core = whole + frac
        elif core[i] == "," and len(frac) <= 2:
            return None
        else:
            core = whole + "." + frac
    elif seps:
        last = seps[-1]
        frac, others = core[last + 1:], {core[i] for i in seps[:-1]}
        decimal = core[last] not in others or len(frac) in (1, 2)
        core = re.sub(r"[.,]", "", core[:last]) + "." + frac if decimal else re.sub(r"[.,]", "", core)
    return Digits(core, bool(m["sign"]), bool(m["pct"]))


def _number_pattern(core: str, written: str = "") -> re.Pattern[str]:
    """The number anywhere in a text, however its thousands are marked, or as `written`.

    A separator may stand only between thousands groups ("1,240", "1 240", "1240", never "12,40"),
    or where the test's own text puts one, so a copy as written always counts ("1.800.934.4850").
    A number starts after anything but a digit or a digit's separator, so "No.12345" holds 12345; a
    "-" is its sign only after a non-word character, so "E-4065" and "COVID-19" are positive."""
    whole, _, frac = core.partition(".")
    groups = [whole[max(0, i - 3):i] for i in range(len(whole), 0, -3)][::-1]
    digits = r"[,\.\u202f ]?".join(re.escape(g) for g in groups)
    if written and written != core: digits = f"(?:{digits}|{re.escape(written)})"
    tail = r"[.,]" + re.escape(frac) if frac else r"(?![.,]\d)"
    return re.compile(r"(?<!\d)(?<!\d[.,])(?P<pre>(?<!\w)-(?=[\d$€£¥])|\(\s?)?(?:[$€£¥]\s?)?"
                      + digits + tail + r"(?P<pct>\s?%)?\)?(?![\d])")


# --------------------------------------------------------------------------- helpers


def _mark(passed: bool, why: str) -> Mark:
    """`why` is kept only when the test fails."""
    return passed, "" if passed else why


def _ratio(needle: str, hay: str, max_diffs: int) -> tuple[bool, float, float]:
    """Fuzzy containment: passes when the best partial match is within `max_diffs` edits."""
    if not needle:
        return False, 0.0, 1.0
    thr = 1.0 - max_diffs / len(needle)
    r = _partial(needle, hay)
    return r >= thr - EPS, r, thr


def _partial(needle: str, hay: str) -> float:
    """How well `needle` matches its best window of `hay`, from 0 to 1.

    Note: rapidfuzz's partial_ratio slides the shorter string over the longer, so a `hay` shorter
    than `needle` would be looked for inside the needle; then the whole of each is compared."""
    return (fuzz.partial_ratio(needle, hay) if len(hay) >= len(needle) else fuzz.ratio(needle, hay)) / 100.0


def contains(needle: str, text: str, max_diffs: int) -> tuple[bool, float, float]:
    """Whether `needle` appears in `text`, with the best match ratio and the threshold: `_ratio`
    after `fold`, then again after `squeeze` for words the text layer glues together."""
    ok, r, thr = _ratio(normalize.fold(needle), normalize.fold(text), max_diffs)
    if ok:
        return True, r, thr
    ok, r2, _ = _ratio(normalize.squeeze(needle), normalize.squeeze(text), max_diffs)
    return ok, max(r, r2), thr


def _fold_cell(s: str) -> str:
    return normalize.fold(s)


def _cell_threshold(cell: str, max_diffs: int) -> float:
    return max(TABLE_MIN_RATIO, 1.0 - max_diffs / max(1, len(cell)))


def _cell_ratio(a: str, b: str) -> float:
    """How alike two folded cells are, also with their spaces removed ("1: 1" and "1:1")."""
    return max(fuzz.ratio(a, b), fuzz.ratio(a.replace(" ", ""), b.replace(" ", ""))) / 100.0


def _relation(table: tables.Table, rc: tables.Cell, kind: str, want: str, max_diffs: int) -> str:
    """Why the cell at `rc` fails one relation, or "" when it holds."""
    thr = _cell_threshold(want, max_diffs)
    if kind.endswith("_heading"):
        cells = tables.heading(table, rc, "up" if kind == "top_heading" else "left")
    else:
        # Note: an empty neighbour stands for the value written over it, above for left and right,
        # beside for up and down: a value over empty cells spans them.
        over = "up" if kind in ("left", "right") else "left"
        cells = {_stand_in(table, c, over) for c in getattr(table, kind)[rc]}
    texts = [_fold_cell(table.text[c]) for c in cells]
    if any(_cell_ratio(want, x) >= thr for x in texts):
        return ""
    if not texts:
        return f"no {kind} cell"
    best = max(texts, key=lambda x: _cell_ratio(want, x))
    return f"{kind} {best!r} doesn't match {want!r} ({_cell_ratio(want, best):.2f})"


def _one_of(want: str, got: str, thr: float) -> bool:
    """Whether cell text `got`, or one of its lines, matches the folded `want`."""
    return any(_cell_ratio(want, _fold_cell(x)) >= thr for x in {got, *got.split("\n")} if x.strip())


def _in_order(want: Sequence[str], got: Sequence[str], max_diffs: int) -> bool:
    """Whether `want` appears in `got` in order, others between allowed; one cell of `got` may hold
    several consecutive items of `want` joined."""
    i = 0
    for g in got:
        for n in range(len(want) - i, 0, -1):
            joined = _fold_cell(" ".join(want[i:i + n]))
            if _one_of(joined, g, _cell_threshold(joined, max_diffs)):
                i += n
                break
    return i == len(want)


def _structure(t: TableCell, table: tables.Table, rc: tables.Cell) -> list[str]:
    """Why the cell at `rc` isn't under `headings`, in `section` or in `row_groups`."""
    if not (t.headings or t.section or t.row_groups): return []
    out = []
    over = [table.text[c] for c in tables.above(table, rc)]
    left = [table.text[c] for c in tables.beside(table, rc)]
    if t.headings and not _in_order(t.headings, over, t.max_diffs):
        out.append(f"not under the headings {' > '.join(t.headings)!r}")
    if t.row_groups and not _in_order(t.row_groups, left, t.max_diffs):
        out.append(f"not in the row groups {' > '.join(t.row_groups)!r}")
    if t.section:
        want = _fold_cell(t.section)
        thr = _cell_threshold(want, t.max_diffs)
        run = tables.section(table, rc)
        groups = [table.text[c] for c in tables.beside(table, rc) if tables.spanning_rows(table, c)]
        # Note: a section label printed on its own line above its row may fairly be written as that row's
        # first cell instead ("ADH-I intron 5 | 851 (703) | 306"): a long label set on a line of its own
        # still names the row below it.
        first = next((c for c in table.grid[min(table.covers[rc][0])] if c is not None), None)
        groups += [table.text[first]] if first is not None and first != rc else []
        in_run = any(_one_of(want, " ".join(run[i:]), thr) for i in range(len(run)))
        if not in_run and not any(_one_of(want, g, thr) for g in groups):
            out.append(f"not in the section {t.section!r} (nearest above: {' '.join(run) or 'none'!r})")
    return out


def _stand_in(table: tables.Table, c: tables.Cell, over: str) -> tables.Cell:
    """`c`, or when it's empty, the first non-empty cell walking `over` from it."""
    seen = {c}
    while not table.text.get(c, "").strip() and (nxt := getattr(table, over).get(c)):
        c = min(nxt)
        if c in seen: break
        seen.add(c)
    return c


def _area(b: Sequence[float]) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _intersection(a: Sequence[float], b: Sequence[float]) -> Box:
    return max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
