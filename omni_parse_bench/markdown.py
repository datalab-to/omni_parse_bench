"""Markdown to HTML: the one converter every provider's markdown goes through.

    markdown.to_html("# Title\\n\\n29. Item")   # -> "<h1>Title</h1>\\n<p>29. Item</p>\\n"

It's markdown-it (commonmark, with tables, strikethrough and raw HTML) plus repairs for page text
a plain conversion loses, applied in this order:

    a fence around the page   removed: LLMs often open with ```markdown and never close it,
                              which would turn the whole page into one code block; a fenced
                              code listing inside the page is kept, as code
    YAML front matter         removed: it's transport, not page text; a page that opens with a
                              rule (---) is not front matter
    page-wide indentation     removed: a page indented inside its fence isn't a code block
    "29." / "1)" / "- "       escaped: the marker is page text, but commonmark moves a number
                              into <ol start> and drops a bullet; not inside code or a raw
                              HTML block, where markdown-it would leave the backslash
    <name@host>               escaped: an address printed in brackets is text, not a mail link
    [1]: url                  kept: a reference list is page text, not link definitions
    <table>..</table>, $..$   held while markdown-it runs: a blank line ends its HTML block, and
                              it eats the braces of $\\{x\\}$; in a table row, only LaTeX spans a |
"""
from __future__ import annotations

import functools
import re
import textwrap

from omni_parse_bench import views

_FENCE = re.compile(r"[ \t]*```([A-Za-z]*)[ \t]*")
_WRAPPERS = ("", "markdown", "md", "html")
_FRONT_MATTER = re.compile(r"^\s*---[ \t]*\n(?:[ \t]*[A-Za-z_][\w-]*:.*\n)+---[ \t]*(?:\n|$)")
_CODE = re.compile(r"(?ms)^[ \t]*```[^\n]*\n.*?^[ \t]*```[ \t]*$|`[^`\n]+`")
_EMAIL = re.compile(r"<(?=[^<>\s@]+@[^<>\s@]+>)")
_OL_MARKER = re.compile(r"(?m)^([ \t]{0,3}\d{1,9})([.)])(?=[ \t]|$)")
_UL_MARKER = re.compile(r"(?m)^([ \t]{0,3})([-+*])(?=[ \t])")
_TABLE = re.compile(r"<table\b.*?</table>", re.S | re.I)
# Note: commonmark's HTML block tags, and pre: markdown-it reads no escapes inside them.
_HTML_ELEMENT = re.compile(
    r"<(figure|table|div|details|section|aside|p|pre|blockquote|ul|ol|li|dl|center|form|header|footer|"
    r"article|main|nav|fieldset|figcaption)\b.*?</\1\s*>", re.S | re.I)
_DISPLAY_MATH = re.compile(r"\$\$.+?\$\$|\\\[.+?\\\]", re.S)
# Note: an escaped dollar (\$5) is a price, neither end of math.
_INLINE_MATH = re.compile(r"(?<!\\)\$(?!\s)[^$\n]+?(?<![\s\\])\$|\\\(.+?\\\)", re.S)
# In a table row, $..$ crosses a bare | only if it holds \ ^ _ or {: "$2.5 | ($27.8)" is two cells.
_ROW_MATH = re.compile(r"(?<!\\)\$(?!\s)(?:(?=[^$\n]*[\\^_{])[^$\n]+?|[^$\n|]+?)(?<![\s\\])\$|\\\(.+?\\\)",
                       re.S)
_ROWS = re.compile(r"(?m)((?:^[ \t]*\|.*(?:\n|$))+)")  # runs of table-row lines


def to_html(md: str) -> str:
    """HTML for a page given as markdown."""
    md = unwrapped(md)
    md = _FRONT_MATTER.sub("", md, count=1)
    md = textwrap.dedent(md)
    # Note: markdown-it reads no escapes in code or inside a raw HTML element, so one added there would stay.
    md, raw = views.hold(md, _HTML_ELEMENT)
    md, raw = views.hold(md, _CODE, raw)
    md = _OL_MARKER.sub(r"\1\\\2", md)
    md = _UL_MARKER.sub(r"\1\\\2", md)
    md = _EMAIL.sub("&lt;", md)
    md = views.release(md, raw)
    md, held = views.hold(md, _TABLE)
    # Note: display math first, so a line of it starting with | isn't read as a table row.
    md, held = views.hold(md, _DISPLAY_MATH, held)
    parts = _ROWS.split(md)  # text, rows, text, rows, ...
    for i, part in enumerate(parts):
        parts[i], held = views.hold(part, _ROW_MATH if i % 2 else _INLINE_MATH, held)
    md = "".join(parts)
    return views.release(_renderer().render(md), held)


def unwrapped(md: str) -> str:
    """`md` without a fence around the whole page, closed or not. A first fence that names another
    language opens a code listing, kept, as does a bare one that closes before the page ends; words
    after a fence naming markdown or html ("Let me know ...") aren't the page."""
    lines = md.strip().split("\n")
    if not (m := _FENCE.fullmatch(lines[0])) or m[1].lower() not in _WRAPPERS: return md
    fences = [i for i, line in enumerate(lines) if _FENCE.fullmatch(line)]
    if len(fences) % 2: return "\n".join(lines[1:])
    return "\n".join(lines[1:fences[-1]]) if m[1] or fences[-1] == len(lines) - 1 else md


@functools.cache
def _renderer():
    from markdown_it import MarkdownIt

    return MarkdownIt("commonmark", {"html": True}).enable(["table", "strikethrough"]).disable("reference")
