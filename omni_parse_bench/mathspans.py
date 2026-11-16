"""Where the dollar-delimited math spans (`$..$`, `$$..$$`) are in model output: one reader for every path.

A `$` is a delimiter or a currency sign, and the characters around it do not always say which
(`$ and $ x $`, `$5.00 ... $U$`, `$92,000; Net +$60,000`). The text path (`normalize`) and the equation
path (`equations`) each used to pair the dollars their own way. This module decides the pairing once; each
path then renders the spans it is given. (`\\(..\\)`, `\\[..\\]`, `<math>` and `\\begin{..}` carry their own
delimiters, so there is no pairing to decide for them.)

The rules, in one place:

1. A line is the unit for a single-dollar span: it never crosses a line (a "\\n", or `views.BREAK` at
   every block tag). A `$$..$$` display may run over several.
2. A dollar escaped by a backslash (`\\$`) is not a delimiter. A run of dollars is a token: one dollar, or
   `$$`, which is a display delimiter, or the close of one span and the open of the next ("$a$$b$"); a run
   of three is a dollar and a `$$`.
3. A span's body holds no dollar of its own, so spans pair ADJACENT tokens: `$a$ and $b$` is the pairs (1, 2)
   and (3, 4), never (2, 3). The words between two spans can therefore not become a span of their own.
4. A dollar with no partner is a stray: currency, or a delimiter the producer left out. Which dollars pair and
   which are strays is one choice for the whole line: the pairing with the greatest total value, each pair
   scored by what its body looks like (`_score`) and each stray costing something (`_stray`), a dollar that
   reads as currency ($5, US$5) costing least. On a tie the earliest dollars are the strays, since a price
   comes before the math it sits beside ("Cost $ and $ x $").
5. A pair is MATH when its body reads as math: LaTeX markup, one to three letters, spaced digits, or plain
   symbols that hug their dollars ("$p < 0.05$"). It is READ (a text reader converts it) unless it is too
   long or too spaced to be ours to read, and not math at all when it is a form's blank (`__`), two prices
   (a digit after each dollar, no LaTeX between), or prose (three or more bare words).
6. Padding is the producer's style, not the span's: `$ p $` is a variable on a page whose math is padded
   (`$ x_1 $` somewhere in the same text), and bare padding without that evidence is worth less than a
   hugging span.
"""
from __future__ import annotations

import re
from typing import NamedTuple

from . import views

# Note: LaTeX is a command, a brace, or a script with something to raise or lower ("_ P" is a subscript, as
# "_P" is); a trailing "_" or "^" with nothing after it is a form's blank, not a subscript.
_LATEX_MARKUP = re.compile(r"[\\{}]|[_^](?=\s*\S)")
# Note: a span with this many bare words (three letters or more, outside every brace, not a command, not
# all capitals: AOB and BOC are points) is prose ("$____ Date paid ____ Balance $"); math has almost none,
# however it is spaced.
_PROSE_WORDS = 3
_PROSE_WORD = re.compile(r"(?<![\\\w&])(?![A-Z]+\b)[^\W\d_]{3,}")
_BRACED = re.compile(r"\{[^{}]*\}")
# Note: one to three letters between dollars is a variable ($U$, $d$, $Re$); an amount has digits.
LETTERS = re.compile(r"[^\W\d_]{1,3}")
# Note: a span longer than this is math we do not read ("$5.00 ... on line $1,000" also sits between two
# dollars, and converting it would eat the money's "$").
MAX_LEN, MAX_SPACES = 120, 4
# Digits spaced out inside the dollars, as a LaTeX writer spaces them ("$$2 . 5 5$$"); a dollar amount has a
# space at the span's edge instead ("$2.7 $2.2": the span is "2.7 "), so it is not one.
SPACED_DIGITS = re.compile(r"\d[\d.,]*(?:\s+[\d.,]+)+")
# Note: in math mode a space renders nothing ("$$2 . 5 5$$" is 2.55), except the one ending a command name
# (\pm 0, \alpha b), a control space (x\ y), and those in and after a text group (\text{is the} x), which
# may hold one level of braces.
_MATH_TEXT = re.compile(r"\\(?:text\w*|mbox|operatorname)\s*\{(?:[^{}]|\{[^{}]*\})*\}\s*")
_COMMAND_SPACE = re.compile(r"(\\[A-Za-z]+)\s+")
_CONTROL_SPACE = re.compile(r"(?<!\\)\\\s+")
# A padded span around LaTeX is the sign of a producer that pads its math.
# Note: `$ ... $` with a space inside both dollars and a command or script between: the page pads its math.
_PADDED_OPEN = re.compile(r"(?<![\\$])\$(?=\s)")
_CURRENCY = re.compile(r"\s?(?:\d|\.\d)")
_CURRENCY_CODE = re.compile(r"(?:^|\s)[A-Z]{1,3}$")    # US$5, CA$5, R$5
_LINE_END = re.compile(r"[\n\u2029]")


class Span(NamedTuple):
    start: int
    end: int
    body: str
    read: bool      # a text reader converts it; False is math too long or too spaced to read
    display: bool   # `$$..$$`


def dense(body: str) -> str:
    """A math span's LaTeX without the spaces that render nothing."""
    body, held = views.hold(body, _MATH_TEXT)
    body = _COMMAND_SPACE.sub(lambda m: m[1] + "\0", _CONTROL_SPACE.sub("\0", body))
    return views.release(re.sub(r"\s+", "", body).replace("\0", " "), held)


def prose(body: str) -> bool:
    """Whether a span's words, outside its braces, are prose's."""
    for _ in range(16):    # nested braces are peeled a bounded number of times
        if (unbraced := _BRACED.sub(" ", body)) == body:
            break
        body = unbraced
    return len(_PROSE_WORD.findall(body)) >= _PROSE_WORDS


def too_long(body: str) -> bool:
    return dense(body).count(" ") > MAX_SPACES or len(body) > MAX_LEN


def balanced(body: str) -> bool:
    """Whether a body's braces close: "x \\tag{ " is half a span, and no pair of dollars around it is one."""
    depth = 0
    for c in re.sub(r"\\[{}]", "", body):
        depth += (c == "{") - (c == "}")
        if depth < 0:
            return False
    return depth == 0


def _strong_markup(body: str) -> bool:
    """A command, a brace, or a script with its operand against it: the markup of math, not of a blank."""
    return bool(re.search(r"[\\{}]|[_^](?=\S)", body))


def has_markup(body: str) -> bool:
    return bool(_LATEX_MARKUP.search(body))


def _pads_math(s: str) -> bool:
    """Whether the text has a span padded inside its dollars around a command or script: `$ x_1 $`. Each
    dollar looks only as far as the next one, so the scan is linear."""
    for m in _PADDED_OPEN.finditer(s):
        end = s.find("$", m.end())
        if end < 0:
            return False
        body = s[m.end():end]
        if (len(body) > 2 and body[-1].isspace() and "\n" not in body and s[end + 1:end + 2] != "$"
                and re.search(r"[\\^_]", body[1:-1])):
            return True
    return False


def find(s: str, pads: bool | None = None) -> list[Span]:
    """The math spans of `s`, in order: `$$..$$` displays and single-dollar pairs whose body reads as math.
    `pads` says whether the page pads its math (rule 6) when `s` is a part of a page; by default `s` says."""
    if "$" not in s:
        return []
    return _pair(s, _pads_math(s) if pads is None else pads)


def pads_math(s: str) -> bool:
    """Whether the text pads its math (rule 6)."""
    return _pads_math(s)


class _Token(NamedTuple):
    pos: int    # where the run starts
    run: int    # 1: one dollar; 2: `$$`

    @property
    def closer(self) -> int:    # the dollar that closes a span: the first of the run
        return self.pos

    @property
    def opener(self) -> int:    # the dollar that opens a span: the last of the run
        return self.pos + self.run - 1


def _tokens(s: str, start: int, end: int) -> list[_Token]:
    """The dollar runs of s[start:end] that are not escaped; a run of three is a dollar, then a `$$`."""
    out, i = [], start
    while (i := s.find("$", i, end)) != -1:
        j = i
        while j < end and s[j] == "$":
            j += 1
        backslashes = 0
        while i - 1 - backslashes >= start and s[i - 1 - backslashes] == "\\":
            backslashes += 1
        if backslashes % 2 == 0:
            k = i
            if (j - i) % 2:
                out.append(_Token(k, 1))
                k += 1
            out += [_Token(k + 2 * m, 2) for m in range((j - k) // 2)]
        i = j
    return out


def _pair(s: str, pads: bool) -> list[Span]:
    """The best reading of the dollars of `s` (rules 3 and 4): each dollar is used at most once, in a pair of
    adjacent tokens or as a stray. A `$$` token has two dollars: it may close one span and open the next.
    A single-dollar span stays on its line; a display may run over several."""
    toks = _tokens(s, 0, len(s))
    n = len(toks)
    if n < 2:
        return []
    # g[i][u]: the best value of toks[i:] when the closing dollar of toks[i] is already used (u = 1) or not.
    g = [[0.0, 0.0] for _ in range(n + 2)]
    how: dict[tuple[int, int], str] = {}
    for i in range(n - 1, -1, -1):
        t = toks[i]
        for u in (0, 1):
            if t.run == 1:    # one dollar: spent if it closed, free to open if not
                strays = 0.0 if u else _stray(s, t.pos)
            else:
                strays = (0.0 if u else _stray(s, t.closer)) + _stray(s, t.opener)
            options = [(g[i + 1][0] - strays, "stray")]    # first, so that a tie leaves this dollar a stray
            body = s[t.opener + 1:toks[i + 1].closer] if i + 1 < n else ""
            if i + 1 < n and (t.run == 2 or u == 0) and not _LINE_END.search(body):
                unused = _stray(s, t.closer) if (t.run == 2 and u == 0) else 0.0
                score = _score(body, s, toks[i + 1].closer, pads)[0]
                options.append((score + g[i + 1][1] - unused, "inline"))
            if u == 0 and t.run == 2 and (j := _partner(toks, i)) is not None:
                nested = _nested_value(toks, i, j, s, pads)
                options.append((_display_value(s[t.pos + 2:toks[j].pos]) + nested + g[j + 1][0], "display"))
            value, name = options[0]
            for v, nm in options[1:]:
                if v > value:
                    value, name = v, nm
            g[i][u], how[(i, u)] = value, name
    out, i, u = [], 0, 0
    while i < n:
        t = toks[i]
        name = how[(i, u)]
        if t.run == 1 and u == 1:
            i, u = i + 1, 0
            continue
        if name == "inline":
            a, b = t.opener, toks[i + 1].closer
            math, read = _math(s[a + 1:b], s, b, pads)
            if math:
                out.append(Span(a, b + 1, s[a + 1:b], read, False))
            i, u = i + 1, 1
        elif name == "display":
            j = _partner(toks, i)
            close = toks[j].pos
            if j - 1 > i and toks[j - 1].run == 1 and toks[j - 1].pos + 1 == close:
                close = toks[j - 1].pos    # "$$x$$$5": the dollar after the close is not part of the display
            body = s[t.pos + 2:close]
            if _display_value(body) > 0:
                out.append(Span(t.pos, close + 2, body, True, True))
            i, u = j + 1, 0
        else:
            i, u = i + 1, 0
    return out


_TEXT_GROUP = re.compile(r"\\(?:text|textrm|textbf|textit|mbox|hbox)\s*\{")


def _in_text_group(before: str) -> bool:
    """Whether the end of `before` is inside an open `\\text{...}` group, where TeX nests math in math."""
    for m in reversed(list(_TEXT_GROUP.finditer(before))):
        depth = 1
        for c in before[m.end():]:
            depth += (c == "{") - (c == "}")
            if depth == 0:
                break
        else:
            return True
    return False


def _nested_value(toks: list[_Token], i: int, j: int, s: str, pads: bool) -> float:
    """What the single dollars inside a display add to it: math in the display's `\\text{...}`, as in
    `\\text{if $b\\neq 0$,}`. Such a pair is worth what it reads as, so the display is not outvoted by the
    spans it contains. Single dollars anywhere else add nothing: they are spans the display swallowed."""
    inner = toks[i + 1:j]
    total = 0.0
    for a, b in zip(inner[::2], inner[1::2], strict=False):
        body = s[a.opener + 1:b.closer]
        if _LINE_END.search(body) or not _in_text_group(s[toks[i].pos + 2:a.pos]):
            continue
        total += max(0.0, _score(body, s, b.closer, pads)[0])
    return total


def _partner(toks: list[_Token], i: int) -> int | None:
    """The `$$` that closes a display opened by toks[i]: the next one, over any single dollars between
    (`\\tag{ $\\dagger$ }` sits inside a display)."""
    j = i + 1
    while j < len(toks) and toks[j].run == 1:
        j += 1
    return j if j < len(toks) else None


def _stray(s: str, d: int) -> float:
    """What a dollar left without a partner costs: little if it reads as currency."""
    return 0.5 if _CURRENCY.match(s, d + 1) else 2.0


def _display_value(body: str) -> float:
    """A `$$..$$` is math unless it is empty or a form's blank: its delimiters are the evidence."""
    return -3.0 if not body.strip() or "__" in body else 5.0


def _math(body: str, s: str, closer: int, pads: bool) -> tuple[bool, bool]:
    """Whether a pair's body is math, and whether a text reader reads it."""
    v, read = _score(body, s, closer, pads)
    return v > 0, read


def _score(body: str, s: str, closer: int, pads: bool) -> tuple[float, bool]:
    """A pair's value (positive for math) and whether it is read."""
    inner = body.strip()
    if not inner or "$" in body.replace("\\$", ""):    # a span holds no dollar of its own
        return -3.0, False
    if "__" in body:    # a form's blank; LaTeX never writes two underscores in a row
        return -3.0, False
    markup = has_markup(body)
    if markup and not balanced(body):    # half a span: worth little, so a longer span that holds it wins,
        return 1.0, True                 # but on its own it is read, as a producer's typo ("\\boxed{x $")
    # Note: a digit on both sides of a span with no LaTeX in it is two prices ("$92,000; Net +$60,000"), not
    # math before a number ("$\\ge$2", "$5\\times$10"), and so is a span that opens on a digit and ends in a
    # space before one: the closing dollar opens the next price ("$2.7 $2.2"), as "US$5" does. A padded span
    # around LaTeX ("0.1 $ \\pm $0.0") is math.
    if s[closer + 1:closer + 2] in tuple("0123456789") and (
            _CURRENCY_CODE.search(body)
            or (body[:1] in "0123456789" and (body[-1:].isspace() or not _strong_markup(body)))):
        return -3.0, False    # the closing dollar opens the next price
    hugs = body == inner
    if LETTERS.fullmatch(inner):
        if hugs:
            return 3.0, True
        # Note: padded, one letter or a name with a capital (FeS, ΔG) is a variable; two or three lowercase
        # letters are a word unless the page pads its math.
        if len(inner) == 1 or not (inner.islower() and inner.isascii()):
            return 2.0, True
        return (1.0, True) if pads else (-1.0, False)
    if SPACED_DIGITS.fullmatch(body):
        return 3.0, True
    if prose(body):
        return -3.0, False
    if markup:
        return (1.0, False) if too_long(body) else (4.0, True)
    if too_long(body):
        return -3.0, False
    if hugs:
        return 2.0, True
    return (1.0 if pads else -1.0), pads
