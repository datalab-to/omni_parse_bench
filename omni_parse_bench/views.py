"""What a reader sees in an output, built once per output:

- `html` and `Html`: an HTML output's three views;
- `blocks` and `Block`: a layout output's blocks;
- `MalformedOutput`: an output of the wrong shape, which fails that output's tests; and
- `hold` and `release`: let a rewrite step around spans it must not touch.
"""
from __future__ import annotations

import functools
import html as _html
import re
from typing import NamedTuple

from . import switches

HOLD_OPEN, HOLD_CLOSE = "\ue000", "\ue001"
CHECKED, UNCHECKED = "☒", "☐"

_HELD = re.compile(HOLD_OPEN + r"(\d+)" + HOLD_CLOSE)
_NO_MARKERS = {ord(HOLD_OPEN): None, ord(HOLD_CLOSE): None}
_LIST_TAG = re.compile(r"<(/?)(ol|ul|li)\b([^<>]*)>", re.I)
_START = re.compile(r"\bstart=[\"']?(\d+)", re.I)
_MATH = re.compile(r"<math\b([^<>]*)>(.*?)</math>", re.I | re.S)
_TEX_ANNOTATION = re.compile(
    r"<annotation\b[^<>]*encoding=[\"']application/x-tex[\"'][^<>]*>(.*?)</annotation>", re.I | re.S)
_CONTROL = re.compile(r"<input\b[^<>]*\btype=[\"']?(?:checkbox|radio)[\"']?[^<>]*>", re.I)
_CHECKED_ATTR = re.compile(r"\bchecked\b", re.I)
_BOX_TAG = re.compile(r"<(un)?checked\s*/?>", re.I)
_INPUT_VALUE = re.compile(r"<input\b[^<>]*?\bvalue=(\"([^\"]*)\"|'([^']*)')[^<>]*>", re.I)
_IMG_ALT = re.compile(r"<img\b[^<>]*\balt=(\"([^\"]*)\"|'([^']*)')[^<>]*>", re.I)
_MD_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
# Note: a comment is removed with nothing in its place, as a browser draws it: "12<!-- -->5" reads "125".
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_DOCTYPE = re.compile(r"<!DOCTYPE[^>]*>", re.I)
# Note: <head> and <title> hold a document's metadata, which a browser never shows on the page.
_SCRIPT = re.compile(r"<(script|style|head|title)\b.*?</\1>", re.S | re.I)
# Note: a tag's attributes end at the first ">" outside a quoted value, so the ">" of title="a>b" does not end
# the tag; a value is quoted only right after "=", as in a browser. A quoted value holds no "<", so a quote
# left open never runs on across later tags: it falls back to ending at the next ">". The loop is possessive,
# so a "<" that starts no tag costs one pass.
_ATTRS = r"""(?:=\s*(?:"[^"<]*"|'[^'<]*')|[^<>])*+"""
_BLOCK = re.compile(
    r"</?(?:table|thead|tbody|tfoot|tr|td|th|p|div|li|ul|ol|dl|dt|dd|h[1-6]|br|hr|section|article|"
    r"figure|figcaption|blockquote|pre|caption|header|footer|nav|aside|form|label|select|option|"
    rf"textarea|img)(?:\s{_ATTRS})?/?>",
    re.I,
)
# Note: a tag has a tag's shape: its name, then attributes with no "<" in them outside quotes, then ">", so
# the "<p" of "p<q\leq r ... )>0" is no tag (`_INLINE`, `_BLOCK`, `_SUP`). A name may hold a namespace prefix,
# as Word's <o:p> and <w:sdt> do.
_TAG = rf"</?[A-Za-z][A-Za-z0-9:-]*(?:\s{_ATTRS})?/?>"
# Note: a "<" before a letter that starts no tag is text, and is escaped before any tag is removed: else
# removing the block tags after it ("<p>p <q</p><p>Total due</p><p>r> s</p>") would join it to a later ">"
# into one tag shape that swallows every block between. `unescape` puts the "<" back last.
_STRAY_LT = re.compile(rf"<(?=/?[A-Za-z])(?!{_TAG[1:]})")
# Note: a block tag breaks the line, so a math span never crosses one ("<p>$5</p><p>$$x$$</p>"); a <br> or
# an image may sit inside a span, and a reader sees them as a space.
_LINE_BREAKING = re.compile(
    r"</?(?:table|thead|tbody|tfoot|tr|td|th|p|div|li|ul|ol|dl|dt|dd|h[1-6]|section|article|figure|"
    r"figcaption|blockquote|pre|caption)\b", re.I)


# Note: U+2029, a paragraph separator: white space to everything that reads the text, and no line start to a
# pattern anchored on "\\n" (a bullet opening a block is not a bullet opening a line).
BREAK = "\u2029"


def _block_break(m: re.Match[str]) -> str:
    return BREAK if _LINE_BREAKING.match(m[0]) else " "


# Note: a footnote marker or exponent set as <sup> would otherwise become digits of the number it
# follows ("1,240<sup>1</sup>" read as 1,2401), or of the number right after it ("<sup>1</sup>1,240" read as
# 11,240, "<sup>1</sup>-4.8" as 1-4.8, a hyphen and no sign), so the opening tag is a space, and so is the
# closing one before a number: a digit, or a sign or point and a digit, past any tags. A text test still finds
# "x2" in "x 2" by `squeeze`.
_SUP = re.compile(rf"<sup(?:\s{_ATTRS})?/?>", re.I)
_SUP_END = re.compile(rf"</sup\s*>(?=(?:{_TAG})*[-+±‐-―−.]?\d)", re.I)
# Note: a tag must start with a letter and hold no stray `<` or `>`, so "P < 0.05" and
# "<name@example.com>" survive as text.
_INLINE = re.compile(_TAG)
# A footnote mark set as a superscript: a <sup> holding only one to three ASCII digits or one to three of
# the footnote symbols * † ‡ § ¶ #, inline tags (a link) and white space aside. One right after a digit is no
# mark (`_drop_mark`): it is an exponent ("10<sup>5</sup>"), or a mark that must not let its number join
# what follows. Math writes its exponents with `^`, `<msup>` or a superscript character, never this tag.
_FOOTNOTE_MARK = re.compile(
    rf"<sup(?:\s{_ATTRS})?>(?:\s|{_TAG})*(?:[0-9]{{1,3}}|[*†‡§¶#]{{1,3}})(?:\s|{_TAG})*</sup\s*>", re.I)


# A block's kind. Each adapter maps its vendor's types onto these in a table a person decides; a vendor
# with no type for a kind never says it (docs/providers.md).
LABELS = ("text", "heading", "page_furniture", "list", "caption", "footnote", "equation", "code",
          "table", "form", "figure")

Box = tuple[float, float, float, float]   # x0, y0, x1, y1, from 0 to 1, origin top-left


class MalformedOutput(ValueError):
    """An output whose shape a view can't read (HTML that isn't a string, a block that isn't `{label,
    bbox[, text]}`): the system's fault, so that output's tests fail. Any other exception while grading is
    a bug in the scorer."""


class Html(NamedTuple):
    html: str
    text: str
    seen: str   # `text` without image alt text: what shows where the images are drawn


class Block(NamedTuple):
    label: str
    bbox: Box
    text: str


def html(s: str) -> Html:
    """The three views of one HTML output; raises `MalformedOutput` when `s` isn't a string. A runner reads
    these, never raw HTML for text:

        v = views.html("<p>Let <b>x</b> be</p>")
        v.html    # the HTML itself: table_cell tests parse it
        v.text    # what a reader sees, alt text included (unless `alt_text_out`): tests crediting text use it
        v.seen    # the text view without alt text: tests that fault extra text read it

    The text view is the HTML with these rewrites, in this order:

        <math>..</math>           -> $..$, or $$..$$ when display="block"
        <ol> items                -> each item's number written before it
        checkbox / radio input    -> ☒ if checked, else ☐
        <checked>, <unchecked>    -> ☒, ☐ (a vendor's own checkbox tags)
        <input value="v">         -> v
        <img alt="a">, ![a](..)   -> a
        comments                  -> removed
        doctype, script, style, head, title -> a space
        "<" before a letter that starts no tag -> kept as text
        <sup>                     -> a space, so a superscript never joins what it follows ("1,240 1")
        </sup> before a number    -> a space, so it never joins the number after it either
        block tags                -> a space
        inline tags               -> removed
        entities                  -> unescaped"""
    if not isinstance(s, str):
        raise MalformedOutput(f"html must be a string, not {type(s).__name__}: {s!r:.80}")
    hide, alt_out = switches.on("visibility"), switches.on("alt_text_out")
    if hide or alt_out:
        from . import reader     # the reader's one parser takes out what a page hides and image alt text
        s = reader.visible_html(s, hidden=hide, alt=alt_out)
    return Html(s, text(s, alt=not alt_out), text(s, alt=False))


def blocks(raw: list) -> tuple[Block, ...]:
    """The blocks of one `blocks` output, each `{label, bbox[, text]}`, as `Block`s. Raises
    `MalformedOutput` on an output that isn't a list of such objects, or a block whose label isn't one of
    `LABELS`, whose box isn't four numbers from 0 to 1, or whose text isn't a string."""
    if not isinstance(raw, list):
        raise MalformedOutput(f"blocks must be a list, not {type(raw).__name__}: {raw!r:.80}")
    out = []
    for i, b in enumerate(raw):
        if not (isinstance(b, dict) and {"label", "bbox"} <= set(b) <= {"label", "bbox", "text"}):
            raise MalformedOutput(f"block {i} isn't an object of label, bbox and text: {b!r:.80}")
        label, bbox, text = b["label"], b["bbox"], b.get("text")
        if not (isinstance(label, str) and label in LABELS):
            raise MalformedOutput(f"block {i}: label {label!r} isn't one of {LABELS}")
        if not (isinstance(bbox, (list, tuple)) and len(bbox) == 4 and all(
                isinstance(x, (int, float)) and not isinstance(x, bool) and 0 <= x <= 1 for x in bbox)):
            raise MalformedOutput(f"block {i}: bbox {bbox!r:.80} isn't four numbers from 0 to 1")
        if not (text is None or isinstance(text, str)):
            raise MalformedOutput(f"block {i}: text must be a string or null, not {text!r:.80}")
        out.append(Block(label, tuple(bbox), text or ""))
    return tuple(out)


def text(s: str, *, alt: bool = True) -> str:
    """The text a reader sees; without `alt`, image alt text is left out."""
    return reading(Seq(s), alt=alt).s


class Seq:
    """A string and, when it tracks its source, where each character came from: `lo[i]:hi[i]` is the stretch
    of the source that character `i` stands for. A rewrite (`sub`) keeps the sources of what it leaves and
    gives what it writes the source of what it replaced, so a position in the text maps back (`source`)."""
    __slots__ = ("s", "lo", "hi")

    def __init__(self, s: str, lo: list[int] | None = None, hi: list[int] | None = None) -> None:
        self.s, self.lo, self.hi = s, lo, hi

    @classmethod
    def tracking(cls, s: str) -> Seq:
        return cls(s, list(range(len(s))), list(range(1, len(s) + 1)))

    def sub(self, pattern: re.Pattern[str], repl, placed: list[tuple[int, int]] | None = None) -> Seq:
        """`pattern.sub(repl, s)`, `repl` a string with no group references or a function of the match. With
        `placed`, the stretch each replacement takes in the result is appended to it."""
        if self.lo is None and placed is None:
            return Seq(pattern.sub(repl, self.s))
        s, parts, lo, hi, i, n = self.s, [], [], [], 0, 0
        for m in pattern.finditer(s):
            a, b = m.span()
            r = repl(m) if callable(repl) else repl
            parts += [s[i:a], r]
            n += a - i
            if placed is not None: placed.append((n, n + len(r)))
            n += len(r)
            if self.lo is not None:
                lo += self.lo[i:a]
                hi += self.hi[i:a]
                if r == s[a:b]:    # left as it was: each character keeps its own source
                    lo += self.lo[a:b]
                    hi += self.hi[a:b]
                    i = b
                    continue
                if a < b: first, last = self.lo[a], self.hi[b - 1]
                else: first = last = self.lo[a] if a < len(self.lo) else (self.hi[-1] if self.hi else 0)
                lo += [first] * len(r)
                hi += [last] * len(r)
            i = b
        if i == 0 and not parts: return self
        parts.append(s[i:])
        if self.lo is None: return Seq("".join(parts))
        return Seq("".join(parts), lo + self.lo[i:], hi + self.hi[i:])

    def source(self, start: int, end: int) -> tuple[int, int]:
        """The stretch of the source that `s[start:end]` stands for."""
        return self.lo[start], self.hi[end - 1]


# The pattern `html.unescape` reads references with.
_CHARREF = re.compile(r"&(#[0-9]+;?|#[xX][0-9a-fA-F]+;?|[^\t\n\f <&#;]{1,32};?)")


def reading(q: Seq, *, alt: bool = True, marks: bool = True) -> Seq:
    """What `text` writes, on a `Seq`: the same rewrites, so a tracking one says where in the HTML each
    character of the text came from. Without `marks`, each footnote mark set as a superscript
    (`_FOOTNOTE_MARK`) is a space (`unmarked`)."""
    q = q.sub(_MATH, _math)
    if "<ol" in q.s.lower(): q = q.sub(_LIST_TAG, _numbering())
    q = q.sub(_CONTROL, lambda m: f" {CHECKED if _CHECKED_ATTR.search(m[0]) else UNCHECKED} ")
    q = q.sub(_BOX_TAG, lambda m: f" {UNCHECKED if m[1] else CHECKED} ")
    q = q.sub(_INPUT_VALUE, lambda m: f" {_quoted(m)} ")
    q = q.sub(_IMG_ALT, lambda m: f" {_quoted(m)} " if alt else " ")
    q = q.sub(_MD_IMAGE, lambda m: f" {m[1]} " if alt else " ")
    q = q.sub(_COMMENT, "")
    for pattern in (_DOCTYPE, _SCRIPT):
        q = q.sub(pattern, " ")
    q = q.sub(_STRAY_LT, "&lt;")
    if not marks: q = q.sub(_FOOTNOTE_MARK, _drop_mark)
    q = q.sub(_SUP, " ").sub(_SUP_END, " ").sub(_BLOCK, _block_break).sub(_INLINE, "")
    if q.lo is None: return Seq(_html.unescape(q.s))
    return q.sub(_CHARREF, lambda m: _html.unescape(m[0]))


@functools.lru_cache(maxsize=256)
def unmarked(s: str) -> str | None:
    """The text view with each footnote mark set as a superscript read as a space, not as its digits or
    symbol ("Probiotic<sup>1</sup> strains" -> "Probiotic  strains"); None when `s` has no such mark. A mark
    right after a digit stays, as in `text` ("10<sup>5</sup>" is an exponent)."""
    if not _FOOTNOTE_MARK.search(s): return None
    return reading(Seq(s), marks=False).s


def _drop_mark(m: re.Match[str]) -> str:
    """A footnote mark as a space, unless a digit comes right before it, past any tags."""
    s, i = m.string, m.start()
    while i and s[i - 1] == ">" and (j := s.rfind("<", 0, i - 1)) >= 0 and _INLINE.fullmatch(s, j, i):
        i = j
    return m[0] if i and s[i - 1].isdecimal() else " "


def hold(s: str, pattern: re.Pattern[str], held: list[str] | None = None) -> tuple[str, list[str]]:
    """Replaces each match of `pattern` with a placeholder; returns the text and what was held."""
    # Note: a fresh hold drops the marker characters the text already has, so only ours are ever released;
    # they are private-use, which `normalize.fold` drops anyway.
    if held is None: s, held = s.translate(_NO_MARKERS), []

    def one(m: re.Match[str]) -> str:
        held.append(m[0])
        return f"{HOLD_OPEN}{len(held) - 1}{HOLD_CLOSE}"

    return pattern.sub(one, s), held


def release(s: str, held: list[str]) -> str:
    """Puts back what `hold` took out."""
    # Note: an item may hold placeholders made before it (inline math `$,$$x$$y$` spans the display math held
    # first), so items are put back in order, each from the ones already put back.
    out: list[str] = []
    for x in held: out.append(_HELD.sub(lambda m: out[int(m[1])], x))
    return _HELD.sub(lambda m: out[int(m[1])], s) if held else s


def _numbering():
    """The rewrite of each <li> of an <ol> to itself preceded by the number a browser draws for it ("3. "),
    from the list's `start`, so an HTML list keeps the numbers a markdown one writes as text."""
    stack: list[list[int]] = []   # per open list: [is_ordered, next number]

    def one(m: re.Match[str]) -> str:
        close, tag, attrs = m[1], m[2].lower(), m[3]
        if tag in ("ol", "ul"):
            if close:
                if stack: stack.pop()
            else:
                start = _START.search(attrs) if tag == "ol" else None
                stack.append([tag == "ol", int(start[1]) if start else 1])
            return m[0]
        if close or not stack or not stack[-1][0]: return m[0]
        n = stack[-1][1]
        stack[-1][1] += 1
        return f"{m[0]}{n}. "

    return one


def mathml_only(body: str) -> bool:
    """Whether a <math> element's body is MathML with no TeX in it: the text view reads it as its text, not as
    `$..$`."""
    return "<" in body and not _TEX_ANNOTATION.search(body)


def _math(m: re.Match[str]) -> str:
    """A <math> element as $..$ LaTeX: its TeX annotation, or its body when that is LaTeX. MathML
    markup without one is read as its text, since there is no LaTeX to fold."""
    body = m[2].strip()
    if tex := _TEX_ANNOTATION.search(body): body = _html.unescape(tex[1].strip())
    elif "<" in body: return f" {_html.unescape(re.sub(r'<[^<>]+>', '', body))} "
    return f" $${body}$$ " if "block" in m[1] else f"${body}$"


def _quoted(m: re.Match[str]) -> str:
    """The value of a `(\"..\"|'..')` attribute group, whichever quote it used."""
    return m[2] if m[2] is not None else m[3]
