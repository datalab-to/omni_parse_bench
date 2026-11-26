"""One runner per test type, and the registry that maps a test's `test_type` to it (`TYPES`).

A test type is the structure a test checks (`present`: the content is found; `order`: found before;
`table_cell`: found in a cell, under its headings). It is a NamedTuple of parameters and a runner, a pure
function of the parameters and one output's view, returning whether the test passed and, if not, why.
HTML test types read a `views.Html`; layout test types read a tuple of `views.Block`s. A test type's
constants (a threshold, a fill ratio) are module constants here, never parameters.
"""
from __future__ import annotations

import functools
import itertools
import re
import unicodedata
from collections.abc import Callable, Sequence
from typing import Any, Literal, NamedTuple

import fuzzysearch
from fuzzysearch.common import group_matches
from fuzzysearch.levenshtein import find_near_matches_levenshtein
from rapidfuzz import fuzz

from omni_parse_bench import markdown, marks, normalize, tables, views
from omni_parse_bench.scorers.unit_tests import hyphenation

# Note: a ratio test (table_cell, or present's first pass) allowing k edits in an n-character string
# passes at ratio 1 - k/n, and rapidfuzz returns exactly that ratio for k substitutions, which in binary lands
# a hair under it.
EPS = 1e-9
TABLE_MIN_RATIO = 0.5
MIN_PLACE_COVER = 0.5
# Note: a block covering exactly half a place has a coverage of 0.5 in exact arithmetic and a hair under or
# over it in floats (areas of boxes that were scaled or summed), so the threshold gets the slack `EPS` gives.
COVER_EPS = 1e-9
# Note: two blocks of equal area in exact arithmetic can differ by a hair in floats ([0.2, 0.15, 0.4, 0.25]
# and [0.2, 0.2, 0.6, 0.25] are both 0.02), so a block must be smaller by more than this to hold the place
# instead of one listed before it. It is relative to the area, so scaled boxes give the same verdict.
AREA_EPS = 1e-9
# Note: a list item or a key-value field is running text for a `text` test; vendors differ in whether they
# give each such line a block of its own, and the test asks only that it isn't a heading or a table.
AS_TEXT = frozenset({"text", "list", "form"})

Box = views.Box
Block = views.Block
Mark = tuple[bool, str]                            # passed, and why not


# --------------------------------------------------------------------------- text


class Text(NamedTuple):
    text: str
    max_diffs: int      # edits allowed, after `normalize.fold` (`normalize.fold_cased` with exact_case)
    place: tuple[Box, ...] = ()     # where it is printed: a box per line, page fractions; () when not pinned
    exact_case: bool = False    # compare with case kept (`normalize.fold_cased`); a `present` content only


class Number(NamedTuple):
    number: str         # as printed, e.g. "1,240.00" or "-4.8%"


class Latex(NamedTuple):
    latex: str          # the equation, as LaTeX


# A piece of content a test compares; its kind says how (`found`).
Arg = Text | Number | Latex


def found(a: Arg, v: views.Html) -> Mark:
    """Whether one piece of content is in the output, compared as its kind says, never by its test type: a
    `Text` within its `max_diffs` edits, after `normalize.fold` on both sides; a `Number` digit for digit
    (`_number_found`); and `Latex` by what it renders, or by its plain text when plain text writes it without
    loss (`_latex_found`).

        present(Present(Text("Total due", max_diffs=1)), views.html("<p>Total due: 40</p>"))
        # -> (True, "")"""
    if isinstance(a, Number): return _number_found(a.number, v)
    if isinstance(a, Latex): return _latex_found(a.latex, v)
    # Note: `exact_case` runs every path below on the case-kept fold (fold_cased); nothing else changes.
    fold_one, fold_marks = (normalize.fold_cased, normalize.unmarked_cased) if a.exact_case else (
        normalize.fold, normalize.unmarked)
    # Note: a gold that holds a digit must match with its numbers exact (`_numbers_kept`), at any budget, so
    # no retry without spaces joins "2 1" into "21". `_contains` passing is necessary for that, so the rule
    # runs only on what it passes.
    strict = any(c.isdigit() for c in fold_one(a.text))
    ok, r, thr, window = _contains(a.text, v.text, a.max_diffs, fold_one, fold_one)
    lost = strict and ok and not _numbers_kept(a.text, v.text, a.max_diffs, fold_one, fold_one)
    ok = ok and not lost
    # Note: fold reads a bracketed footnote marker as a spaced number (so a number test still sees it, and
    # a gold that writes the marker finds it), and the text view a mark set as a superscript the same way,
    # which leaves either free only at the end of the gold: "Smith[1] and Jones" and
    # "Smith<sup>1</sup> and Jones" missed "Smith and Jones". Retry with the page's markers dropped.
    if not ok and ((page := views.unmarked(v.html)) is not None or "[" in v.text):
        page = v.text if page is None else page
        if _contains(a.text, page, a.max_diffs, fold_marks, fold_one)[0] and (
                not strict or _numbers_kept(a.text, page, a.max_diffs, fold_marks, fold_one)):
            return True, ""
    if not ok and hyphenation.matches(a.text, v.text, _cut_before, _cut_after, cased=a.exact_case,
                                      numbers=strict):
        return True, ""
    if lost:
        return False, (f"{a.text[:60]!r} not found with its numbers exact (a number differs, or one was "
                       "added, split or joined)")
    if not ok and _only_glued(a.text, v.text, fold_one):
        return False, f"{a.text[:60]!r} found only inside a longer number"
    near = f"; closest {_excerpt(window)!r}" if window else ""
    return _mark(ok, f"{a.text[:60]!r} not found (best {r:.3f} < {thr:.3f}){near}")


class Present(NamedTuple):
    content: Arg
    # `{"blank_after": true}`: the content is a form field's label, and nothing follows it (`blank_after`)
    blank_after: bool = False
    printed: Text | None = None     # the field's printed placeholder (`__/__/____`), allowed once
    stops: tuple[Text, ...] = ()    # every other field label on the page: where a field's region ends
    md_mask: str | None = None      # `printed` as markdown writes it (set by the scorer)


def present(t: Present, v: views.Html) -> Mark:
    return blank_after(t, v) if t.blank_after else found(t.content, v)


# --------------------------------------------------------------------------- blank form fields

_PLACEHOLDER = re.compile(r"[\s_.\u00b7\u2026]*")    # what a blank field may show: white space, _ . · …
_TABLE_OPEN, _TABLE_CLOSE = "\u00a7opb-table\u00a7", "\u00a7opb-table-end\u00a7"    # marks round a table
_TABLE_TAG = re.compile(r"<(/?)table\b[^<>]*>", re.I)
_TABLE_MARK = re.compile(f"{_TABLE_OPEN}|{_TABLE_CLOSE}")


def blank_after(t: Present, v: views.Html) -> Mark:
    """Every occurrence of the label `t.content` is followed by nothing but white space and placeholder
    characters, up to the next stop or the end of the page, and has nothing before it (in its paragraph,
    line or cell, when no other stop comes first). A label in a table cell reads the rest of its cell, then
    every cell to its right up to another field's label, then, down its column, the cells below up to
    another field's label (or the table's end, and then the text after the table up to the next stop); and
    the cells to its left, back to another field's label. Passes only when plain `present` passes too. See
    docs/scoring/present-text.md, "Blank fields".

    The page is the text view without image descriptions, nothing for an element that holds nothing (as
    `page_near_empty`); a table is read by `tables.parse`, so a label in one is judged by its cells, not by
    the text that comes after it in reading order."""
    ok, why = found(t.content, v)
    if not ok:
        return False, why
    label = t.content.text
    t = t._replace(md_mask=_md_mask(t, v.html))
    flow, spans, loose, chunks = _flow(v.html)
    reasons: list[str] = []
    copies = 0
    for start, region, cut in _regions(t, flow):
        if any(a <= start < b and parsed for a, b, parsed in spans):
            continue    # in a table the cell reader parses: its cells judge it
        copies += 1
        if why := _in_text(label, t, region, cut):
            reasons.append(why)
    for line in re.split(r"[\u2029\n]", loose):
        hay = normalize.fold(line)
        reasons += [why for start, _, _ in _regions(t, hay) if (why := _before(label, t, hay, start))]
    for (_, end, parsed), chunk in zip(spans, chunks, strict=True):
        for n, table in enumerate(tables.parse(chunk) if parsed else ()):
            for rc, text in table.text.items():
                cell = _fold_cell(text)
                for start, region, _cut in _regions(t, cell):
                    copies += 1
                    if rest := _rest(t, region):
                        reasons.append(f"{label[:60]!r} is followed by {rest[:60]!r} in its cell")
                    elif why := _before(label, t, cell, start):
                        reasons.append(why)
                    else:
                        why, at_end = _value_cell(t, table, rc)
                        if why:
                            reasons.append(f"{label[:60]!r} cell's {why}")
                        elif at_end and n == 0 and (why := _after_table(t, flow, end)):
                            reasons.append(f"{label[:60]!r} {why}")
    if not copies:
        return False, f"{label[:60]!r} not found whole, at a word edge, in one paragraph or one table cell"
    if not reasons:
        return True, ""
    return False, "; ".join(reasons[:2]) + (f" (and {len(reasons) - 2} more)" if len(reasons) > 2 else "")


def _before(label: str, t: Present, hay: str, start: int) -> str:
    """Why the text before the label that starts at `start` in the folded `hay` (a paragraph, a line or a
    cell) holds a value, or "" when it is blank, or when another field's label comes first (what follows
    that label is its value)."""
    prior = hay[:start]
    if _PLACEHOLDER.fullmatch(prior):
        return ""
    for x in [*t.stops, t.content]:    # an earlier copy of the label is judged by its own region
        if (f := normalize.fold(x.text)) and any(b <= start for _, b in _copies(f, hay, False)):
            return ""
    return f"{label[:60]!r} has {prior.strip()[:60]!r} before it"


def _after_table(t: Present, flow: str, end: int) -> str:
    """Why the text after a label's table, up to the next stop, holds a value (a value written past the
    table), or "" when it is blank."""
    stops = sorted(a for x in [*t.stops, t.content] if (f := normalize.fold(x.text))
                   for a, _ in _copies(f, flow, False))
    cut = next((a for a in stops if a >= end), None)
    if not (rest := _rest(t, _TABLE_MARK.sub("", flow[end:cut]))):
        return ""
    return (f"is followed by {rest[:60]!r} after its table, "
            f"{'before the next field' if cut is not None else 'to the end of the page'}")


def _in_text(label: str, t: Present, region: str, cut: bool) -> str:
    """Why the text region after a label holds a value, or "" when it is blank."""
    if not (rest := _rest(t, _TABLE_MARK.sub("", region))):
        return ""
    return (f"{label[:60]!r} is followed by {rest[:60]!r} "
            f"{'before the next field' if cut else 'to the end of the page'}")


def _flow(html: str) -> tuple[str, list[tuple[int, int, bool]], str, list[str]]:
    """The folded text view of a page for `blank_after`, with a mark round each outermost table, and the
    stretches the tables take in it, each with whether the cell reader parses it (`tables.parse`): one it
    cannot parse (`<td>` outside a `<tr>`) is read as text. Also the text view (not folded) of the page
    without the tables the cell reader parses, and the html of each outermost table."""
    parts, loose, chunks, last, depth, begun, wholes = [], [], [], 0, 0, 0, []
    for m in _TABLE_TAG.finditer(html):
        if m[1]:
            if depth:
                depth -= 1
                if depth == 0:
                    parts += [html[last:m.end()], f"<p>{_TABLE_CLOSE}</p>"]
                    chunks.append(html[begun:m.end()])
                    wholes.append(bool(tables.parse(chunks[-1])))
                    loose += [] if wholes[-1] else [chunks[-1]]
                    last = m.end()
        else:
            if depth == 0:
                parts += [html[last:m.start()], f"<p>{_TABLE_OPEN}</p>"]
                loose.append(html[last:m.start()])
                last = begun = m.start()
            depth += 1
    parts.append(html[last:])
    if depth:
        chunks.append(html[begun:])
        wholes.append(bool(tables.parse(chunks[-1])))
        loose += [] if wholes[-1] else [chunks[-1]]
    else:
        loose.append(html[last:])
    flow = normalize.fold(views.text(_NOTHING.sub("", "".join(parts)), alt=False))
    opens = [m.start() for m in re.finditer(re.escape(_TABLE_OPEN), flow)]
    closes = [m.end() for m in re.finditer(re.escape(_TABLE_CLOSE), flow)]
    closes += [len(flow)] * (len(opens) - len(closes))
    return (flow, [(a, b, ok) for (a, b), ok in zip(zip(opens, closes, strict=True), wholes, strict=True)],
            views.text(_NOTHING.sub("", "".join(loose)), alt=False), chunks)


def _edge(want: str, hay: str, i: int, j: int) -> bool:
    """Whether `hay[i:j]`, a copy of the folded `want`, starts and ends at a word edge and is not cut out of
    a longer number."""
    return not ((_WORD_CHAR.match(want[0]) and i and _WORD_CHAR.match(hay[i - 1]))
                or (_WORD_CHAR.match(want[-1]) and _WORD_CHAR.match(hay[j:j + 1]))
                or _glued(hay, i, j))


def _copies(want: str, hay: str, squeezed: bool) -> list[tuple[int, int]]:
    """The copies of the folded `want` in the folded `hay` at a word edge, as spans of `hay`, or of its
    squeezed text (no spaces) when `squeezed`."""
    kept = [k for k, c in enumerate(hay) if c != " "] if squeezed else None
    w, h = (want.replace(" ", ""), hay.replace(" ", "")) if squeezed else (want, hay)
    out = []
    for m in re.finditer(f"(?={re.escape(w)})", h):
        i, j = m.start(), m.start() + len(w)
        if _edge(want, hay, *_folded_span(i, j, kept)):
            out.append((i, j))
    return out


def _regions(t: Present, hay: str) -> list[tuple[int, str, bool]]:
    """Each occurrence of the label in the folded `hay`: where it starts (in `hay`), the text after it up to
    the next stop or the end (in `hay`, or squeezed when the label is found only with its spaces removed),
    and whether a stop ended it. A copy inside a longer stop (`Name:` in `Last Name:`) is that stop."""
    label = normalize.fold(t.content.text)
    squeezed = not (spans := _copies(label, hay, False))
    if squeezed:
        spans = _copies(label, hay, True)
    kept = [k for k, c in enumerate(hay) if c != " "] if squeezed else None
    w = hay.replace(" ", "") if squeezed else hay
    stops = sorted(s for x in t.stops if (f := normalize.fold(x.text)) for s in _copies(f, hay, squeezed))
    ends = sorted([a for a, _ in stops] + [i for i, _ in spans])    # the next copy of the label ends one too
    out = []
    for i, j in spans:
        if any(a <= i and j <= b and b - a > j - i for a, b in stops):
            continue
        cut = next((a for a in ends if a >= j), None)
        out.append((_folded_span(i, j, kept)[0], w[j:cut], cut is not None))
    return out


def _md_mask(t: Present, html: str) -> str | None:
    """The printed placeholder as the markdown converter writes it (`__/__/____` is read as bold and comes out
    as `//`), folded, when the page holds the converter's html for it: a page written in markdown. A literal
    `//` in html is not that mask."""
    if t.printed is None or "_" not in t.printed.text:
        return None
    converted = markdown.to_html(t.printed.text).strip()
    inner = re.sub(r"^<p>|</p>$", "", converted)
    if inner == t.printed.text or inner not in html:
        return None
    return normalize.fold(views.text(converted, alt=False)).strip() or None


def _rest(t: Present, region: str) -> str:
    """What a field's region shows besides one copy of its printed placeholder and the characters a blank
    shows; "" when it is blank. A mask of underscores that a markdown page lost to bold (`_md_mask`) is the
    printed placeholder too."""
    if t.printed is not None:
        printed = normalize.fold(t.printed.text)
        for mask in (printed, printed.replace(" ", ""), t.md_mask):
            if mask and mask.strip() and mask in region:
                region = region.replace(mask, "", 1)
                break
    return "" if _PLACEHOLDER.fullmatch(region) else region.strip()


def _value_cell(t: Present, table: tables.Table, rc: tables.Cell) -> tuple[str, bool]:
    """Why a cell beside the label cell `rc` holds a value ("" when none does), and whether nothing in the
    table comes after the label (no other field's label below it), so that its region goes on past the table.

    Read, besides the rest of the label's own cell: every cell to its right, up to another field's label
    (its whole text is a stop); then, in a table of several columns, the cells below it in its columns, up
    to another field's label (a header-row layout, a label in the last column, a blank cell to the right);
    and the cells to its left, back to another field's label (the value of that field, not this one's). An
    image is a value. Neighbors are read raw (no stand-in)."""
    # another field's label, or another copy of this one, ends a region
    stops = [f for x in [*t.stops, t.content] if (f := normalize.fold(x.text))]
    def is_label(x: tables.Cell) -> bool:
        """Whether the cell's whole text is a field's label."""
        return _fold_cell(table.text[x]) in stops
    def has_label(x: tables.Cell) -> bool:
        """Whether a field's label is written in the cell."""
        hay = _fold_cell(table.text[x])
        return any(_copies(f, hay, False) for f in stops)
    def value(x: tables.Cell | None) -> str:
        """What the cell shows: "" for a blank one or a field's label."""
        if x is None or is_label(x):
            return ""
        return _rest(t, _fold_cell(table.text[x])) or ("an image" if x in table.figures else "")
    rows, cols = table.covers[rc]
    width = len(table.grid[0])
    for r in rows:    # to the left, back to a field's label
        seen = list(dict.fromkeys(x for x in reversed(table.grid[r][:min(cols)]) if x is not None))
        held = [v for x in seen if (v := value(x))]
        if held and not any(has_label(x) for x in seen):
            return f"value cell (left) holds {held[0][:60]!r}", False
    value_cols: set[int] = set(cols)    # the columns the value may be written in, below
    for r in rows:    # to the right, up to a field's label
        for c in range(max(cols) + 1, width):
            if (x := table.grid[r][c]) is None:
                continue
            if is_label(x):
                break
            if v := value(x):
                return f"value cell (right) holds {v[:60]!r}", False
            value_cols.add(c)
    for r in range(max(rows) + 1, len(table.grid)):    # below, down to a field's label in the label's columns
        if any(x is not None and is_label(x) for x in (table.grid[r][c] for c in cols)):
            return "", False
        if width > 1 and (held := [v for x in dict.fromkeys(table.grid[r][c] for c in sorted(value_cols))
                                   if (v := value(x))]):
            return f"value cell (below) holds {held[0][:60]!r}", False
    return "", True


def _number_found(text: str, v: views.Html) -> Mark:
    """Digit-for-digit: strict on digits, separators as the gold writes them, sign and percent.
    Bounded by non-digits, so 123 never passes on 1234."""
    n = number(text)
    assert n is not None, text
    written = _NUMBER.match(text.strip())["body"]
    hits = list(_number_pattern(written).finditer(normalize.fold(v.text).translate(_NUM_CLEAN)))
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
    """`before` comes before `after`, found as `contains` finds them: after `fold`, then, if either has
    no exact match there, both again after `squeeze`, whose positions keep the folded text's
    order. An exact match counts only if it is not cut out of a longer number (`_edges_ok`).

    Note: whether to retry does not depend on the budget: with an edit to spend, both can be found in the
    folded text out of order while the squeezed text, which passed with fewer edits, holds them in order."""
    folded = normalize.fold(v.text)
    cut = [False, False]
    both = False
    for f in (normalize.fold, normalize.squeeze):
        hay = f(v.text)
        kept = [k for k, c in enumerate(folded) if not c.isspace()] if f is normalize.squeeze else None

        raw = [_near(f(x), hay, t.max_diffs) for x in (t.before, t.after)]
        a, b = (_unglued(m, folded, kept) for m in raw)
        cut = [c or (bool(m) and not x) for c, m, x in zip(cut, raw, (a, b), strict=True)]
        if a and b and any(x.start < y.start for x in a for y in b):
            return True, ""
        both = both or bool(a and b)
        if all(any(not m.dist for m in x) for x in (a, b)): break
    if _order_hyphenated(t, v):
        return True, ""
    if both: return False, f"{t.before[:34]!r} does not appear before {t.after[:34]!r}"
    if not a: return False, f"'before' text {t.before[:40]!r} {_why_missing(cut[0])}"
    return False, f"'after' text {t.after[:40]!r} {_why_missing(cut[1])}"


def _order_hyphenated(t: Order, v: views.Html) -> bool:
    """Whether `before` comes before `after` when a hyphen a line broke after, on the page or in either
    string, is read kept or dropped (`hyphenation.copies`): an exact copy of each, starting in order, one of
    them reading such a hyphen. The fallback `present` has, for a pair; it spends no edits."""
    if not hyphenation.optional(t.before, t.after, v.text):
        return False
    a, b = (hyphenation.copies(x, v.text, _cut_before, _cut_after) for x in (t.before, t.after))
    first = min((c.first for c in a), default=None)
    first_continued = min((c.first for c in a if c.continued), default=None)
    last = max((c.last for c in b), default=None)
    last_continued = max((c.last for c in b if c.continued), default=None)
    return any(x is not None and y is not None and x < y
               for x, y in ((first_continued, last), (first, last_continued)))


class Repeat(NamedTuple):
    content: Text | Number      # a `Text` is counted as whole words, a `Number` as `present` finds one
    expected_count: int


def repeat(t: Repeat, v: views.Html) -> Mark:
    """The content appears exactly N times. A `Text` is counted as a whole run of words: a longer word doesn't
    count. When the count is not N, it is counted again with each hyphen a line broke after, on the page or in
    the line, read kept or dropped (`_hyphenated_count`), and N copies there pass too. A `Number` is counted
    as `present` finds one, digit for digit, line by line (`_number_copies`); the hyphen reading does not
    apply to it. Neither counts image descriptions."""
    if isinstance(t.content, Number):
        n = _number_copies(t.content.number, v)
        return _mark(n == t.expected_count, f"{t.content.number!r} appears {n}x, not {t.expected_count}x")
    text = t.content.text
    n = _text_copies(text, v.seen)
    if n == t.expected_count:
        return True, ""
    h = _hyphenated_count(text, v.seen)
    if h == t.expected_count:
        return True, ""
    how = "" if h is None else " (reading line-end hyphens kept or dropped)"
    return False, f"{text[:50]!r} appears {n if h is None else h}x{how}, not {t.expected_count}x"


def _text_copies(text: str, page: str) -> int:
    """How many whole-word copies of `text` the page holds, after `normalize.fold` on both. """
    chars = [c for c in normalize.fold(text) if not c.isspace()]
    pattern = r"(?<![^\W_])" + r"\s*".join(re.escape(c) for c in chars) + r"(?![^\W_])"
    return len(re.findall(pattern, normalize.fold(page)))


@functools.lru_cache(maxsize=64)
def _number_lines(html: str, marks: bool = False) -> tuple[str, ...]:
    """The lines a page shows without alt text, for counting numbers: its text view with each block and each
    <br> a line of its own, a footnote marker (`<sup>2</sup>`, `[2]`) and a list's numbers left out, each line
    folded. A line is the unit because a space groups digits ("12 500") and a block break is a space to
    fold. With `marks`, a footnote marker is kept, as `present` reads it (a spaced number)."""
    page = re.sub(r"<br\s*/?>", views.BREAK, re.sub(r"<(/?)ol\b", r"<\1ul", html, flags=re.I), flags=re.I)
    q = views.reading(views.Seq(page), alt=False, marks=marks)
    return tuple(line if marks else normalize.unmarked(line) for line in q.s.split(views.BREAK))


def _number_copies(text: str, v: views.Html) -> int:
    """How many copies of the number `text` the page holds: the places `_number_found` accepts, each counted
    once (a copy is a match of `_number_pattern` with the gold's sign and, if the gold has one, its percent
    sign), counted line by line (`_number_lines`). Matches never overlap and are bounded by non-digits, so
    12.5 is not a copy inside 12.5.7. A gold of plain or space-grouped digits ("500", "12 500") is also no
    copy where a group of digits continues across a space: 500 is not a copy in "12 500" and neither is 12 (a
    gold of three digits is not preceded by a number of up to three digits and a space, a gold is not followed
    by a space and three digits). `present` is more lenient on both counts."""
    n = number(text)
    assert n is not None, text
    written = _NUMBER.match(text.strip())["body"]
    pattern, plain = _number_pattern(written), re.sub(r"\s", " ", written)
    # digits that a further group could continue, and ones that are themselves a group to continue
    grouped = bool(re.fullmatch(r"\d{1,3}(?: \d{3})*", plain))
    starts_group = grouped and bool(re.match(r"\d{3}(?: |$)", plain))
    copies = 0
    # Note: a gold written with spaces ("12 500") has a place between its groups where a footnote marker could
    # be dropped and join two numbers that `present` reads as two ("12<sup>2</sup> 500"), so it is counted on
    # the lines with their markers kept; a marker after it ("12 500<sup>1</sup>") is still not a group
    for line in _number_lines(v.html, " " in plain):
        line = line.translate(_NUM_CLEAN)
        for m in pattern.finditer(line):
            if ((m["pre"] or "").strip() == "-") != n.negative or not (m["pct"] or not n.percent):
                continue
            if (starts_group and re.search(r"(?<![\w.,])\d{1,3}(?: \d{3})* $", line[:m.start()])
                    or grouped and re.match(r" \d{3}(?!\w)", line[m.end():])):
                continue
            copies += 1
    return copies


_WORD_CHAR = re.compile(r"[^\W_]")


def _hyphenated_count(text: str, page: str) -> int | None:
    """How many copies of `text` the page holds as whole words when each hyphen a line broke after, on the
    page or in `text`, may be read kept or dropped; None when no copy reads such a hyphen (the count is then
    the main one's to give).

    Each copy is counted once, read with or without its hyphen, and copies that overlap are counted as a scan
    from the start takes them, as the main count does: a page that writes the word once whole and once broken
    holds two copies, never three."""
    if not hyphenation.optional(text, page):
        return None
    copies = hyphenation.copies(text, page, lambda s, i: i > 0 and bool(_WORD_CHAR.match(s, i - 1)),
                                lambda s, j: bool(_WORD_CHAR.match(s, j)))
    if not any(c.continued for c in copies):
        return None
    ends: dict[int, int] = {}
    for c in copies:
        ends[c.end] = min(c.first, ends.get(c.end, c.first))
    n, taken = 0, 0
    for first, end in sorted((first, end) for end, first in ends.items()):
        if first >= taken:
            n, taken = n + 1, end
    return n


class PageNearEmpty(NamedTuple):
    max_chars: int


# Note: marks the text view writes for an element that holds nothing: the `$$` of an empty <math>, the
# number of an empty list item, the value of a hidden input.
_NOTHING = re.compile(
    r"<math\b[^<>]*>\s*</math>|<li\b[^<>]*>\s*</li>|<input\b[^<>]*\btype=[\"']?hidden\b[^<>]*>", re.I)


def page_near_empty(t: PageNearEmpty, v: views.Html) -> Mark:
    """A blank page yields at most `max_chars` characters a reader sees outside image alt text: no white
    space, no invisible format character (a zero-width space, a byte-order mark, a soft hyphen), and none of
    the marks the text view writes for an element that holds nothing."""
    seen = views.text(_NOTHING.sub("", v.html), alt=False)
    n = sum(unicodedata.category(c) != "Cf" for c in re.sub(r"\s", "", seen))
    return _mark(n <= t.max_chars, f"{n} non-space characters (limit {t.max_chars})")


# --------------------------------------------------------------------------- tables


class TableCell(NamedTuple):
    cell: str
    relations: dict[Literal["up", "down", "left", "right",
                            "top_heading", "left_heading", "right_heading"], str]
    max_diffs: int
    headings: tuple[str, ...] = ()      # the headings over its column, top to bottom
    section: str | None = None          # the section row nearest above it
    row_groups: tuple[str, ...] = ()    # the cells to its left that span its rows, left to right
    # {"empty": true} or {"end": true} on a side: nothing beside it, nothing in that direction
    shapes: dict[Literal["up", "down", "left", "right"], Literal["empty", "end"]] = {}


def table_cell(t: TableCell, v: views.Html) -> Mark:
    """Some table has a cell matching `cell` whose neighbours and headings match `relations`, and
    which sits under `headings`, in `section` and in `row_groups`. With `{"empty": true}` or `{"end": true}`
    on a side, every such cell (every cell that matches `cell` and holds the relations, headings, section and
    row groups, in every table) must have nothing beside it or past it, and must hold nothing but `cell`.

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
    def again(other: tables.Table) -> bool:
        """Whether a table holds the anchor cell too."""
        return any(_one_of(cell, x, thr, t.cell) for x in other.text.values())
    reasons: list[str] = []    # why a cell is not the anchor
    held: list[str] = []       # why an anchor has something beside it
    anchors = 0
    for i, table in enumerate(ts):
        for rc in [rc for rc, x in table.text.items() if _one_of(cell, x, thr, t.cell)]:
            failed = [why for k, want in expected.items()
                      if (why := _relation(table, rc, k, want, t.max_diffs, t.relations[k]))]
            failed += _structure(t, table, rc)
            if failed:
                reasons += failed
                continue
            if not t.shapes:
                return True, ""
            anchors += 1
            # a shape guard says nothing was invented beside the cell, so every such cell must hold it
            if not _one_of(cell, table.text[rc], thr, t.cell, lines=False):
                held.append(f"the cell holds more than {t.cell!r}: {_fold_cell(table.text[rc])!r}")
            held += [why for k, shape in t.shapes.items() if (why := _shape(ts, i, rc, k, shape, again))]
    if anchors and not held:
        return True, ""
    if not (reasons or held):
        return False, f"no cell matching {t.cell!r} in any table"
    return False, f"cells matching {t.cell!r} found, but: {'; '.join(held or reasons)}"


def _latex_found(latex: str, v: views.Html) -> Mark:
    """The equation is in the output's math, compared by what KaTeX renders (`equations`); or, for an
    equation plain text writes without loss (`plain`), its text reading is in the output's text, as a
    text test would find it."""
    from omni_parse_bench import equations

    ok, why = equations.appears(latex, v.html)
    # Note: "3σ" and "α = 0.05" are faithful transcriptions of $3\sigma$ and $\alpha = 0.05$, as a text
    # test already accepts $3\sigma$ for "3σ"; a fraction or a root written as text loses its structure.
    if ok or not plain(latex): return ok, why
    return (True, "") if equations.in_text(latex, v.html) else (False, why)


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
    # A transpose command inside a superscript has a faithful plain-text T spelling.
    def transpose(m: re.Match) -> str:
        return re.sub(r"\\(?:top|intercal)(?![A-Za-z])", "T", m.group())
    latex = re.sub(r"\^(?:\{[^{}]*\}|\\(?:top|intercal)(?![A-Za-z]))", transpose, latex)
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
    """The smallest block covering at least MIN_PLACE_COVER of the place's area, or None; of blocks of equal
    area (within a relative `AREA_EPS`), the first listed.

    Note: coverage of the place, not IoU, since a vendor's block may rightly be larger than our place (a list
    for an item), and the smallest is the most specific."""
    total = sum(_area(x) for x in place)
    if total <= 0: return None
    held = [b for b in blocks
            if sum(_area(_intersection(x, b.bbox)) for x in place) / total >= MIN_PLACE_COVER - COVER_EPS]
    best = None
    for b in held:
        if best is None or _area(b.bbox) < _area(best.bbox) * (1 - AREA_EPS): best = b
    return best


# --------------------------------------------------------------------------- format


class Format(NamedTuple):
    # Note: before and after are context only, None when the test gives none; the context (before + span +
    # after) is found exactly, so max_diffs is always 0 (a test's args carry it, and the loader refuses more);
    # marks is what every letter or digit of the span must carry (and the ones next to it must not), absent
    # what none of them may.
    before: str | None
    span: str
    after: str | None
    max_diffs: int
    marks: tuple[str, ...]
    absent: tuple[str, ...]


def format_mark(p: Format, v: views.Html) -> Mark:
    """Whether the span carries the marks the page prints on it (`marks`), and not the words around it, or
    none of the marks in `absent`. Reads the output's markup (`marks.read`), never the text view. See
    docs/scoring/format.md."""
    return marks.check(marks.read(v.html), p.before or "", p.span, p.after or "", p.marks, p.absent)


# --------------------------------------------------------------------------- registry

Runner = Callable[[Any, Any], Mark]

TYPES: dict[str, tuple[type, Runner]] = {
    "present": (Present, present),
    "order": (Order, order),
    "repeat": (Repeat, repeat),
    "page_near_empty": (PageNearEmpty, page_near_empty),
    "table_cell": (TableCell, table_cell),
    "layout_kind": (LayoutKind, layout_kind),
    "format": (Format, format_mark),
}


# What a test type's parameters must satisfy beyond their types, checked when a test is loaded.
VALID: dict[str, tuple[Callable[[Any], bool], str]] = {
    "present": (lambda t: not isinstance(t.content, Number) or number(t.content.number) is not None,
                "a number must read as one number, e.g. 1,240.00 or -4.8%"),
    "repeat": (lambda t: t.expected_count > 0, "expected_count must be a positive whole number"),
    "page_near_empty": (lambda t: t.max_chars >= 0, "max_chars must be a whole number, 0 or more"),
    "format": (lambda t: t.max_diffs == 0 and marks.letters(t.span) > 0 and bool(t.marks) != bool(t.absent)
               and len(set(t.marks)) == len(t.marks) and len(set(t.absent)) == len(t.absent)
               and not (set(t.marks) | set(t.absent)) - set(marks.KINDS)
               and not {"sup", "sub"} <= set(t.marks)
               and (marks.letters(t.span) >= 3 or marks.letters((t.before or "") + (t.after or "")) > 0),
               "a format test has no edit budget (max_diffs 0), a span with a letter or digit, exactly one "
               "of "
               f"marks and absent, distinct kinds of {marks.KINDS} (a span is not both superscript and "
               "subscript), and a context with a letter or digit when its span has fewer than 3"),
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
    thousands mark after a ",", and a decimal point after a "." ("8.455"). One "," followed by one or
    two digits is ambiguous: "16,17" may be two numbers. Parentheses aren't a sign.
    """
    m = _NUMBER.match(text.strip())
    if not m: return None
    core = m["body"].replace(" ", "").replace("\u202f", "")
    seps = [i for i, ch in enumerate(core) if ch in ".,"]
    if len(seps) == 1:
        i = seps[0]
        whole, frac = core[:i], core[i + 1:]
        if core[i] == "," and len(frac) == 3 and whole != "0":
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


def _number_pattern(written: str) -> re.Pattern[str]:
    """The number anywhere in a text, its digits and separators as `written` ("1,240" is not in "1240",
    "1 240" nor "1.240"; a space of any width is a space).

    A number starts after anything but a digit or a digit's separator, so "No.12345" holds 12345, and
    ends before anything but a digit or a separator and a digit, so "12.5" is not in "12.5.7" nor
    "12.5,3", but is in "12.5. Next"; a "-" is its sign only after a non-word character, so "E-4065"
    and "COVID-19" are positive."""
    return re.compile(r"(?<!\d)(?<!\d[.,])(?P<pre>(?<!\w)-(?=[\d$€£¥])|\(\s?)?(?:[$€£¥]\s?)?"
                      + re.escape(written.translate(_NUM_CLEAN)) + r"(?![.,]\d)(?P<pct>\s?%)?\)?(?![\d])")


# --------------------------------------------------------------------------- helpers


def _mark(passed: bool, why: str) -> Mark:
    """`why` is kept only when the test fails."""
    return passed, "" if passed else why


def _ratio(needle: str, hay: str, max_diffs: int) -> tuple[bool, float, float]:
    """Fuzzy containment: passes when some substring of `hay` is within `max_diffs` edits of `needle`, an edit
    being a character substituted, inserted or deleted, or two adjacent characters swapped (`_edits`).
    Returns the verdict, the best match's ratio, and the threshold `1 - max_diffs / len(needle)`.

    Note: rapidfuzz's partial ratio is the first pass, and with no edit to spend the only one (it is 1 only
    for an exact copy). Its windows have the needle's length, so it scores a substring k edits off at 1 - k/n
    or better, and a `hay` at least as long as `needle` that it fails is more than `max_diffs` edits off. It
    forgives more than that (an inserted letter, a letter moved a few places, a text cut at an edge of
    `hay`), so a fuzzy pass is confirmed by the edit count, and the ratio is then
    `1 - edits / len(needle)`."""
    if not needle:
        return False, 0.0, 1.0
    thr = 1.0 - max_diffs / len(needle)
    r = _partial(needle, hay)
    if not max_diffs or needle in hay or (r < thr - EPS and len(hay) >= len(needle)):
        return r >= thr - EPS, r, thr
    d = _edits(needle, hay, max_diffs)
    return d <= max_diffs, 1.0 - d / len(needle), thr


def _edits(needle: str, hay: str, max_diffs: int) -> int:
    """The fewest edits that turn `needle` into some substring of `hay` (the empty one too), an edit being a
    character substituted, inserted or deleted, or two adjacent characters swapped: the optimal string
    alignment distance (restricted Damerau-Levenshtein), where no character is edited twice.

    Note: a match within `max_diffs` edits keeps one of `2 * max_diffs + 1` pieces of `needle` intact
    (an edit touches at most two), so only the stretches of `hay` around an exact copy of a piece are scanned
    first; the whole of `hay` is scanned when they find none, or would not be shorter (`_edits_scan`)."""
    n, k = len(needle), max_diffs
    count = 2 * k + 1
    step = n // count
    if step >= 3:
        spans = []
        for i in range(count):
            o = i * step
            piece = needle[o:n if i == count - 1 else o + step]
            p = hay.find(piece)
            while p != -1:
                spans.append((max(0, p - o - k), p - o + n + 2 * k))
                if len(spans) > len(hay) // step:    # so many stretches that a whole-page scan is cheaper
                    return _edits_scan(needle, hay)
                p = hay.find(piece, p + 1)
        spans.sort()
        merged: list[list[int]] = []
        for a, b in spans:
            if merged and a <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        if sum(b - a for a, b in merged) < len(hay):
            d = min((_edits_scan(needle, hay[a:b]) for a, b in merged), default=n)
            if d <= k:
                return d
    return _edits_scan(needle, hay)


def _edits_scan(needle: str, hay: str) -> int:
    """`_edits` by one pass over the whole of `hay`: Hyyrö's bit-parallel form of Myers' algorithm, with the
    transposition term, in its search form (a match may start anywhere in `hay`). One bit per character of
    `needle`."""
    m = len(needle)
    full, top = (1 << m) - 1, 1 << (m - 1)
    peq: dict[str, int] = {}
    for i, c in enumerate(needle):
        peq[c] = peq.get(c, 0) | 1 << i
    vp, vn, d0, prev = full, 0, 0, 0
    score = best = m
    for c in hay:
        eq = peq.get(c, 0)
        tr = (((~d0) & eq) << 1) & prev
        d0 = ((((eq & vp) + vp) ^ vp) | eq | vn | tr) & full
        hp = (vn | ~(d0 | vp)) & full
        hn = d0 & vp
        if hp & top:
            score += 1
        elif hn & top:
            score -= 1
        x = (hp << 1) & full
        vn = x & d0
        vp = ((hn << 1) | ~(x | d0)) & full
        prev = eq
        if score < best:
            best = score
    return best


def _partial(needle: str, hay: str) -> float:
    """How well `needle` matches its best window of `hay`, from 0 to 1.

    Note: rapidfuzz's partial_ratio slides the shorter string over the longer, so when `hay` is the shorter,
    the whole of each is compared instead."""
    return (fuzz.partial_ratio(needle, hay) if len(hay) >= len(needle) else fuzz.ratio(needle, hay)) / 100.0


def _window(needle: str, hay: str) -> tuple[float, str]:
    """`_partial`'s score and the window of `hay` it came from (all of `hay` when it is the shorter). Kept
    apart from `_partial`, which runs on every test, so only a failure pays for the alignment."""
    if len(hay) < len(needle):
        return fuzz.ratio(needle, hay) / 100.0, hay
    a = fuzz.partial_ratio_alignment(needle, hay)
    return a.score / 100.0, hay[a.dest_start:a.dest_end]


def _excerpt(window: str, n: int = 120) -> str:
    return window if len(window) <= n else window[:n - 1] + "…"


def contains(needle: str, text: str, max_diffs: int) -> tuple[bool, float, float]:
    """Whether `needle` appears in `text`, with the best match ratio and the threshold: `_ratio`
    after `fold`, then again after `squeeze` for words the text layer glues together."""
    return _contains(needle, text, max_diffs)[:3]


def _folded_span(i: int, j: int, kept: list[int] | None) -> tuple[int, int]:
    """Span [i, j) of the squeezed text as a span of the folded text; `kept`: its non-space indices."""
    return (i, j) if kept is None else (kept[i], kept[j - 1] + 1)


def _unglued(matches: list, folded: str, kept: list[int] | None) -> list:
    """The matches but exact ones cut out of a longer number in `folded` (`kept`: see `_edges_ok`)."""
    return [m for m in matches
            if m.dist or m.end <= m.start or not _glued(folded, *_folded_span(m.start, m.end, kept))]


def _glued(hay: str, i: int, j: int) -> bool:
    """Whether the span hay[i:j] is cut out of a longer number: a leading digit glued to a digit, a sign or
    a separator after a digit, a trailing digit glued to a digit or to a separator before one. A hyphen
    after a letter or digit is a hyphen, not a sign."""
    return j > i and (_cut_before(hay, i) or _cut_after(hay, j))


def _cut_before(hay: str, i: int) -> bool:
    """`_glued`'s leading edge, for a match starting at i."""
    before = hay[i - 1:i]
    return hay[i].isdigit() and bool(before) and (
        before.isdigit()
        or (before in ".," and hay[i - 2:i - 1].isdigit())
        or (before in "-\u2212+" and not hay[i - 2:i - 1].isalnum()))


def _cut_after(hay: str, j: int) -> bool:
    """`_glued`'s trailing edge, for a match ending before j."""
    after = hay[j:j + 1]
    return hay[j - 1].isdigit() and bool(after) and (
        after.isdigit() or (after in ".," and hay[j + 1:j + 2].isdigit()))


def _edges_ok(want: str, hay: str, folded: str = "", kept: list[int] | None = None) -> bool:
    """Whether some occurrence of `want` in `hay` is not cut out of a longer number (`_glued`). For a
    squeezed `hay`, pass the `folded` text and its non-space indices `kept`, to judge the edges there."""
    i = hay.find(want)
    while i != -1:
        if not _glued(folded or hay, *_folded_span(i, i + len(want), kept)):
            return True
        i = hay.find(want, i + 1)
    return False


def _near(want: str, hay: str, max_diffs: int) -> list:
    """`want`'s matches in `hay` within `max_diffs` edits: every exact copy, and the best matches of each
    run of overlapping ones at each budget from 1 to `max_diffs`, so a larger budget keeps every match a
    smaller one found.

    Note: with an edit to spend, fuzzysearch keeps one match per run of overlapping ones, and a larger budget
    makes longer runs: an exact copy overlapping another match ("a a" in "a a a a"), or a match one budget
    found, would lose its start to a match that spends more edits.
    Note: fuzzysearch picks that one match as the min of a set by (edits, -length); on a tie the pick
    followed set order, i.e. the string hash, so a verdict changed with PYTHONHASHSEED. Every match tied
    for best in its run is kept instead, which no hash order can change."""
    if not max_diffs or not want: return fuzzysearch.find_near_matches(want, hay, max_l_dist=max_diffs)
    found: dict[tuple[int, int], fuzzysearch.Match] = {}
    for k in range(1, max_diffs + 1):
        for run in group_matches(find_near_matches_levenshtein(want, hay, k)):
            best = min((m.dist, m.start - m.end) for m in run)
            for m in run:
                if (m.dist, m.start - m.end) == best: found.setdefault((m.start, m.end), m)
    for i in (m.start() for m in re.finditer(f"(?={re.escape(want)})", hay)):
        found[i, i + len(want)] = fuzzysearch.Match(i, i + len(want), 0, want)
    return sorted(found.values())


def _unglue(want: str, hay: str, folded: str = "", kept: list[int] | None = None) -> str:
    """`hay` with each exact copy of `want` cut out of a longer number (`_glued`) blanked out, so no window of
    a rejected copy matches while a fuzzy match elsewhere still can (`kept`: see `_edges_ok`)."""
    out = list(hay)
    for m in re.finditer(f"(?={re.escape(want)})", hay):
        i = m.start()
        if _glued(folded or hay, *_folded_span(i, i + len(want), kept)):
            out[i:i + len(want)] = "\0" * len(want)
    return "".join(out)


def _why_missing(cut: bool) -> str:
    return "found only inside a longer number" if cut else "not found"


def _only_glued(needle: str, text: str, fold: Callable[[str], str] = normalize.fold) -> bool:
    """Whether `needle` is in `text` exactly but only cut out of a longer number (`_contains` fails it
    on its edges): as `_contains` judges it, in the folded text, else in the squeezed. `fold` is the fold
    the test compares with (`normalize.fold_cased` for an `exact_case` arg)."""
    want, hay = fold(needle), fold(text)
    if not want: return False
    if want in hay: return not _edges_ok(want, hay)
    squeezed = want.replace(" ", ""), hay.replace(" ", "")
    return squeezed[0] in squeezed[1] and not _squeezed_ok(*squeezed, hay)


def _squeezed_ok(want: str, hay: str, folded: str) -> bool:
    """Whether a squeezed match stands: an exact one must not be cut out of a longer number in `folded`
    (a space is not glued); a fuzzy one is not checked."""
    if want not in hay:
        return True
    return _edges_ok(want, hay, folded, [k for k, c in enumerate(folded) if c != " "])


def _contains(needle: str, text: str, max_diffs: int, fold_page: Callable[[str], str] = normalize.fold,
              fold_needle: Callable[[str], str] = normalize.fold) -> tuple[bool, float, float, str]:
    """`contains`, and, when it fails, the best-matching window of the folded text (the squeezed, if that
    matched better): lowercased (case kept under `fold_cased`), its spacing folded; "" when it passes or
    `needle` is empty. `fold_page` folds `text` (`normalize.unmarked` drops its footnote markers)."""
    want, hay = fold_needle(needle), fold_page(text)
    ok, r, thr = _ratio(want, hay, max_diffs)
    if ok and want and want in hay and not _edges_ok(want, hay):
        # Note: a copy cut out of a longer number does not count, nor any window of it ("total: 40" spends
        # its edit on "otal: 400"); a fuzzy match elsewhere still does, as one clean copy anywhere would.
        # The squeezed text is tried next: a spaced copy elsewhere ("400 4 0" holds "4 0") is a copy too.
        ok = _ratio(want, _unglue(want, hay), max_diffs)[0]
    if ok:
        return True, r, thr, ""
    # fold has already collapsed all whitespace to ASCII spaces; reuse it for squeeze.
    squeezed = want.replace(" ", ""), hay.replace(" ", "")
    ok, r2, _ = _ratio(*squeezed, max_diffs)
    if ok and want and not _squeezed_ok(*squeezed, hay):
        kept = [k for k, c in enumerate(hay) if c != " "]
        ok = _ratio(squeezed[0], _unglue(*squeezed, hay, kept), max_diffs)[0]
    window = "" if ok or not want else _window(*(squeezed if r2 > r else (want, hay)))[1]
    return ok, max(r, r2), thr, window


# Note: `_tokens` writes a number as one character from plane 15's private use area. Fold keeps those (it
# drops only the BMP's), so it first replaces any the text holds; `_within` reads a character from
# `_NUMBER_CHAR` up as a number.
_NUMBER_CHAR = "\U000F0000"
_PLANE_15_16 = re.compile("[\U000F0000-\U0010FFFF]")


def _tokens(want: str, hay: str) -> tuple[str, str] | None:
    """`want` and `hay` with each maximal run of digits (`str.isdigit`) made one character: a private-use
    code point of its own for each distinct run of `want`, and one shared by every run of `hay` that `want`
    lacks (no edit may touch a number, so those never need telling apart). None when a number of `want`
    is missing from `hay`, which no stretch can then match."""
    codes: dict[str, str] = {}

    def encode(s: str, gold: bool) -> str:
        out = []
        for digits, run in itertools.groupby(_PLANE_15_16.sub("\ufffd", s), str.isdigit):
            run = "".join(run)
            if digits and gold:
                codes.setdefault(run, chr(ord(_NUMBER_CHAR) + 1 + len(codes)))
            out.append(codes.get(run, _NUMBER_CHAR) if digits else run)
        return "".join(out)

    want = encode(want, True)
    hay = encode(hay, False)
    return None if any(c not in hay for c in codes.values()) else (want, hay)


def _numbers_kept(needle: str, text: str, max_diffs: int, fold_page: Callable[[str], str] = normalize.fold,
                  fold_needle: Callable[[str], str] = normalize.fold) -> bool:
    """Whether some stretch of the folded `text` is within `max_diffs` edits of the folded `needle` with every
    number (a maximal run of digits) kept whole and exact: as `_contains` counts edits, but an edit that
    changes, adds or drops a number costs more than the budget (`_within`). Tried on the folded strings,
    then on the squeezed ones, squeezed after the numbers are made one character each, so a squeeze never
    joins two numbers. An exact copy cut out of a longer number, in either, is blanked out first (`_unglue`),
    as `_contains` does, so the rule and `_contains` never pass on two different stretches of one glued
    copy and one other."""
    want, hay = fold_needle(needle), fold_page(text)
    if not want.replace(" ", ""):
        return False
    encoded = _tokens(want, _unglued_both(want, hay))
    if encoded is None:
        return False
    want, hay = encoded
    return (_within(want, hay, max_diffs)
            or _within(want.replace(" ", ""), hay.replace(" ", ""), max_diffs))


def _unglued_both(want: str, hay: str) -> str:
    """`hay` with each exact copy of `want` cut out of a longer number blanked out, in it and in its squeezed
    form (`_unglue`), the squeezed copies blanked at their places in `hay`."""
    kept = [i for i, c in enumerate(hay) if c != " "]
    blanked = list(_unglue(want, hay))
    for i, c in enumerate(_unglue(want.replace(" ", ""), hay.replace(" ", ""), hay, kept)):
        if c == "\0":
            blanked[kept[i]] = "\0"
    return "".join(blanked)


def _within(want: str, hay: str, k: int) -> bool:
    """Whether at most k edits turn `want` into some stretch of `hay`, both encoded by `_tokens`. An edit is
    a character substituted, inserted or deleted, or two adjacent ones swapped (as `_edits` counts), and
    costs 1, except one that touches a number character, which costs k + 1; a number matched to the same
    number costs 0. A stretch starts and ends anywhere in `hay`, so never inside a number (one character).

    Note: a dynamic program over `hay` one column at a time, each column a list of the costs of matching each
    prefix of `want` ending there, cut after its last row within k (Ukkonen's cutoff): a row beyond holds
    more than k, and a cost above k is stored as k + 1. Time O(len(hay) * rows within k); memory
    O(len(want))."""
    over = k + 1

    def number(c: str) -> bool:
        return c >= _NUMBER_CHAR

    drop = [over if number(c) else 1 for c in want]
    col = [0]
    for d in drop:      # the empty stretch: every character of `want` deleted
        if col[-1] + d > k:
            break
        col.append(col[-1] + d)
    if len(col) > len(want):
        return True
    before: list[int] = []
    for j, h in enumerate(hay):
        add = over if number(h) else 1
        last = max(len(col), len(before) + 1)     # no row from here on can come within k from a column before
        cur = [0]
        for i in range(1, len(want) + 1):
            g = want[i - 1]
            best = cur[i - 1] + drop[i - 1]
            if i - 1 < len(col):
                best = min(best, col[i - 1] + (0 if g == h else over if number(g) or number(h) else 1))
            if i < len(col):
                best = min(best, col[i] + add)
            if (i >= 2 and i - 2 < len(before) and g == hay[j - 1] and want[i - 2] == h and g != h
                    and not number(g) and not number(h)):
                best = min(best, before[i - 2] + 1)
            if best > k and i >= last:
                break
            cur.append(min(best, over))
        while cur[-1] > k:
            cur.pop()
        if len(cur) > len(want):
            return True
        before, col = col, cur
    return False


def _fold_cell(s: str) -> str:
    return normalize.fold(s)


def _cell_threshold(cell: str, max_diffs: int) -> float:
    return max(TABLE_MIN_RATIO, 1.0 - max_diffs / max(1, len(cell)))


def _cell_ratio(a: str, b: str) -> float:
    """How alike two folded cells are, also with their spaces removed ("1: 1" and "1:1")."""
    return max(fuzz.ratio(a, b), fuzz.ratio(a.replace(" ", ""), b.replace(" ", ""))) / 100.0


def _relation(table: tables.Table, rc: tables.Cell, kind: str, want: str, max_diffs: int,
              raw: str = "") -> str:
    """Why the cell at `rc` fails one relation, or "" when it holds. `raw` is the gold as written, for the
    hyphen fallback (`_hyphenated_cell`)."""
    thr = _cell_threshold(want, max_diffs)
    if kind.endswith("_heading"):
        walk = {"top_heading": "up", "left_heading": "left", "right_heading": "right"}
        cells = tables.heading(table, rc, walk[kind])
    else:
        # Note: an empty neighbour stands for the value written over it, above for left and right,
        # beside for up and down: a value over empty cells spans them.
        over = "up" if kind in ("left", "right") else "left"
        cells = {_stand_in(table, c, over) for c in getattr(table, kind)[rc]}
    texts = [_fold_cell(table.text[c]) for c in cells]
    if any(_cell_ratio(want, x) >= thr - EPS for x in texts):
        return ""
    if raw and any(_hyphenated_cell(raw, table.text[c]) for c in cells):
        return ""
    if not texts:
        return f"no {kind} cell"
    best = max(texts, key=lambda x: _cell_ratio(want, x))
    return f"{kind} {best!r} doesn't match {want!r} ({_cell_ratio(want, best):.2f})"


def _blank(table: tables.Table, c: tables.Cell | None) -> bool:
    """Whether a slot shows nothing: no cell (a short row's missing `<td>`), or a cell with no figure whose
    folded text is empty (`&nbsp;`, `<br>`, invisible characters and leaders fold away). An image draws
    something, with an alt text or without."""
    return c is None or (c not in table.figures and not _fold_cell(table.text[c]).strip())


def _slots(table: tables.Table, rc: tables.Cell, kind: str) -> list[tables.Cell | None] | None:
    """The cells (None for a short row's missing one) in the slots touching one side of the cell at `rc`, read
    raw; None when that side is past the table's edge."""
    rows, cols = table.covers[rc]
    dr, dc = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}[kind]
    r0, c0 = (min(rows) if dr < 0 else max(rows)) + dr, (min(cols) if dc < 0 else max(cols)) + dc
    slots = [(r0, c) for c in cols] if dr else [(r, c0) for r in rows]
    if not all(0 <= r < len(table.grid) and 0 <= c < len(table.grid[0]) for r, c in slots):
        return None
    return [table.grid[r][c] for r, c in slots]


def _shape(ts: tuple[tables.Table, ...], i: int, rc: tables.Cell, kind: str, shape: str,
           again: Callable[[tables.Table], bool] = lambda _: False) -> str:
    """Why the cell at `rc` of table `ts[i]` fails `{"empty": true}` or `{"end": true}` on one side, or ""
    when it holds.

    `empty`: every slot touching that side of the cell is blank, read raw (no stand-in, unlike a text arg:
    a copy of the value above or beside must not pass); a missing trailing cell counts as blank, the table's
    edge does not (`no right cell`). `end`: no cell in any row below (any column to the right, ...) has
    text, in the table or in a table that continues it (`_continues`)."""
    table = ts[i]
    rows, cols = table.covers[rc]
    dr, dc = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}[kind]
    height, width = len(table.grid), len(table.grid[0])
    if shape == "empty":
        if (slots := _slots(table, rc, kind)) is None:
            return f"no {kind} cell"
        for x in slots:
            if not _blank(table, x):
                return f"{kind} {_fold_cell(table.text[x]) or 'an image'!r} isn't empty"
        return ""
    if dr:
        lines = range(max(rows) + 1, height) if dr > 0 else range(min(rows) - 1, -1, -1)
        found = [(r, [x for x in dict.fromkeys(table.grid[r]) if not _blank(table, x)]) for r in lines]
        word = "row"
    else:
        lines = range(max(cols) + 1, width) if dc > 0 else range(min(cols) - 1, -1, -1)
        found = [(c, [x for x in dict.fromkeys(row[c] for row in table.grid) if not _blank(table, x)])
                 for c in lines]
        word = "column"
    for n, cells in found:
        if cells:
            held = ", ".join(repr(_fold_cell(table.text[x]) or "an image") for x in cells[:3])
            return f"{kind}: {word} {n + 1} holds {held}{', ...' if len(cells) > 3 else ''}"
    for other in _continuations(ts, i, kind, again):
        for row in other.grid:
            if cells := [x for x in dict.fromkeys(row) if not _blank(other, x)]:
                held = ", ".join(repr(_fold_cell(other.text[x]) or "an image") for x in cells[:3])
                return f"{kind}: a table continuing this one holds {held}{', ...' if len(cells) > 3 else ''}"
    return ""


def _continuations(ts: tuple[tables.Table, ...], i: int, kind: str,
                   again: Callable[[tables.Table], bool]) -> list[tables.Table]:
    """The tables that go on from `ts[i]` past the side `kind`: a table written right after it
    (`Table.follower`) that has as many columns (`down`) or rows (`right`) and no heading, and does not hold
    the anchor again (then it is a copy, judged as the anchor's table is). One written right before it, with
    this table as the continuation, serves `up` and `left`. A continuation may be continued."""
    out: list[tables.Table] = []
    if kind in ("down", "right"):
        cur = ts[i]
        while cur.follower is not None and _goes_on(cur, nxt := ts[cur.follower], kind) and not again(nxt):
            out.append(nxt)
            cur = nxt
    else:
        before = {t.follower: k for k, t in enumerate(ts) if t.follower is not None}
        cur, k = ts[i], i
        while ((j := before.get(k)) is not None and _goes_on(ts[j], cur, "down" if kind == "up" else "right")
               and not again(ts[j])):
            out.append(ts[j])
            cur, k = ts[j], j
    return out


def _goes_on(a: tables.Table, b: tables.Table, kind: str) -> bool:
    """Whether `b`, written right after `a`, goes on from it below (`down`, as many columns) or to its right
    (as many rows), with no heading of its own. A table that prints its header again is not told from a
    second table of the same shape, so it is read as one."""
    same = len(a.grid[0]) == len(b.grid[0]) if kind == "down" else len(a.grid) == len(b.grid)
    return same and not b.headings


def _one_of(want: str, got: str, thr: float, raw: str = "", lines: bool = True) -> bool:
    """Whether cell text `got`, or one of its lines (unless `lines` is False), matches the folded `want`; or,
    given `raw` (the gold as written), is it with a hyphen a line broke after read kept or dropped
    (`_hyphenated_cell`)."""
    parts = [x for x in {got, *(got.split("\n") if lines else ())} if x.strip()]
    return (any(_cell_ratio(want, _fold_cell(x)) >= thr - EPS for x in parts)
            or bool(raw) and any(_hyphenated_cell(raw, x) for x in parts))


# A hyphen (or a form NFKC makes one) with white space after it, perhaps past marks: a cell without one, on
# either side, has no hyphen a line broke after, so the fallback is not tried.
_MAY_WRAP = re.compile(r"[-\u2010\u2011\ufe63\uff0d]\W*?\s")


def _hyphenated_cell(raw: str, got: str) -> bool:
    """Whether the gold `raw` is the whole cell text `got` when a hyphen a line broke after, in either, is
    read kept or dropped, as `present` reads one (`hyphenation.matches`): exactly, spending no edits."""
    if not (_MAY_WRAP.search(raw) or _MAY_WRAP.search(got)):
        return False
    return hyphenation.matches(raw, got, lambda s, i: i > 0, lambda s, j: j < len(s))


def _in_order(want: Sequence[str], got: Sequence[str], max_diffs: int) -> bool:
    """Whether `want` appears in `got` in order, others between allowed; one cell of `got` may hold
    several consecutive items of `want` joined. A cell may also match through the hyphen fallback, but only
    when the plain reading fails: a cell that takes several items through a broken hyphen must not leave an
    item to a later cell that the plain reading would have matched."""
    return _greedy(want, got, max_diffs, False) or _greedy(want, got, max_diffs, True)


def _greedy(want: Sequence[str], got: Sequence[str], max_diffs: int, wrapped: bool) -> bool:
    i = 0
    for g in got:
        for n in range(len(want) - i, 0, -1):
            raw = " ".join(want[i:i + n])
            joined = _fold_cell(raw)
            if _one_of(joined, g, _cell_threshold(joined, max_diffs), raw if wrapped else ""):
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
        # Note: a row that writes the test's section in every cell is that section row written without a
        # merge, in a second reading (the first still passes what it passed); another repeated row
        # (`Yes Yes`) is data. So a test that names `Yes` passes on a `Yes | Yes` row, which tests do not:
        # they name section labels.
        runs = [run, tables.section(table, rc, repeated=lambda x: _one_of(want, x, thr, t.section))]
        groups = [table.text[c] for c in tables.beside(table, rc) if tables.spanning_rows(table, c)]
        # Note: a section label printed on its own line above its row may fairly be written as that row's
        # first cell instead ("ADH-I intron 5 | 851 (703) | 306"): a long label set on a line of its own
        # still names the row below it.
        first = next((c for c in table.grid[min(table.covers[rc][0])] if c is not None), None)
        groups += [table.text[first]] if first is not None and first != rc else []
        in_run = any(_one_of(want, " ".join(r[i:]), thr, t.section) for r in runs for i in range(len(r)))
        if not in_run and not any(_one_of(want, g, thr, t.section) for g in groups):
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
