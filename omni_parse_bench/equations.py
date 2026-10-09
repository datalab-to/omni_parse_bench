"""Equations as what they render: the math runner's comparison.

An equation is compared by what KaTeX renders it to, never by how its LaTeX is written. KaTeX turns
the LaTeX into MathML (`katex/katex.js`, run in one embedded V8 per process), where every
symbol is its final character (`\\to` and `\\rightarrow` are both →) and the structure is explicit:
fractions, scripts, roots, rows of an array. `symbols` walks that MathML into a flat sequence,
leaving out what doesn't change the equation:

    spacing                  \\quad, \\, and friends: dropped
    alignment                `&`, and how rows are split into cells: dropped; rows are kept
    fonts                    upright, italic and bold: dropped; blackboard, script and fraktur kept
    invisible operators      function application, invisible times: dropped
    look-alikes              ⩽ and ≤, ⩾ and ≥, ∥ and ‖, − and -, ′ and ', … and ⋯, ≔ and :=,
                             ∖ and a backslash, ♯ and #, ⋆ and *, a multiplying . and ·
    negations                a relation with a slash through it (\\not\\in) and its negated character (∉)
    restrictions             a | opening a subscript and a | just before it (φ_{|S} and φ|_S)
    constructions            `cases` and `\\left\\{ \\begin{aligned} … \\right.` render alike already

These equivalences were decided on real disagreements between the gold and vendors' outputs; the
differences judged real stay differences: \\bar and \\overline, \\setminus and a minus, one letter
font for another, a dropped blackboard font.

`appears(test, html)` says whether a test's equation is in an output: every math span of the
output (`$…$`, `$$…$$`, `\\(…\\)`, `\\[…\\]`, and `<math>` holding LaTeX or MathML) in order,
their sequences joined, must hold the test's sequence unbroken. A comma, semicolon or full stop
of the test's may fall between two of the output's spans instead ("$\\rho_{AB}$, $\\sigma$").
A different symbol, a missing or added index, exponent or term, or a dropped condition fails.
"""
from __future__ import annotations

import functools
import html as _html
import re
import threading
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

KATEX = Path(__file__).parent / "katex" / "katex.js"   # KaTeX 0.16.22, MIT (LICENSE beside it)
_RENDER = """(tex, display) => {
  try {
    return {mathml: katex.renderToString(tex, {output: "mathml", displayMode: display, strict: "ignore",
                                                throwOnError: true, trust: false})};
  } catch (e) {
    return {error: String(e.message || e).slice(0, 300)};
  }
}"""
_NS = "{http://www.w3.org/1998/Math/MathML}"
# Note: bold is dropped, so a bold script or fraktur letter is its plain script or fraktur letter.
_KEPT_FONTS = {"double-struck": "double-struck", "script": "script", "fraktur": "fraktur",
               "bold-script": "script", "bold-fraktur": "fraktur"}
_ALIASES = str.maketrans({"⩽": "≤", "⩾": "≥", "∥": "‖", "−": "-", "′": "'", "∣": "|", "⋅": ".",
                          "·": ".", "∗": "*", "⋆": "*", "ϵ": "ε", "ϕ": "φ", "ϑ": "θ", "∶": ":",
                          "…": "⋯", "\\": "∖", "♯": "#", "≔": ":=", "≕": "=:"})
_INVISIBLE = {"⁡", "⁢", "⁣", "⁤", "​"}
_DROPPED = {"mspace", "mphantom", "annotation", "annotation-xml", "none", "mprescripts"}
_SPANS = re.compile(r"\$\$(.+?)\$\$|\\\[(.+?)\\\]|\\\((.+?)\\\)|(?<![\\$])\$(?!\s)([^$\n]+?)(?<!\s)\$"
                    r"|<math\b([^<>]*)>(.*?)</math>", re.S | re.I)
_TAG = re.compile(r"<[^<>]+>")
_BOUNDARY = "\uffff"
_PUNCT = {",", ";", "."}


class _KaTeX:
    """KaTeX in an embedded V8 (mini-racer), shared by the threads of a scoring run."""

    def __init__(self) -> None:
        from py_mini_racer import MiniRacer

        # Note: a V8 context runs one call at a time, so the threads take turns.
        self.lock = threading.Lock()
        self.ctx = MiniRacer()
        self.ctx.eval(KATEX.read_text())
        self.ctx.eval(f"var render = {_RENDER}")

    def mathml(self, tex: str, display: bool) -> str | None:
        with self.lock:
            answer = self.ctx.call("render", tex, display)
        return answer.get("mathml")


@functools.cache
def _katex() -> _KaTeX:
    return _KaTeX()


@functools.lru_cache(maxsize=200_000)
def symbols(tex: str, display: bool = False) -> tuple[str, ...] | None:
    """What `tex` renders to, as a flat sequence of symbols and structure; None if it doesn't parse."""
    mathml = _katex().mathml(tex, display)
    return None if mathml is None else _from_mathml(mathml)


def _from_mathml(mathml: str) -> tuple[str, ...] | None:
    try:
        root = ET.fromstring(re.sub(r"^<span[^>]*>|</span>$", "", mathml.strip()))
    except ET.ParseError:
        return None
    return tuple(_canonical(_walk(root)))


def _canonical(xs: list[str]) -> list[str]:
    """A slash through a relation made its negated character, and a | opening a subscript moved
    before it."""
    out: list[str] = []
    for x in xs:
        if out and "\u0338" in (out[-1], x) and len(neg := unicodedata.normalize(
                "NFC", (x if out[-1] == "\u0338" else out[-1]) + "\u0338")) == 1:
            out[-1] = neg
        elif out and out[-1] == "_(" and x == "|":
            out[-1:] = ["|", "_("]
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
        text = "".join(ch for ch in (e.text or "") if ch not in _INVISIBLE and not ch.isspace())
        text = text.translate(_ALIASES)
        font = e.get("mathvariant")
        return [f"{_KEPT_FONTS[font]}:{ch}" if font in _KEPT_FONTS else ch for ch in text]
    if tag == "mfrac":
        num, den = (_walk(k) for k in kids[:2])
        name = "binom" if e.get("linethickness") in ("0", "0px", "0em") else "frac"
        return [f"{name}(", *num, ",", *den, ")"]
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
            out += [s for cell in row for s in _walk(cell)]
        return out
    return [s for k in kids for s in _walk(k)]


def _invisible(s: str | None) -> bool:
    """Whether `s` holds an invisible operator and nothing else visible."""
    return bool(s) and any(ch in _INVISIBLE for ch in s) and all(ch in _INVISIBLE or ch.isspace() for ch in s)


def spans(html: str) -> list[tuple[str, bool]]:
    """The math in an output, in order: each span's LaTeX (or MathML) and whether it is display math."""
    out = []
    for m in _SPANS.finditer(html):
        if m[6] is not None:
            body, display = m[6].strip(), "block" in (m[5] or "")
            if "<" in body:
                out.append((f"<math>{body}</math>", display))
            else:
                out.append((_html.unescape(body), display))
        else:
            tex = next(g for g in m.groups()[:4] if g is not None)
            out.append((_html.unescape(_TAG.sub(" ", tex)), m[1] is not None or m[2] is not None))
    return out


def _span_symbols(tex: str, display: bool) -> tuple[str, ...]:
    if tex.startswith("<math>"):
        return _from_mathml(f'<math xmlns="http://www.w3.org/1998/Math/MathML">{tex[6:-7]}</math>') or ()
    return symbols(tex, display) or ()


def appears(test_tex: str, html: str) -> tuple[bool, str]:
    """Whether the test's equation is in the output's math, and why not."""
    want = symbols(test_tex, True)
    if want is None:
        return False, "the test's LaTeX doesn't render"
    if not want:
        return True, ""
    parts = [_span_symbols(tex, display) for tex, display in spans(html)]
    got = [s for p in parts for s in p]
    if not got:
        return False, "no math in the output"
    # Note: symbols are coded as one character each, so the match is a regex over strings; a span
    # boundary is its own character, skipped anywhere, and standing in for the test's punctuation.
    code: dict[str, str] = {}
    enc = lambda s: code.setdefault(s, chr(0xE000 + len(code)))  # noqa: E731
    hay = _BOUNDARY.join("".join(enc(s) for s in p) for p in parts)
    one = lambda s: f"(?:{re.escape(enc(s))}|{_BOUNDARY})" if s in _PUNCT else re.escape(enc(s))  # noqa: E731
    pattern = f"{_BOUNDARY}*".join(one(s) for s in want)
    if re.search(pattern, hay):
        return True, ""
    return False, f"equation not found ({len(want)} symbols; the output's math has {len(got)})"
