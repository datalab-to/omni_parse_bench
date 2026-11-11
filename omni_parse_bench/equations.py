"""Equations compared by what they render, not by how their LaTeX is written: `symbols` turns an equation into
what it renders, `spans` finds the math in an output, `appears` says whether a test's equation is in it, and
`in_text` whether plain text writes it.
"""
from __future__ import annotations

import atexit
import functools
import html as _html
import re
import threading
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

from omni_parse_bench import views

KATEX = Path(__file__).parent / "katex" / "katex.js"   # KaTeX 0.16.22, MIT (LICENSE beside it)
# Note: KaTeX bundles mathtools' pre-2022 \coloneq (":-"); since 2022 it prints ":=", as \coloneqq does.
_RENDER = """(tex, display) => {
  try {
    const macros = {"\\\\coloneq": "\\\\coloneqq", "\\\\Coloneq": "\\\\Coloneqq"};
    return {mathml: katex.renderToString(tex, {output: "mathml", displayMode: display, strict: "ignore",
                                                throwOnError: true, trust: false, macros})};
  } catch (e) {
    return {error: String(e.message || e).slice(0, 300)};
  }
}"""
_NS = "{http://www.w3.org/1998/Math/MathML}"
# Note: bold is dropped, so a bold script or fraktur letter is its plain script or fraktur letter.
_KEPT_FONTS = {"double-struck": "double-struck", "script": "script", "fraktur": "fraktur",
               "bold-script": "script", "bold-fraktur": "fraktur"}
_ALIASES = str.maketrans({"⩽": "≤", "⩾": "≥", "∥": "‖", "−": "-", "′": "'", "∣": "|", "⋅": "·",
                          "∗": "*", "⋆": "*", "ϵ": "ε", "ϕ": "φ", "ϑ": "θ", "∶": ":",
                          "…": "⋯", "\\": "∖", "♯": "#", "≔": ":=", "≕": "=:", "≦": "≤", "≧": "≥"})
_DOTS, _VDOTS = {"⋯", "·", "."}, {"⋮", "⋱", "⋰"}
_INVISIBLE = {"⁡", "⁢", "⁣", "⁤", "​"}
_DROPPED = {"mspace", "mphantom", "annotation", "annotation-xml", "none", "mprescripts"}
_SPANS = re.compile(
    r"\$\$(?P<dd>.+?)\$\$|\\\[(?P<db>.+?)\\\]|\\\((?P<ib>.+?)\\\)|(?<![\\$])\$(?!\s)(?P<i>[^$\n]+?)(?<!\s)\$"
    r"|<math\b(?P<mattr>[^<>]*)>(?P<m>.*?)</math>"
    r"|(?P<env>\\begin\{(?P<name>(?:equation|align|alignat|aligned|gather|gathered|multline|eqnarray|"
    r"displaymath)\*?)\}.*?\\end\{(?P=name)\})"
    # Note: dollars with a space inside are math only around LaTeX ("$ x_1 $", "$\\psi = $ const"), never
    # a price ("$5 or $6").
    r"|(?<![\\$])\$(?P<pad>[^$\n]*?[\\^_][^$\n]*?)\$(?!\$)"
    r"|(?:^|(?<=>))(?P<bare>(?:[^<>$\n\\]|\\(?![(\[]))+)(?=<|$)", re.S | re.I | re.M)
_TAG = re.compile(r"<[^<>]+>")
# Note: a line break before each block tag, so an inline $..$ never spans two blocks
# ("<p>$5</p><p>$$x$$</p>").
# Not <br> or <img>: a break or an image may sit inside a span. The name must end the tag, so "0<p\leq 1"
# isn't one.
_BLOCK = re.compile(r"(?=</?(?:table|thead|tbody|tfoot|tr|td|th|p|div|li|ul|ol|dl|dt|dd|h[1-6]|section|"
                    r"article|figure|figcaption|blockquote|pre|caption)(?=[\s/>]))", re.I)
_UNTAG = re.compile(r"\\(?:tag\*?|label)\s*\{[^{}]*\}|\\(?:notag|nonumber)(?![A-Za-z])")
_UNDEFINED = re.compile(r"Undefined control sequence: (\\[A-Za-z]+)")
_LATEX = re.compile(r"\\[A-Za-z]|[\^_]")
_WORD = re.compile(r"(?<![\\\w])[^\W\d_]{3,}")
_BRACED = re.compile(r"\{[^{}]*\}")
_MAX_UNDEFINED = 5
# Between spans: whitespace only (soft), or prose (hard); a full stop, comma or semicolon right after
# a span (its own token). The tokens aren't symbols KaTeX makes.
_SOFT, _HARD, _GAP, _SPACE, _DISPLAY_END = "\0~", "\0#", "\0", " ", "\0$"
_PUNCT = {",": ",", ";": ";", ".": "·"}
_ROW = "\\\\"
_SIGNS = frozenset("-+±∓")
# What stands between symbols and leaves the expressions on either side whole.
_OPS = frozenset("=<>≤≥≠≈∼≃≅≡∝≪≫∈∉∋⊂⊆⊃⊇→←↔⇒⇐⇔↦+-±∓·×÷*/∘∪∩∧∨⊕⊗,;:") | {":=", "=:", _ROW}


class _KaTeX:
    """KaTeX in an embedded V8 (mini-racer), shared by the threads of a scoring run."""

    def __init__(self) -> None:
        import py_mini_racer

        # Note: a V8 context runs one call at a time, so the threads take turns.
        self.lock = threading.Lock()
        self.ctx = py_mini_racer.MiniRacer()
        self.ctx.eval(KATEX.read_text())
        self.ctx.eval(f"var render = {_RENDER}")

    def render(self, tex: str, display: bool) -> dict:
        with self.lock:
            return self.ctx.call("render", tex, display)

    def mathml(self, tex: str, display: bool) -> str | None:
        return self.render(tex, display).get("mathml")

    def close(self) -> None:
        # Note: takes the lock, so a thread mid-call finishes before the context goes away.
        with self.lock:
            self.ctx.close()


@functools.cache
def _katex() -> _KaTeX:
    katex = _KaTeX()
    # Note: closed here, while Python can still run threads. Left to its finalizer at interpreter exit, the
    # context joins its event-loop thread, which can't take the GIL by then, and the process never exits.
    atexit.register(katex.close)
    return katex


@functools.lru_cache(maxsize=200_000)
def symbols(tex: str, display: bool = False) -> tuple[str, ...] | None:
    r"""What `tex` renders to, as a flat sequence of symbols and structure; None if it doesn't parse.

    KaTeX (one embedded V8 per process) turns the LaTeX into MathML, where every symbol is its final character
    (`\to` and `\rightarrow` are both →) and the structure is explicit: fractions, scripts, roots, rows of an
    array. This walks that MathML into a flat sequence, leaving out what doesn't change the equation:

        spacing                  \quad, \, and friends: dropped
        alignment                `&`, and how rows are split into cells: dropped; rows are kept, and a row of
                                 nothing but dots is one ellipsis, whatever its dots (vertical and diagonal
                                 dots one kind, horizontal another)
        fonts                    upright, italic and bold: dropped; blackboard, script and fraktur kept
        invisible operators      function application, invisible times: dropped
        look-alikes              ⩽, ≦ and ≤, ⩾, ≧ and ≥, ∥ and ‖, − and -, ′ and ', … and ⋯, ≔ and :=,
                                 ° and a degree written ^\circ, ϵ and ε, ϕ and φ, ϑ and θ,
                                 ∖ and a backslash, ♯ and #, ⋆ and *, . and ·
        equation numbers         \tag and \label, and a number after dot leaders ending a display formula
                                 (". . . (2)"): dropped, on both sides
        negations                a relation with a slash through it (\not\in) and its negated character (∉)
        restrictions             a | opening a subscript and a | just before it (φ_{|S} and φ|_S)
        constructions            `cases` and `\left\{ \begin{aligned} … \right.` render alike already

    These stay differences: \bar and \overline, \setminus and a minus, one letter font for another, and a
    dropped blackboard font."""
    mathml = _katex().mathml(tex, display)
    return None if mathml is None else _from_mathml(mathml)


def _from_mathml(mathml: str) -> tuple[str, ...] | None:
    try:
        root = ET.fromstring(re.sub(r"^<span[^>]*>|</span>$", "", mathml.strip()))
    except ET.ParseError:
        return None
    return tuple(_degrees(_canonical(_walk(root))))


def _degrees(xs: list[str]) -> list[str]:
    """A degree written as an exponent (^\\circ) as the degree sign."""
    out: list[str] = []
    for x in xs:
        if x == ")" and out[-2:] == ["^(", "∘"]: out[-2:] = ["°"]
        else: out.append(x)
    return out


def _unnumber(xs: tuple[str, ...]) -> tuple[str, ...]:
    """A display formula without the number an old book prints after dot leaders ("… (1),"), keeping
    the punctuation that ends it."""
    body, tail = (xs[:-1], xs[-1:]) if xs and xs[-1] in _PUNCT.values() else (xs, ())
    # Note: a starred number, (4)^* or (4*), is a number too.
    body = body[:-3] if body[-3:] == ("^(", "*", ")") else body
    if not body or body[-1] != ")" or "(" not in body: return xs
    j = len(body) - 1 - body[::-1].index("(")
    number = body[j + 1:-1]
    if not 0 < len(number) <= 8 or not all(t.isalnum() or t in ".·'*" for t in number): return xs
    k = j
    while k and body[k - 1] in ("⋯", "·"): k -= 1
    return body[:k] + tail if k < j else xs


def _canonical(xs: list[str]) -> list[str]:
    """A slash through a relation made its negated character, a | opening a subscript moved before
    it, and three dots an ellipsis."""
    out: list[str] = []
    for x in xs:
        if out and "\u0338" in (out[-1], x) and len(neg := unicodedata.normalize(
                "NFC", (x if out[-1] == "\u0338" else out[-1]) + "\u0338")) == 1:
            out[-1] = neg
        elif out and out[-1] == "_(" and x == "|":
            out[-1:] = ["|", "_("]
        elif x == "·" and out[-2:] == ["·", "·"]:
            out[-2:] = ["⋯"]
        else:
            out.append(x)
    return out


def _walk(e: ET.Element) -> list[str]:
    tag = e.tag.removeprefix(_NS)
    # Note: KaTeX can put the invisible function application after an operator name as a child of its
    # own (d_{\\min}^{C} is <msubsup> of d, min, U+2061 and C), which would shift the children read by
    # position below. Only an invisible operator is dropped: an empty <mo> holds a place
    # (\mathbin{}^{2} is <msup> of an empty <mo> and 2).
    kids = [k for k in e if not (k.tag.removeprefix(_NS) == "mo" and not len(k) and _invisible(k.text))]
    if tag in _DROPPED: return []
    if tag == "semantics": return _walk(kids[0]) if kids else []
    if tag in ("mi", "mn", "mo", "mtext", "ms"):
        if kids:  # Note: KaTeX nests some symbols, an <mi> inside an <mo> (\\coloneqq)
            return [s for k in kids for s in _walk(k)]
        # Note: a space in text ends a word (\\text{of } a): kept as `_SPACE`, which a match may skip.
        words = (e.text or "").split() if tag == "mtext" else [e.text or ""]
        return [t for i, w in enumerate(words) for t in [*([_SPACE] if i else []), *_leaf(tag, w, e)]]
    if tag == "mfrac":
        num, den = (_walk(k) for k in kids[:2])
        name = "binom" if e.get("linethickness") in ("0", "0px", "0em") else "frac"
        return [f"{name}(", *num, ",", *den, ")"]
    if tag == "munder" and e.get("accentunder") == "true":
        return ["accent(", *_walk(kids[1]), ")(", *_walk(kids[0]), ")"]
    if tag in ("msub", "munder"):
        return [*_walk(kids[0]), "_(", *_walk(kids[1]), ")"]
    if tag in ("msup", "mover"):
        if tag == "mover" and e.get("accent") == "true":
            return ["accent(", *_walk(kids[1]), ")(", *_walk(kids[0]), ")"]
        return [*_walk(kids[0]), "^(", *_walk(kids[1]), ")"]
    if tag in ("msubsup", "munderover"):
        return [*_walk(kids[0]), "_(", *_walk(kids[1]), ")", "^(", *_walk(kids[2]), ")"]
    if tag == "msqrt":
        return ["sqrt(", *[s for k in kids for s in _walk(k)], ")"]
    if tag == "mroot":
        return ["root(", *_walk(kids[1]), ")(", *_walk(kids[0]), ")"]
    if tag == "mtable":
        # Note: rows are kept, and a row's cells joined: where `&` splits a row is alignment.
        out = []
        for i, row in enumerate(kids):
            if i: out.append("\\\\")
            cells = [s for cell in row for s in _walk(cell)]
            # Note: a row of nothing but dots elides rows, whatever the dots' style or number; vertical
            # and diagonal dots are one kind, horizontal ones another.
            if cells and set(cells) <= _DOTS | _VDOTS: cells = ["⋮" if set(cells) & _VDOTS else "⋯"]
            out += cells
        return out
    return [s for k in kids for s in _walk(k)]


def _leaf(tag: str, text: str, e: ET.Element) -> list[str]:
    text = "".join(ch for ch in text if ch not in _INVISIBLE and not ch.isspace()).translate(_ALIASES)
    # Note: a point is a raised dot, whether it is a decimal point, multiplies or ends a sentence.
    text = text.replace(".", "·")
    font = e.get("mathvariant")
    return [f"{_KEPT_FONTS[font]}:{ch}" if font in _KEPT_FONTS else ch for ch in text]


def _invisible(s: str | None) -> bool:
    """Whether `s` holds an invisible operator and nothing else visible."""
    return bool(s) and any(ch in _INVISIBLE for ch in s) and all(ch in _INVISIBLE or ch.isspace() for ch in s)


def spans(html: str) -> list[tuple[str, bool]]:
    """The math in an output, in order: each span's LaTeX (or MathML) and whether it is display math."""
    return [(tex, display) for tex, display, _, _ in _spans(_blocks(html))]


def _blocks(html: str) -> str:
    return _BLOCK.sub("\n", html)


def _spans(s: str) -> list[tuple[str, bool, int, int]]:
    """Each math span of `s` (`_blocks`): its LaTeX or MathML, whether it is display math, and where."""
    out = []
    for m in _SPANS.finditer(s):
        if m["m"] is not None:
            body, display = m["m"].strip(), "block" in (m["mattr"] or "")
            span = (f"<math>{body}</math>" if "<" in body else _html.unescape(body), display)
        elif m["bare"] is not None:
            if not _bare(tex := _html.unescape(m["bare"]).strip()): continue
            span = (tex, True)
        else:
            tex = next(m[g] for g in ("dd", "db", "ib", "i", "env", "pad") if m[g] is not None)
            span = (_html.unescape(_TAG.sub(" ", tex)), m["dd"] is not None or m["db"] is not None
                    or m["env"] is not None)
        out.append((*span, m.start(), m.end()))
    return out


def _bare(tex: str) -> bool:
    """Whether a line without delimiters is LaTeX: it has a command or a script, no prose word outside
    its braces, and renders."""
    if not _LATEX.search(tex) or "__" in tex: return False
    words = tex
    while (unbraced := _BRACED.sub(" ", words)) != words: words = unbraced
    return not _WORD.search(words) and symbols(tex, True) is not None


def _span_symbols(tex: str, display: bool) -> tuple[str, ...]:
    if tex.startswith("<math>"):
        return _from_mathml(f'<math xmlns="http://www.w3.org/1998/Math/MathML">{tex[6:-7]}</math>') or ()
    tex = _UNTAG.sub(" ", tex)
    # Note: a command KaTeX doesn't know is left out, not the whole span with it.
    for _ in range(_MAX_UNDEFINED):
        if (got := symbols(tex, display)) is not None: return got
        if not (m := _UNDEFINED.search(_katex().render(tex, display).get("error", ""))): break
        tex = re.sub(re.escape(m[1]) + r"(?![A-Za-z])", " ", tex)
    return ()


def _gap(text: str) -> list[str]:
    """The tokens for the text between two spans: a full stop, comma or semicolon just after the first,
    then whether the rest is whitespace (`_SOFT`) or prose (`_HARD`)."""
    text = views.text(text).lstrip()
    punct = [_GAP + _PUNCT[text[0]]] if text[:1] in _PUNCT else []
    return [*punct, _SOFT if not text[len(punct):].strip() else _HARD]


def appears(test_tex: str, html: str) -> tuple[bool, str]:
    r"""Whether the test's equation is in the output's math, and why not.

    Its spans (`$…$`, `$ … $` holding LaTeX, `$$…$$`, `\(…\)`, `\[…\]`, a bare `\begin{equation}`, `<math>`
    holding LaTeX or MathML, and a line of nothing but LaTeX) in order must hold the test's sequence unbroken.
    Two spans join only across whitespace and block tags, never prose; a comma, semicolon or full stop of the
    test's may stand between them, or just after the last, instead of inside ("$\rho_{AB}$, $\sigma$"); one
    ending the test may be left out at the end of a display formula; and a row break between display spans
    stands for the test's `\\`. The match is a whole expression: no letter, digit or sign before it continues
    its first term, and no letter, digit or script after it its last ("x+1=0" isn't in "-x+1=0", nor "E=mc"
    in "E=mc^2"). A span with a command KaTeX doesn't know is read without it. A different symbol, a missing
    or added index, exponent or term, or a dropped condition fails.
    """
    want = symbols(_UNTAG.sub(" ", test_tex), True)
    if want is None:
        return False, "the test's LaTeX doesn't render"
    want = _unnumber(want)
    if not want:
        return True, ""
    s = _blocks(html)
    hay, end, got = [_HARD], 0, 0
    for tex, display, start, stop in _spans(s):
        if not (part := _span_symbols(tex, display)): continue
        part = _unnumber(part) if display else part
        hay += [*(_gap(s[end:start]) if end else []), *part, *([_DISPLAY_END] if display else [])]
        end, got = stop, got + len(part)
    if not got:
        return False, "no math in the output"
    hay += [*_gap(s[end:]), _HARD]
    if _search(want, hay):
        return True, ""
    return False, f"equation not found ({len(want)} symbols; the output's math has {got})"


def _search(want: tuple[str, ...], hay: list[str], words: bool = False) -> bool:
    """Whether `hay` holds `want` as a whole expression, across soft gaps; with `words`, also not inside
    a word."""
    # Note: tokens are coded as one character each, so the match is a regex over strings.
    code: dict[str, str] = {}
    enc = lambda t: re.escape(code.setdefault(t, chr(0xE000 + len(code))))  # noqa: E731

    def one(t: str, last: bool) -> str:
        alts = [enc(t)]
        # Note: a full stop outside math ends the test's equation; it never multiplies.
        if t in _PUNCT.values() and (t != "·" or last): alts.append(enc(_GAP + t))
        # Note: a display formula may leave out the sentence's punctuation that ends it.
        if t in _PUNCT.values() and last: alts.append(f"(?={skip}{enc(_DISPLAY_END)})")
        if t == _ROW: alts.append(enc(_SOFT))
        return f"(?:{'|'.join(alts)})"

    if not (want := tuple(t for t in want if t != _SPACE)): return True
    skip = f"(?:{enc(_SOFT)}|{enc(_SPACE)}|{enc(_DISPLAY_END)})*"
    body = skip.join(one(t, i == len(want) - 1) for i, t in enumerate(want))
    text = "".join(enc(t) for t in hay)
    digits = "".join(c for t, c in code.items() if t.isdigit() or t == ".")
    signs = "".join(c for t, c in code.items() if t in _SIGNS)
    operators = "".join(c for t, c in code.items() if not _operand(t))
    scripts = "".join(c for t, c in code.items() if t in ("^(", "_(", "'"))
    # Note: a match is a whole expression: no digit continues a number it starts or ends with, no sign
    # before it negates its first term (one after an operand is a binary + or -), no script after it
    # raises its last; a letter beside it is a factor of a longer product, which a test may quote.
    letters = "".join(c for t, c in code.items() if words and t[-1:].isalnum() and not t.startswith(_GAP))
    edges = [f"(?<![{letters}])" if want[0][-1:].isalnum() and letters else "",
             f"(?<![{digits}])" if want[0].isdigit() and digits else "",
             f"(?<![{operators}][{signs}])" if want[0] not in _OPS and signs and operators else ""]
    ends = [f"(?![{letters}])" if want[-1][-1:].isalnum() and letters else "",
            f"(?![{digits}])" if want[-1].isdigit() and digits else "",
            f"(?![{scripts}])" if want[-1] not in _OPS and scripts else ""]
    return re.search("".join(edges) + body + "".join(ends), text) is not None


def _operand(t: str) -> bool:
    """Whether a token ends an operand, so a sign after it is binary."""
    return t[-1:].isalnum() and not t.startswith(_GAP) or t in (")", "]", "}", "|", "‖", "!", "'")


# Unicode's superscript and subscript characters, and what each writes.
_SCRIPTS = {ch: (kind, unicodedata.normalize("NFKC", ch))
            for ch in map(chr, range(0xA0, 0x2100))
            for kind, form in (("^(", "<super>"), ("_(", "<sub>"))
            if unicodedata.decomposition(ch).startswith(form)}
_HTML_SCRIPT = re.compile(r"<(sup|sub)\b[^<>]*>(.*?)</\1>", re.I | re.S)


def in_text(test_tex: str, html: str) -> bool:
    """Whether the test's equation is in the output's text, with its scripts written as scripts: the
    text read as symbols, each math span as what it renders ("ex$(n, C_5)$")."""
    want = symbols(_UNTAG.sub(" ", test_tex), True)
    if not want: return False
    s = _blocks(html)
    out, parts, end = [], {}, 0
    for tex, display, start, stop in _spans(s):
        parts[mark := chr(0xF0000 + len(parts))] = _span_symbols(tex, display)
        out += [s[end:start], mark]
        end = stop
    script = lambda m: f"{'^' if m[1].lower() == 'sup' else '_'}{{{m[2]}}}"  # noqa: E731
    s = _HTML_SCRIPT.sub(script, "".join(out) + s[end:])
    return _search(want, [_HARD, *_text_tokens(views.text(s), parts), _HARD], words=True)


def _text_tokens(text: str, parts: dict[str, tuple[str, ...]]) -> list[str]:
    """Text as symbols: what `symbols` makes of the same characters, a space as `_SOFT`, and each
    span's mark (`parts`) as its symbols."""
    out: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in parts:
            out += parts[ch]
        elif ch.isspace() or ch in _INVISIBLE:
            if out and out[-1] != _SOFT: out.append(_SOFT)
        elif ch in _SCRIPTS:
            kind = _SCRIPTS[ch][0]
            j = i
            while j < len(text) and text[j] in _SCRIPTS and _SCRIPTS[text[j]][0] == kind: j += 1
            out += [kind, *_chars("".join(_SCRIPTS[c][1] for c in text[i:j])), ")"]
            i = j
            continue
        elif ch in "^_" and i + 1 < len(text) and not text[i + 1].isspace():
            j = text.find("}", i) + 1 if text[i + 1] == "{" else i + 2
            j = j or len(text)
            out += [f"{ch}(", *_chars(text[i + 1:j].strip("{}")), ")"]
            i = j
            continue
        elif text.startswith("...", i):
            out.append("⋯")
            i += 3
            continue
        elif ch in "'′":
            out += ["^(", "'", ")"]
        elif ch == ".":
            decimal = 0 < i < len(text) - 1 and text[i - 1].isdigit() and text[i + 1].isdigit()
            out.append("·" if decimal else _GAP + "·")
        else:
            out += _chars(ch)
        i += 1
    return out


# Note: a dash stands for a minus in typewritten text.
_DASHES = str.maketrans(dict.fromkeys("‐‑‒–—―", "-"))


def _chars(s: str) -> list[str]:
    s = unicodedata.normalize("NFKC", s)
    s = s.translate(_ALIASES).translate(_DASHES)
    return [ch if ch != "." else _GAP + "·" for ch in s if not ch.isspace() and ch not in _INVISIBLE]
