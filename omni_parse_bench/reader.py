"""The reader: an output's HTML as a document D of blocks, lines and tokens, and a gold string as tokens.

    read(h)           HTML -> `Document`: the visible text only, in blocks and lines, each line tokens
    tokenize(s)       a plain string (a test's gold) -> tokens, by the same rules
    visible_html(h)   the HTML with the text a page hides (and image alt text) taken out, still HTML

One HTML5 parser (html5lib, the WHATWG algorithm, scripting on) reads every output, so malformed HTML has one
reading. Text the page hides is not read; what a reader draws on screen is: `aria-hidden` text is kept.

    dropped    <script> <style> <template> <noscript> <head> <title>, comments, <input type=hidden>, elements
               with the `hidden` attribute or an inline style `display:none` / `visibility:hidden`, and
               everything inside them
    alt text   is not text; a figure contributes its caption
    cells      a table cell is its own block, tagged (table, row, column); a window never crosses one

This is the Id reading: the Text fold (compatibility forms, typography) is a later stage between the
quantity scan and word tokenization, so a Word here is not yet a Text token.

Tokens (classes below) are fixed for an output: no later step splits or joins one. Text is cut into grapheme
clusters (UAX #29, at the Unicode version of the pinned `regex`), and each cluster takes its script's class:
spaced scripts make a `Word` of a run; Han, kana, Hangul and the phrase-spaced scripts make one `Word` per
cluster. A quantity (`Qty`) is read once, on the raw characters, before any fold.

A rule of the reader that changes what the scorer decides is a switch (`switches.py`): visibility,
alt_text_out, cell_windows, sup_exponent, tokens. The reader reads the switches as they stand, unless it is
given `rules`.
"""

from __future__ import annotations

import functools
import re
import unicodedata
from dataclasses import dataclass, field
from collections.abc import Iterable, Iterator

import html5lib
import regex

from . import switches
from .views import MalformedOutput

# ------------------------------------------------------------------------------------------ token classes

WORD, QTY, SYM, SPACE, BREAK, MARK, WRAP, MATH = (
    "Word",
    "Qty",
    "Sym",
    "Space",
    "Break",
    "Mark",
    "Wrap",
    "Math",
)
CLASSES = (WORD, QTY, SYM, SPACE, BREAK, MARK, WRAP, MATH)
CONTENT = frozenset(
    {WORD, QTY, SYM, MATH}
)  # the tokens a candidate is identified by: not Mark, Space, Break, Wrap

# The four script classes of section 8 of the design, for a letter's cluster.
SPACED, HANGUL, CHARACTER, PHRASE = "spaced", "hangul", "character", "phrase"

RULES = ("visibility", "alt_text_out", "cell_windows", "sup_exponent", "tokens", "text_fold")


@dataclass(frozen=True, slots=True)
class Token:
    cls: str  # one of CLASSES
    text: str  # as written (a `Wrap` is "-" and its line break "\n")
    canon: str  # a Qty's spelling with its exponent as `^`, width and minus variants folded; else `text`
    block: int  # index of the block in the document (-1 for a gold string)
    line: int  # index of the line within the document (-1 for a gold string)
    start: int  # offsets of `text` in `Document.text`
    end: int
    markup: frozenset[str]  # inline formatting every character of it carries (`b`, `i`, `sup`, ...)
    cell: tuple[int, int, int] | None = None  # (table, row, column) of the cell it sits in
    script: str = ""  # a Word of one cluster in an unsegmented script: its class


@dataclass(frozen=True, slots=True)
class Block:
    kind: str  # p, heading, li, cell, caption, pre, math, text
    cell: tuple[int, int, int] | None
    first: int  # index into `Document.tokens` of its first token
    last: int  # one past its last


@dataclass(slots=True)
class Document:
    tokens: list[Token] = field(default_factory=list)
    blocks: list[Block] = field(default_factory=list)
    text: str = ""  # every token's text, in order; `Break` is "\n"

    def content(self) -> list[Token]:
        return [t for t in self.tokens if t.cls in CONTENT]

    def visible_characters(self) -> int:
        """The number of characters the page shows: every token's text but the breaks."""
        return sum(len(t.text) for t in self.tokens if t.cls != BREAK)

    def crosses_cell(self, i: int, j: int) -> bool:
        """Whether the window of tokens `i..j` (inclusive) holds content of two different cells, or of a
        cell and of text outside every cell. With `cell_windows` off nothing crosses."""
        return crosses_cell(self.tokens, i, j)


def crosses_cell(tokens: list[Token], i: int, j: int, *, rules: Iterable[str] | None = None) -> bool:
    if "cell_windows" not in _rules(rules):
        return False
    seen = {t.cell for t in tokens[i : j + 1] if t.cls in CONTENT}
    return len(seen) > 1


def _rules(rules: Iterable[str] | None) -> frozenset[str]:
    if rules is None:
        return frozenset(r for r in RULES if switches.on(r))
    rules = frozenset(rules)
    if unknown := rules - set(RULES):
        raise KeyError(f"unknown rule {sorted(unknown)}; known: {RULES}")
    return rules


# ------------------------------------------------------------------------------------------------- scripts

_HAN = regex.compile(r"\p{Script=Han}")
_KANA = regex.compile(r"[\p{Script=Hiragana}\p{Script=Katakana}ーｰ]")
_HANGUL = regex.compile(r"\p{Script=Hangul}")
_PHRASE = regex.compile(
    r"[\p{Script=Thai}\p{Script=Lao}\p{Script=Khmer}\p{Script=Myanmar}\p{Script=Tibetan}]"
)
_CLUSTER = regex.compile(r"\X")


@functools.lru_cache(maxsize=4096)
def script_class(ch: str) -> str:
    """The class of the script of a letter (the base of a cluster): `spaced`, `hangul`, `character` (Han and
    kana) or `phrase`. Combining marks, ZWJ and ZWNJ take the class of their base, so callers pass
    the base."""
    if _HAN.match(ch) or _KANA.match(ch):
        return CHARACTER
    if _HANGUL.match(ch):
        return HANGUL
    if _PHRASE.match(ch):
        return PHRASE
    return SPACED


def _is_letter(ch: str) -> bool:
    return unicodedata.category(ch)[0] == "L"


def _is_mark(ch: str) -> bool:
    return unicodedata.category(ch)[0] == "M"


def _is_digit(ch: str) -> bool:
    return unicodedata.category(ch) == "Nd"


def _digit_zero(ch: str) -> int:
    """The code point of the zero of the digit's own run of ten (so two digits are of one script when these
    agree); full-width digits count as ASCII."""
    z = ord(ch) - unicodedata.digit(ch)
    return 0x30 if z == 0xFF10 else z


def _glues(ch: str) -> bool:
    """Whether the character glues to a neighbouring number when it is a spaced script's letter, a digit or a
    combining mark: the characters of a run that makes a Word of `x123y`."""
    return _is_digit(ch) or _is_mark(ch) or (_is_letter(ch) and script_class(ch) == SPACED)


# ---------------------------------------------------------------------------------------------- quantities

# Note: the suffixes a number may carry glued to its digits (no space): a published table. SI base units with
# every SI prefix, common units, and magnitudes. Letters glued to digits that are not in it make the whole run
# a `Word` (`5pm`, `A4`, `10kgs`).
_SI_UNITS = (
    "m",
    "g",
    "s",
    "A",
    "K",
    "mol",
    "cd",
    "Hz",
    "N",
    "Pa",
    "J",
    "W",
    "C",
    "V",
    "F",
    "Ω",
    "S",
    "Wb",
    "T",
    "H",
    "lm",
    "lx",
    "Bq",
    "Gy",
    "Sv",
    "L",
    "l",
    "B",
    "b",
    "bit",
    "Wh",
    "eV",
    "bar",
)
_SI_PREFIXES = (
    "",
    "Y",
    "Z",
    "E",
    "P",
    "T",
    "G",
    "M",
    "k",
    "h",
    "da",
    "d",
    "c",
    "m",
    "µ",
    "μ",
    "n",
    "p",
    "f",
    "a",
    "z",
    "y",
)
_COMMON_UNITS = (
    "kg",
    "mm",
    "km",
    "ml",
    "lb",
    "oz",
    "in",
    "ft",
    "mi",
    "yd",
    "cm",
    "min",
    "sec",
    "hr",
    "h",
    "yr",
    "px",
    "pt",
    "dpi",
    "rpm",
    "mph",
    "kph",
    "psi",
    "atm",
    "cal",
    "kcal",
    "ppm",
    "ppb",
    "mmHg",
    "°C",
    "°F",
    "°",
    "KB",
    "MB",
    "GB",
    "TB",
    "KiB",
    "MiB",
    "GiB",
    "TiB",
    "gal",
    "pc",
    "ha",
    "rad",
)
_MAGNITUDES = ("k", "K", "M", "B", "bn", "mn", "十", "百", "千", "万", "億", "兆")
QTY_SUFFIX: frozenset[str] = frozenset(
    {p + u for u in _SI_UNITS for p in _SI_PREFIXES} | set(_COMMON_UNITS) | set(_MAGNITUDES)
)
_SUFFIX_BY_LENGTH = tuple(sorted(QTY_SUFFIX, key=lambda s: (-len(s), s)))
_SUFFIX_FIRST = frozenset(s[0] for s in QTY_SUFFIX)

_SIGNS = frozenset("-−－﹣+＋±")
_MINUS = frozenset("-−－﹣")
_PERCENT = frozenset("%‰")
_THIN = frozenset("  ")
_DECIMAL_POINTS = frozenset(".,'．·∙")  # between two digits; the last three are decimal-point variants
_SUP_DIGITS = {c: str(i) for i, c in enumerate("⁰¹²³⁴⁵⁶⁷⁸⁹")}
_SUP_MINUS = "⁻"
# A character that, directly before a sign, makes it a sign: a start of line, space, opening bracket, "=", an
# operator or a CJK character. After a letter or a digit with no space a sign is a `Sym`.
_SIGN_BEFORE = frozenset("([{<=:;,/*×÷^|&~\"'“‘«¿¡")
_FOOT_SYMBOLS = frozenset("*†‡§¶#")

SUP_OPEN, SUP_CLOSE = "﷐", "﷑"  # noncharacters: wrap a <sup> run on the raw line, so a scan sees it
SOFT_BREAK = "﷒"  # a source line break inside a text node (not a <br>)

_FOOTNOTE_BRACKET = regex.compile(r"\[\^\s*\w{1,3}\s*\]|\[\s*\d{1,3}\s*\]")
_SUP_MARK = regex.compile(rf"{SUP_OPEN}\s*(?:[0-9]{{1,3}}|[*†‡§¶#]{{1,3}})\s*{SUP_CLOSE}")
_SUP_EXPONENT = regex.compile(rf"{SUP_OPEN}\s*([-−]?\d+)\s*{SUP_CLOSE}")


def _canon_digit(ch: str) -> str:
    return "0123456789"[ord(ch) - 0xFF10] if "０" <= ch <= "９" else ch


def qty_canon(text: str) -> str:
    """A quantity's spelling for comparison: both superscript forms of an exponent written `^`, full-width
    digits as ASCII, minus variants as "-", decimal-point variants as ".", the space of a spaced sign and the
    markers of a `<sup>` removed. Digit scripts, thousands separators and case are left as written:
    equality is by spelling, never by value."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == SUP_OPEN:
            j = text.find(SUP_CLOSE, i)
            body = text[i + 1 : j].strip()
            out.append(
                "^" + ("-" if body[:1] in _MINUS else "") + "".join(map(_canon_digit, body.lstrip("-−")))
            )
            i = j + 1
            continue
        if c in _SUP_DIGITS or c == _SUP_MINUS:
            j = i
            while j < n and (text[j] in _SUP_DIGITS or (j == i and text[j] == _SUP_MINUS)):
                j += 1
            out.append(
                "^"
                + ("-" if c == _SUP_MINUS else "")
                + "".join(_SUP_DIGITS[x] for x in text[i:j] if x in _SUP_DIGITS)
            )
            i = j
            continue
        if c.isspace():
            if "".join(out) in ("-", "+", "±"):    # the gap of a spaced sign; a grouping space is content
                i += 1
                continue
            out.append(c)
            i += 1
            continue
        if c in _MINUS:
            out.append("-")
        elif c in "＋":
            out.append("+")
        elif c in "．·∙":
            out.append(".")
        else:
            out.append(_canon_digit(c))
        i += 1
    return "".join(out)


def _digit_run(u: str, i: int) -> int:
    """The end of the digits of one script starting at `i` (== `i` when there are none)."""
    n = len(u)
    if i >= n or not _is_digit(u[i]):
        return i
    zero, j = _digit_zero(u[i]), i + 1
    while j < n and _is_digit(u[j]) and _digit_zero(u[j]) == zero:
        j += 1
    return j


def _qty_end(
    u: str, i: int, sign_ok: bool, sup_exponent: bool = True, spaced_ok: bool = False
) -> tuple[int | None, int]:
    """Where the quantity starting at `i` ends, or (None, core_end): no quantity, with the end of the number
    when letters glued to it are what rule it out (the run is then one Word). `sign_ok` says a sign may start
    it."""
    n, j = len(u), i
    if j < n and u[j] in _SIGNS:
        if not sign_ok:
            return None, i
        j += 1
        if j < n and u[j].isspace() and spaced_ok:
            k = j
            while k < n and u[k].isspace():
                k += 1
            if k < n and (_is_digit(u[k]) or unicodedata.category(u[k]) == "Sc"):
                j = k
    if j < n and unicodedata.category(u[j]) == "Sc":
        j += 1
    d = _digit_run(u, j)
    if d == j:
        return None, i
    zero = _digit_zero(u[j])
    j = d
    while (
        j + 1 < n
        and (u[j] in _DECIMAL_POINTS or u[j] in _THIN)
        and _is_digit(u[j + 1])
        and _digit_zero(u[j + 1]) == zero
    ):
        j = _digit_run(u, j + 1)
    # exponent
    if j < n and u[j] in "eE":
        k = j + 1
        if k < n and u[k] in "+-−":
            k += 1
        e = _digit_run(u, k)
        if e > k:
            j = e
    elif sup_exponent and j < n and u[j] == SUP_OPEN and (m := _SUP_EXPONENT.match(u, j)):
        j = m.end()
    elif sup_exponent and j < n and (u[j] in _SUP_DIGITS or u[j] == _SUP_MINUS):
        k = j + 1 if u[j] == _SUP_MINUS else j
        e = k
        while e < n and u[e] in _SUP_DIGITS:
            e += 1
        if e > k:
            j = e
    core = j
    # suffix
    if j < n and (u[j] in _PERCENT or unicodedata.category(u[j]) == "Sc"):
        j += 1
    elif j < n and u[j] in _SUFFIX_FIRST:
        for s in _SUFFIX_BY_LENGTH:
            if u.startswith(s, j) and not (j + len(s) < n and _glues(u[j + len(s)])):
                j += len(s)
                break
    if j == core and j < n and _glues(u[j]) and not (script_class(u[j]) != SPACED and _is_letter(u[j])):
        return None, core  # letters, digits or marks glued on: a Word
    if j < n and u[j] == "/":
        r, _ = _qty_end(u, j + 1, False, sup_exponent)
        if r is not None:
            return r, core
    return j, core


# ----------------------------------------------------------------------------------------------- tokenizer

_WRAP_HYPHEN = frozenset("-‐‑")
_JOINERS = frozenset("\u200c\u200d")  # ZWNJ and ZWJ: part of the word they sit inside


def _tokenize_line(u: str, mk: list[frozenset[str]], emit, *, output: bool, rules: frozenset[str]) -> None:
    """Tokens of one line `u` (with `<sup>` runs wrapped in SUP_OPEN/SUP_CLOSE, source line breaks as
    SOFT_BREAK); `mk` is the markup of each character of `u`. `emit(cls, raw, canon, lo, hi, script)` is
    called for each token, `lo:hi` the stretch of `u` it stands for (sentinels included)."""
    n = len(u)
    sup_exp = "sup_exponent" in rules
    starts = [m.start() for m in _CLUSTER.finditer(u)]
    boundary = set(starts) | {n}
    i = 0

    def prev_glues(k: int) -> bool:
        """Whether the character before `k` makes a number there part of a Word: spaced letter, digit, mark"""
        j = k - 1
        while j >= 0 and u[j] in (SUP_OPEN, SUP_CLOSE):
            j -= 1
        return j >= 0 and _glues(u[j])

    last = [""]  # class of the last content-bearing token on the line

    def put(cls: str, lo: int, hi: int, canon: str | None = None, script: str = "", raw: str | None = None):
        text = raw if raw is not None else u[lo:hi].replace(SUP_OPEN, "").replace(SUP_CLOSE, "")
        emit(cls, text, text if canon is None else canon, lo, hi, script)
        if cls not in (SPACE, MARK):
            last[0] = cls

    while i < n:
        c = u[i]
        # white space
        if c.isspace() or c == SOFT_BREAK:
            j = i
            while j < n and (u[j].isspace() or u[j] == SOFT_BREAK):
                j += 1
            if _character(u, i - 1) and _character(u, j):
                i = j  # a space between two Han or kana characters is not content
                continue
            put(SPACE, i, j, raw=u[i:j].replace(SOFT_BREAK, " "))
            i = j
            continue
        # a sup run: a footnote mark, or an exponent the quantity scan did not take, or plain text
        if c == SUP_OPEN:
            after_digit = i > 0 and _is_digit(u[i - 1])
            m = _SUP_MARK.match(u, i)
            if m is not None and (not after_digit or not sup_exp):
                put(MARK, i, m.end())
                i = m.end()
                continue
            i += 1
            continue
        if c == SUP_CLOSE:
            i += 1
            continue
        # a bracketed footnote marker, not between digits
        if c == "[" and (m := _FOOTNOTE_BRACKET.match(u, i)):
            e = m.end()
            before = u[i - 1] if i else ""
            after = u[e] if e < n else ""
            if not (before.isdigit() and after.isdigit()):
                put(MARK, i, e)
                i = e
                continue
        # a wrapped word: "-" at the end of a line before a lowercase letter
        if (
            output
            and c in _WRAP_HYPHEN
            and i > 0
            and _is_letter(u[i - 1])
            and i + 1 < n
            and u[i + 1] == SOFT_BREAK
        ):
            j = i + 1
            while j < n and (u[j].isspace() or u[j] == SOFT_BREAK):
                j += 1
            if j < n and _is_letter(u[j]) and u[j].islower():
                put(WRAP, i, j, raw=c + "\n", canon=c + "\n")
                i = j
                continue
        # a quantity
        sign_ok = True
        if c in _SIGNS:
            j = i - 1
            while j >= 0 and u[j] in (SUP_OPEN, SUP_CLOSE):
                j -= 1
            if j >= 0:
                p = u[j]
                sign_ok = (
                    p.isspace()
                    or p == SOFT_BREAK
                    or p in _SIGN_BEFORE
                    or (script_class(p) != SPACED and _is_letter(p))
                    or unicodedata.category(p) in ("Ps", "Pi")
                )
        spaced_ok = last[0] not in (
            QTY,
            WORD,
        )  # a spaced sign ("- 0.756"): no Qty or letter stands directly before
        starts_number = _is_digit(c) or unicodedata.category(c) == "Sc" or c in _SIGNS
        if starts_number and (c in _SIGNS or not prev_glues(i)):
            end, core = _qty_end(u, i, sign_ok, sup_exp, spaced_ok)
            if end is not None and (end in boundary or end == n or u[end] in (SUP_OPEN, SUP_CLOSE)):
                raw = u[i:end]
                put(QTY, i, end, canon=qty_canon(raw))
                i = end
                continue
            if end is None and core > i and _is_digit(c):
                # letters glued to the digits: the whole run is one Word
                j = _word_end(u, core)
                put(WORD, i, j)
                i = j
                continue
        # a Word or a Sym, by clusters
        if _word_start(u, i):
            j, script = _word_run(u, i, boundary)
            put(WORD, i, j, script=script)
            i = j
            continue
        # a Sym: one cluster
        j = next((s for s in starts if s > i), n)
        put(SYM, i, j)
        i = j


_INNER = frozenset("-‐‑'’ʼ")     # hyphens and apostrophes


def _fold_records(u: str, recs: list[tuple], rules: frozenset[str]) -> list[tuple]:
    """The Id -> Text fold between the quantity scan and word tokenization: each run of Word, Sym and Space
    records is folded as text and, when the fold changed it, read into tokens again. A quantity, a mark and a
    wrap keep what the scan made of them. A re-read token stands for the whole run in the source (`lo:hi`)."""
    from .fold import fold_gap

    out: list[tuple] = []
    i, n = 0, len(recs)
    while i < n:
        if recs[i][0] not in (WORD, SYM, SPACE):
            out.append(recs[i])
            i += 1
            continue
        j = i
        while j < n and recs[j][0] in (WORD, SYM, SPACE):
            j += 1
        lo, hi = recs[i][3], recs[j - 1][4]
        at = [x for x in range(lo, hi) if u[x] not in (SUP_OPEN, SUP_CLOSE)]  # raw position -> offset in u
        raw = "".join(" " if u[x] == SOFT_BREAK else u[x] for x in at)
        folded = fold_gap(raw, line_start=i == 0)
        if folded == raw:
            out.extend(recs[i:j])
        else:
            again: list[tuple] = []
            _tokenize_line(
                folded,
                [frozenset()] * len(folded),
                lambda *r, _a=again: _a.append(r),
                output=False,
                rules=rules,
            )
            while again and again[0][0] == SPACE and not out:
                again.pop(0)
            while again and again[-1][0] == SPACE and j == n:
                again.pop()
            span = _fold_map(raw, folded)
            for c, t, k, a, b, sc in again:
                src = [span[x] for x in range(a, b)] or [span[min(a, len(folded) - 1)]]
                out.append((c, t, k, at[min(x[0] for x in src)], at[max(x[1] for x in src)] + 1, sc))
        i = j
    return out


def _fold_map(raw: str, folded: str) -> list[tuple[int, int]]:
    """For each character of `folded`, the (first, last) raw positions it comes from: an unchanged stretch
    maps one to one, a rewritten stretch (`ﬁ` to `fi`) maps each of its characters to the raw stretch."""
    import difflib

    p = 0
    while p < min(len(raw), len(folded)) and raw[p] == folded[p]:
        p += 1
    q = 0
    while q < min(len(raw), len(folded)) - p and raw[-1 - q] == folded[-1 - q]:
        q += 1
    out = [(x, x) for x in range(p)]
    rm, fm = raw[p : len(raw) - q], folded[p : len(folded) - q]
    for tag, a0, a1, b0, b1 in difflib.SequenceMatcher(None, rm, fm, autojunk=False).get_opcodes():
        if tag == "equal":
            out.extend((p + a0 + d, p + a0 + d) for d in range(a1 - a0))
        elif b1 > b0:
            out.extend([(p + a0, p + max(a1, a0 + 1) - 1)] * (b1 - b0))
    out.extend((len(raw) - q + x, len(raw) - q + x) for x in range(q))
    return out


def _spaced_letter(u: str, i: int) -> bool:
    """Whether the cluster `u[i]` is in has a spaced-script letter for its base (a mark looks back)."""
    while 0 < i < len(u) and _is_mark(u[i]):
        i -= 1
    return 0 <= i < len(u) and _is_letter(u[i]) and script_class(u[i]) == SPACED


def _character(u: str, i: int) -> bool:
    """Whether `u[i]` is a Han or kana letter."""
    return 0 <= i < len(u) and _is_letter(u[i]) and script_class(u[i]) == CHARACTER


def _word_start(u: str, i: int) -> bool:
    c = u[i]
    return _is_letter(c) or _is_digit(c)


def _word_end(u: str, i: int) -> int:
    """The end of the run of letters, digits and marks from `i` (digits keep their separators when between
    two digits)."""
    n, j = len(u), i
    while j < n:
        c = u[j]
        if _glues(c) or (_is_letter(c) and script_class(c) == SPACED):
            j += 1
        elif c in _JOINERS and j > i and j + 1 < n and _glues(u[j + 1]):
            j += 1
        elif c in _INNER and j > i and _spaced_letter(u, j - 1) and _spaced_letter(u, j + 1):
            j += 1
        elif c in _DECIMAL_POINTS and j > i and _is_digit(u[j - 1]) and j + 1 < n and _is_digit(u[j + 1]):
            j += 1
        else:
            break
    return j


def _word_run(u: str, i: int, boundary: set[int]) -> tuple[int, str]:
    """The Word starting at `i`: in a spaced script a run of letters, digits and marks; in any other script
    one cluster. Returns its end and, for a one-cluster Word, the script class."""
    n = len(u)
    c = u[i]
    if _is_letter(c) and script_class(c) != SPACED:
        j = i + 1
        while j < n and j not in boundary:
            j += 1
        return j, script_class(c)
    j = i
    while j < n:
        d = u[j]
        if _is_letter(d) and script_class(d) != SPACED:
            break
        if _is_letter(d) or _is_digit(d) or _is_mark(d):
            j += 1
        elif d in _JOINERS and j > i and j + 1 < n and (_is_letter(u[j + 1]) or _is_digit(u[j + 1])):
            j += 1
        elif d in _INNER and j > i and _spaced_letter(u, j - 1) and _spaced_letter(u, j + 1):
            j += 1           # a hyphen or apostrophe between two letters stays in the word
        elif (
            d in _DECIMAL_POINTS
            and j > i
            and _is_digit(u[j - 1])
            and j + 1 < n
            and _is_digit(u[j + 1])
            and any(_is_digit(x) for x in u[i:j])
        ):
            j += 1
        else:
            break
    if j == i:
        j = i + 1
    return j, ""


# ------------------------------------------------------------------------------------- building a document


class _Builder:
    """Collects the text of the page as lines of (text, markup) segments, a block at a time."""

    def __init__(self, rules: frozenset[str], output: bool) -> None:
        self.rules, self.output = rules, output
        self.doc = Document()
        self._parts: list[str] = []  # pieces of Document.text
        self._offset = 0
        self._block_kind, self._block_cell = "text", None
        self._open: list | None = None  # current block: [kind, cell, lines]; a line is a list of segments
        self._line = 0
        self._last_block: int | None = None

    # -- building lines
    def begin(self, kind: str, cell) -> None:
        self.flush()
        self._block_kind, self._block_cell = kind, cell

    def text(self, s: str, markup: frozenset[str], pre: bool = False) -> None:
        if not s:
            return
        if self._open is None:
            self._open = [self._block_kind, self._block_cell, [[]]]
        lines = self._open[2]
        if pre:
            parts = s.replace("\r\n", "\n").split("\n")
            for k, piece in enumerate(parts):
                if k:
                    lines.append([])
                if piece:
                    lines[-1].append((piece, markup))
            return
        for k, piece in enumerate(re.split(r"([ \t\n\f\r]*\n[ \t\n\f\r]*)", s)):
            if k % 2:  # a run of white space holding a line break
                self._space(lines, markup, soft=True)
                continue
            for j, sub in enumerate(re.split(r"([ \t\f\r]+)", piece)):
                if j % 2:
                    self._space(lines, markup)
                elif sub:
                    lines[-1].append((sub, markup))

    @staticmethod
    def _space(lines, markup, soft: bool = False) -> None:
        seg = lines[-1]
        if seg and seg[-1][0] in (" ", SOFT_BREAK):
            if soft and seg[-1][0] == " ":
                seg[-1] = (SOFT_BREAK, seg[-1][1])
            return
        if not seg:
            return  # no leading space on a line
        seg.append((SOFT_BREAK if soft else " ", markup))

    def line_break(self) -> None:
        if self._open is None:
            self._open = [self._block_kind, self._block_cell, [[]]]
        self._open[2].append([])

    def flush(self) -> None:
        if self._open is None:
            return
        kind, cell, lines = self._open
        self._open = None
        first = len(self.doc.tokens)
        index = len(self.doc.blocks)
        emitted = False
        for line in lines:
            while line and line[-1][0] in (" ", SOFT_BREAK):
                line.pop()
            if line and line[-1][0][-1:] in (" ", "\t", "\f"):
                line[-1] = (line[-1][0].rstrip(" \t\f"), line[-1][1])
            while line and not line[0][0].strip(" \t\f"):
                line.pop(0)
            if line and line[0][0][:1] in (" ", "\t", "\f"):
                line[0] = (line[0][0].lstrip(" \t\f"), line[0][1])
            if not line:
                continue
            if emitted:
                self._add(BREAK, "\n", "\n", index, self._line, frozenset(), cell)
            elif self._last_block is not None:
                self._add(BREAK, "\n", "\n", index, self._line, frozenset(), None)
            self._tokenize(line, index, cell)
            self._line += 1
            emitted = True
        if emitted:
            self.doc.blocks.append(Block(kind, cell, first, len(self.doc.tokens)))
            self._last_block = index

    def _add(self, cls, text, canon, block, line, markup, cell, script="") -> None:
        start = self._offset
        self._offset += len(text)
        self._parts.append(text)
        self.doc.tokens.append(
            Token(cls, text, canon, block, line, start, self._offset, markup, cell, script)
        )

    def math(self, tex: str, display: bool, markup: frozenset[str]) -> None:
        """A math span is a block of its own, holding one `Math` token that carries its source."""
        self.flush()
        cell, index, first = self._block_cell, len(self.doc.blocks), len(self.doc.tokens)
        if self._last_block is not None:
            self._add(BREAK, "\n", "\n", index, self._line, frozenset(), None)
        self._add(MATH, tex, tex, index, self._line, markup | ({"display"} if display else frozenset()), cell)
        self._line += 1
        self.doc.blocks.append(Block("math", cell, first, len(self.doc.tokens)))
        self._last_block = index

    def _tokenize(self, segments, block, cell) -> None:
        u_parts: list[str] = []
        mk: list[frozenset[str]] = []
        in_sup = False
        for text, markup in segments:
            sup = "sup" in markup
            if sup and not in_sup:
                u_parts.append(SUP_OPEN)
                mk.append(markup)
            if not sup and in_sup:
                u_parts.append(SUP_CLOSE)
                mk.append(markup)
            in_sup = sup
            text = text.replace(SUP_OPEN, "�").replace(SUP_CLOSE, "�")
            if "text_fold" in self.rules:
                from .fold import enumerator_digits

                text = enumerator_digits(text)
            u_parts.append(text)
            mk.extend([markup] * len(text))
        if in_sup:
            u_parts.append(SUP_CLOSE)
            mk.append(segments[-1][1])
        u = "".join(u_parts)
        line = self._line

        def emit(cls, text, canon, lo, hi, script) -> None:
            ms = [m for m in mk[lo:hi]] or [frozenset()]
            both = frozenset.intersection(*ms) if ms else frozenset()
            self._add(cls, text, canon, block, line, both, cell, script)

        recs: list[tuple] = []
        _tokenize_line(u, mk, lambda *r: recs.append(r), output=self.output, rules=self.rules)
        if "text_fold" in self.rules:
            recs = _fold_records(u, recs, self.rules)
        for r in recs:
            emit(*r)

    def finish(self) -> Document:
        self.flush()
        # a wrapped word across a <br>: "-" ending a line, a lowercase Word beginning the next
        if self.output:
            _join_wraps(self.doc)
        self.doc.text = "".join(self._parts)
        return self.doc


def _join_wraps(doc: Document) -> None:
    """A hyphen ending one line of a block and a lowercase letter beginning the next (across a <br> or a
    paragraph-internal line) is a `Wrap`, the line break part of it."""
    t = doc.tokens
    out: list[Token] = []
    # the Break between two lines of one block has the same block index on both sides
    k = 0
    while k < len(t):
        tok = t[k]
        if (
            tok.cls == SYM
            and tok.text in _WRAP_HYPHEN
            and k + 2 < len(t)
            and t[k + 1].cls == BREAK
            and t[k + 2].cls == WORD
            and t[k + 2].block == tok.block
            and t[k + 2].text[:1].islower()
            and out
            and out[-1].cls == WORD
            and out[-1].end == tok.start
        ):
            out.append(
                Token(
                    WRAP,
                    tok.text + "\n",
                    tok.text + "\n",
                    tok.block,
                    tok.line,
                    tok.start,
                    tok.end + 1,
                    tok.markup,
                    tok.cell,
                )
            )
            k += 2
            continue
        out.append(tok)
        k += 1
    if len(out) != len(t):
        # recompute offsets and text, then block bounds
        doc.tokens = _renumber(out)
        _rebound(doc)


def _renumber(tokens: list[Token]) -> list[Token]:
    out, off = [], 0
    for tok in tokens:
        out.append(
            Token(
                tok.cls,
                tok.text,
                tok.canon,
                tok.block,
                tok.line,
                off,
                off + len(tok.text),
                tok.markup,
                tok.cell,
                tok.script,
            )
        )
        off += len(tok.text)
    return out


def _rebound(doc: Document) -> None:
    blocks, k = [], 0
    for idx, b in enumerate(doc.blocks):
        first = k
        while k < len(doc.tokens) and doc.tokens[k].block == idx:
            k += 1
        blocks.append(Block(b.kind, b.cell, first, k))
    doc.blocks = blocks


# ------------------------------------------------------------------------------------------- the HTML walk

_DROP_TAGS = frozenset({"script", "style", "template", "noscript", "head", "title"})
_BLOCK_TAGS = frozenset(
    {
        "p",
        "div",
        "li",
        "ul",
        "ol",
        "dl",
        "dt",
        "dd",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "section",
        "article",
        "header",
        "footer",
        "nav",
        "aside",
        "main",
        "blockquote",
        "pre",
        "figure",
        "form",
        "address",
        "details",
        "summary",
        "fieldset",
        "legend",
        "table",
        "thead",
        "tbody",
        "tfoot",
        "tr",
        "caption",
        "hr",
        "body",
        "html",
        "center",
        "menu",
        "dir",
        "option",
        "select",
        "textarea",
    }
)
_KIND = {
    "h1": "heading",
    "h2": "heading",
    "h3": "heading",
    "h4": "heading",
    "h5": "heading",
    "h6": "heading",
    "li": "li",
    "figcaption": "caption",
    "caption": "caption",
    "pre": "pre",
    "dt": "text",
    "dd": "text",
}
_MARKUP = {
    "b": "b",
    "strong": "b",
    "i": "i",
    "em": "i",
    "u": "u",
    "ins": "u",
    "s": "s",
    "strike": "s",
    "del": "s",
    "mark": "mark",
    "sup": "sup",
    "sub": "sub",
    "code": "code",
    "tt": "code",
}
_HIDDEN_STYLE = re.compile(
    r"(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*hidden)\s*(?:!\s*important\s*)?(?=;|$)", re.I
)
_MD_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_HINT = re.compile(r"\bhidden\b|display\s*:\s*none|visibility\s*:\s*hidden|<template|<noscript", re.I)
_ALT_HINT = re.compile(r"<img\b[^<>]*\balt\s*=|!\[", re.I)


def _parse(h: str):
    root = html5lib.parse(h, treebuilder="etree", namespaceHTMLElements=False, scripting=True)
    for el in root.iter():  # MathML and SVG elements keep a namespace: read by local name
        if isinstance(el.tag, str) and el.tag.startswith("{"):
            el.tag = el.tag.rsplit("}", 1)[1]
    return root


def _is_hidden(el) -> bool:
    attrs = el.attrib
    if "hidden" in attrs:
        return True
    if el.tag == "input" and attrs.get("type", "").strip().lower() == "hidden":
        return True
    style = attrs.get("style")
    return bool(style and _HIDDEN_STYLE.search(style))


def _walk(root, drop) -> Iterator[tuple[str, object]]:
    """Events ("start", el), ("text", str), ("end", el) of the tree under `root` in document order; an element
    `drop(el)` is true of is skipped with everything in it."""
    if drop(root):
        return
    yield "start", root
    if root.text:
        yield "text", root.text
    stack = [(root, iter(list(root)))]
    while stack:
        el, it = stack[-1]
        for child in it:
            if not isinstance(child.tag, str) or drop(child):
                if child.tail:
                    yield "text", child.tail
                continue
            yield "start", child
            if child.text:
                yield "text", child.text
            stack.append((child, iter(list(child))))
            break
        else:
            stack.pop()
            yield "end", el
            if stack and el.tail:
                yield "text", el.tail


def read(h: str, *, rules: Iterable[str] | None = None, output: bool = True) -> Document:
    """The document D of an output's HTML. Raises `MalformedOutput` when `h` is not a string. `rules`
    names the reader's rules in force (default: the switches as they stand); a rule that is off reads as
    the scorer did before it."""
    if not isinstance(h, str):
        raise MalformedOutput(f"html must be a string, not {type(h).__name__}: {h!r:.80}")
    rules = _rules(rules)
    root = _parse(h)
    maths: dict[int, str] = {}
    for el in list(root.iter("math")):  # a math element is its source: its children are not text
        maths[id(el)] = _math_source(el)
        el.text = None
        for kid in list(el):
            el.remove(kid)
    hidden = (
        (lambda el: el.tag in _DROP_TAGS or _is_hidden(el))
        if "visibility" in rules
        else (lambda el: el.tag in ("script", "style", "head", "title"))
    )
    b = _Builder(rules, output)
    markup: list[frozenset[str]] = [frozenset()]
    cell_stack: list[list[int]] = []  # per open table: [table_id, row, col]
    tables = 0
    lists: list[list] = []  # per open list: [ordered, next number]
    cell_now: list = [None]
    pre = 0
    for event, x in _walk(root, hidden):
        if event == "text":
            s = x
            if "alt_text_out" not in rules:
                s = _MD_IMAGE.sub(lambda m: f" {m[1]} ", s)
            elif "![" in s:
                s = _MD_IMAGE.sub(" ", s)
            b.text(s, markup[-1], pre=bool(pre))
            continue
        el = x
        tag = el.tag
        if event == "start":
            m = _MARKUP.get(tag)
            markup.append(markup[-1] | {m} if m else markup[-1])
            if tag == "table":
                tables += 1
                cell_stack.append([tables, -1, -1, set()])
                b.begin("text", None)
            elif tag == "tr":
                if cell_stack:
                    cell_stack[-1][1] += 1
                    cell_stack[-1][2] = -1
                b.begin("text", None)
            elif tag in ("td", "th"):
                if cell_stack:
                    st = cell_stack[-1]
                    st[2] += 1
                    while (st[1], st[2]) in st[3]:      # a slot an earlier rowspan holds
                        st[2] += 1
                    cell_now.append((st[0], st[1], st[2]))
                    b.begin("cell", cell_now[-1])
                    cs, rs = (_span(el, k) for k in ("colspan", "rowspan"))
                    st[3].update((st[1] + dr, st[2] + dc) for dr in range(rs) for dc in range(cs))
                    st[2] += cs - 1
                else:
                    b.begin("text", cell_now[-1])
            elif tag == "br":
                b.line_break()
            elif tag == "wbr":
                pass
            elif tag in ("ol", "ul"):
                lists.append(
                    [
                        tag == "ol",
                        int(el.attrib["start"]) if el.attrib.get("start", "").lstrip("-").isdigit() else 1,
                    ]
                )
                b.begin("text", cell_now[-1])
            elif tag == "li":
                b.begin("li", cell_now[-1])
                if lists and lists[-1][0]:
                    b.text(f"{lists[-1][1]}. ", markup[-1])
                    lists[-1][1] += 1
            elif tag in _BLOCK_TAGS or tag in ("figcaption",):
                b.begin(_KIND.get(tag, "text"), cell_now[-1])
                if tag == "pre":
                    pre += 1
            elif tag == "img":
                if "alt_text_out" not in rules and (alt := el.attrib.get("alt")):
                    b.text(f" {alt} ", markup[-1])
                else:
                    b.text(" ", markup[-1])
            elif tag == "input":
                typ = el.attrib.get("type", "").strip().lower()
                if typ in ("checkbox", "radio"):
                    b.text(f" {'☒' if 'checked' in el.attrib else '☐'} ", markup[-1])
                elif (v := el.attrib.get("value")) is not None and typ not in ("hidden",):
                    b.text(f" {v} ", markup[-1])
            elif tag in ("checked", "unchecked"):
                b.text(f" {'☒' if tag == 'checked' else '☐'} ", markup[-1])
            elif tag == "math":
                b.math(maths[id(el)], el.attrib.get("display") == "block", markup[-1])
            continue
        # end
        markup.pop()
        if tag in ("td", "th"):
            if cell_stack:
                cell_now.pop() if len(cell_now) > 1 else None
            b.begin("text", cell_now[-1])
        elif tag == "table":
            if cell_stack:
                cell_stack.pop()
            b.begin("text", cell_now[-1])
        elif tag in ("ol", "ul"):
            if lists:
                lists.pop()
            b.begin("text", cell_now[-1])
        elif tag in _BLOCK_TAGS or tag in ("figcaption", "li", "tr"):
            if tag == "pre" and pre:
                pre -= 1
            b.begin("text", cell_now[-1])
    return b.finish()


def _span(el, name: str) -> int:
    v = el.attrib.get(name, "1").strip()
    return min(int(v), 1000) if v.isdigit() and int(v) > 0 else 1


def _math_source(el) -> str:
    """The TeX of a <math> element: its TeX annotation, else its text content."""
    for a in el.iter("annotation"):
        if "tex" in a.attrib.get("encoding", "").lower() and a.text:
            return a.text.strip()
    return "".join(el.itertext()).strip()


# ---------------------------------------------------------------------------------------------- gold text


def tokenize(s: str, *, output: bool = False, rules: Iterable[str] | None = None) -> list[Token]:
    """The tokens of a plain string (a test's gold, or text that carries no markup): lines split at "\\n" and
    U+2029, `Break` between them, the same classes as `read`. A gold string has no `Wrap`."""
    rules = _rules(rules)
    b = _Builder(rules, output)
    for k, piece in enumerate(re.split("[\n ]", s)):
        if k:
            b.line_break()
        b.text(piece, frozenset(), pre=True)
    b.flush()
    toks = b.finish().tokens
    return [
        t if t.block < 0 else Token(t.cls, t.text, t.canon, -1, -1, t.start, t.end, t.markup, None, t.script)
        for t in toks
    ]


# --------------------------------------------------------------------------------- hiding, for the scorer


@functools.lru_cache(maxsize=256)
def visible_html(h: str, *, hidden: bool = True, alt: bool = True) -> str:
    """`h` as HTML with the text a page hides taken out (`hidden`) and image alt text taken out (`alt`);
    unchanged when it holds none, so a page that hides nothing reads exactly as before. The part of the
    reader the scorer's text views use while they are still the old ones."""
    wants_hidden = hidden and _HINT.search(h)
    wants_alt = alt and _ALT_HINT.search(h)
    if not (wants_hidden or wants_alt):
        return h
    root = _parse(h)
    changed = False
    if wants_hidden:
        for parent in list(root.iter()):
            for child in list(parent):
                if (
                    isinstance(child.tag, str)
                    and child.tag in ("template", "noscript")
                    or (isinstance(child.tag, str) and _is_hidden(child))
                ):
                    _remove(parent, child)
                    changed = True
    if wants_alt:
        for el in root.iter("img"):
            if "alt" in el.attrib:
                del el.attrib["alt"]
                changed = True
    out = h
    if changed or ("![" in h):
        body = root.find("body")
        out = _serialize(body if body is not None else root)
    if alt and "![" in out:
        out = _MD_IMAGE.sub(" ", out)
    return out


def _remove(parent, child) -> None:
    """Takes `child` out of `parent`, keeping the text that follows it."""
    tail = child.tail or ""
    kids = list(parent)
    i = kids.index(child)
    if i:
        kids[i - 1].tail = (kids[i - 1].tail or "") + tail
    else:
        parent.text = (parent.text or "") + tail
    parent.remove(child)


def _serialize(el) -> str:
    from html5lib.serializer import HTMLSerializer
    from html5lib.treewalkers import getTreeWalker

    walker = getTreeWalker("etree")(el)
    ser = HTMLSerializer(
        omit_optional_tags=False,
        quote_attr_values="always",
        minimize_boolean_attributes=False,
        use_trailing_solidus=False,
        escape_lt_in_attrs=True,
        resolve_entities=False,
        strip_whitespace=False,
    )
    s = "".join(ser.serialize(walker))
    return re.sub(r"^<body[^>]*>|</body>$", "", s)
