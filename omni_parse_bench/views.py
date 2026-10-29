"""What a reader sees in an output, built once per output:

- `html` and `Html`: an HTML output's three views;
- `blocks` and `Block`: a layout output's blocks;
- `MalformedOutput`: an output of the wrong shape, which fails that output's tests; and
- `hold` and `release`: let a rewrite step around spans it must not touch.
"""
from __future__ import annotations

import html as _html
import re
from typing import NamedTuple

HOLD_OPEN, HOLD_CLOSE = "\ue000", "\ue001"
CHECKED, UNCHECKED = "☒", "☐"

_HELD = re.compile(HOLD_OPEN + r"(\d+)" + HOLD_CLOSE)
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
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_DOCTYPE = re.compile(r"<!DOCTYPE[^>]*>", re.I)
# Note: <head> and <title> hold a document's metadata, which a browser never shows on the page.
_SCRIPT = re.compile(r"<(script|style|head|title)\b.*?</\1>", re.S | re.I)
_BLOCK = re.compile(
    r"</?(?:table|thead|tbody|tfoot|tr|td|th|p|div|li|ul|ol|dl|dt|dd|h[1-6]|br|hr|section|article|"
    r"figure|figcaption|blockquote|pre|caption|header|footer|nav|aside|form|label|select|option|"
    r"textarea|img)\b[^<>]*>",
    re.I,
)
# Note: a footnote marker or exponent set as <sup> would otherwise become digits of the number it
# follows ("1,240<sup>1</sup>" read as 1,2401); a text test still finds "x2" in "x 2" by `squeeze`.
_SUP = re.compile(r"<sup\b[^<>]*>", re.I)
# Note: a tag must start with a letter and hold no stray `<` or `>`, so "P < 0.05" and
# "<name@example.com>" survive as text.
_INLINE = re.compile(r"</?[A-Za-z][A-Za-z0-9-]*(?:\s[^<>]*)?/?>")


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
        v.text    # what a reader sees, image alt text included: tests that credit text read it
        v.seen    # the text view without alt text: tests that fault extra text read it

    The text view is the HTML with these rewrites, in this order:

        <math>..</math>           -> $..$, or $$..$$ when display="block"
        <ol> items                -> each item's number written before it
        checkbox / radio input    -> ☒ if checked, else ☐
        <checked>, <unchecked>    -> ☒, ☐ (a vendor's own checkbox tags)
        <input value="v">         -> v
        <img alt="a">, ![a](..)   -> a
        comments, doctype, script, style, head, title -> removed
        <sup>                     -> a space, so a superscript never joins what it follows ("1,240 1")
        block tags                -> a space
        inline tags               -> removed
        entities                  -> unescaped"""
    if not isinstance(s, str):
        raise MalformedOutput(f"html must be a string, not {type(s).__name__}: {s!r:.80}")
    return Html(s, text(s), text(s, alt=False))


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
    s = _MATH.sub(_math, s)
    if "<ol" in s.lower(): s = _numbered(s)
    s = _CONTROL.sub(lambda m: f" {CHECKED if _CHECKED_ATTR.search(m[0]) else UNCHECKED} ", s)
    s = _BOX_TAG.sub(lambda m: f" {UNCHECKED if m[1] else CHECKED} ", s)
    s = _INPUT_VALUE.sub(lambda m: f" {_quoted(m)} ", s)
    s = _IMG_ALT.sub(lambda m: f" {_quoted(m)} " if alt else " ", s)
    s = _MD_IMAGE.sub(lambda m: f" {m[1]} " if alt else " ", s)
    for pattern in (_COMMENT, _DOCTYPE, _SCRIPT):
        s = pattern.sub(" ", s)
    s = _INLINE.sub("", _BLOCK.sub(" ", _SUP.sub(" ", s)))
    return _html.unescape(s)


def hold(s: str, pattern: re.Pattern[str], held: list[str] | None = None) -> tuple[str, list[str]]:
    """Replaces each match of `pattern` with a placeholder; returns the text and what was held."""
    held = [] if held is None else held

    def one(m: re.Match[str]) -> str:
        held.append(m[0])
        return f"{HOLD_OPEN}{len(held) - 1}{HOLD_CLOSE}"

    return pattern.sub(one, s), held


def release(s: str, held: list[str]) -> str:
    """Puts back what `hold` took out."""
    # Note: recursive, as a later match can hold an earlier placeholder: inline math `$,$$x$$y$` spans the
    # display math held before it.
    return _HELD.sub(lambda m: release(held[int(m[1])], held), s) if held else s


def _numbered(s: str) -> str:
    """`s` with each <li> of an <ol> preceded by the number a browser draws for it ("3. "), from the
    list's `start`, so an HTML list keeps the numbers a markdown one writes as text."""
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

    return _LIST_TAG.sub(one, s)


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
