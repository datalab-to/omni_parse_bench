"""The marks an output's text carries: bold, italic, underline, strikethrough, superscript, subscript.

The text view (`views.html(...).text`) drops tags, and `present` is certified to give the same verdict
with an answer wrapped in `<b>` or not (M7a). A `format` test asks the opposite question, so it reads this
module instead: the same words, each character with the set of marks the output's markup puts on it.

    m = marks.read("<p>the <b>total</b> due</p>")
    m.text      # "thetotaldue": folded, no spaces
    m.marks[3]  # frozenset({"bold"})

What a mark is:

    bold        <b>, <strong>, font-weight bold or 600 and over, `font: bold ...`
    italic      <i>, <em>, font-style italic or oblique, `font: italic ...`
    underline   <u>, <ins>, text-decoration underline
    strike      <s>, <strike>, <del>, text-decoration line-through
    sup, sub    <sup>, <sub>, vertical-align super or sub (the style wins over the element)

An element that is a mark by default is a mark: `<ins>` is underlined and `<del>` struck through whatever
a page's style sheet says, and the reader does not read one. A style that draws the text plain
(`font-weight: normal`, `font-style: normal`, a `font` shorthand without the weight or the style) takes bold
or italic off, as a browser does. On an element's own mark, `text-decoration: none` takes off its underline
or strikethrough and `vertical-align: baseline` its script (`<u style="text-decoration: none">` is plain
text); neither takes off a mark an ancestor makes, as in a browser.

Markdown is a vendor's output: the harness turns it into HTML (`markdown.to_html`) before any test reads
it, so `**x**` and `<strong>x</strong>` are the same marks by construction, and an HTML tag inside the
markdown (`H<sub>2</sub>O`) is read as HTML. Markdown has no superscript or subscript and no single-tilde
strikethrough, so a markdown-only output cannot carry them. Not a mark: a heading or `<th>` (drawn bold, not
marked), `<mark>`, `<a>`, `<kbd>`, Unicode superscript characters, and LaTeX. Text inside `<math>` carries
no mark, and nothing in `<script>`, `<style>`, `<head>`, `<title>`, a comment or a doctype is read at all
(the same elements `views.html` hides). An unclosed `<head>` ends at the first tag or text a head does not
hold, and an unclosed `<title>` at the first tag.

The text is compared as the fold of the character forms (`normalize.typography`: dashes, quotes, spaces,
compatibility forms), case-folded, NFC, with no whitespace: the fold `format` uses is that and no more (no
footnote, hyphen, bullet or math rule), so a character's marks are easy to keep through it. A run is
folded as a whole, so a character form that spans two runs (a combining accent, two apostrophes that fold
to a quotation mark, an arrow written in two characters) is read as written when a mark boundary falls
inside it: a known limitation (M57b)."""
from __future__ import annotations

import collections
import functools
import re
import unicodedata
from html.parser import HTMLParser
from typing import NamedTuple

from omni_parse_bench import normalize

KINDS = ("bold", "italic", "underline", "strike", "sup", "sub")
# Note: the most mark elements an end tag that crosses them puts back on: a page of 20,000 is not read twice
REOPEN = 16

# element -> the mark it makes
TAGS = {"b": "bold", "strong": "bold", "i": "italic", "em": "italic", "u": "underline", "ins": "underline",
        "s": "strike", "strike": "strike", "del": "strike", "sup": "sup", "sub": "sub"}
# elements whose content is not text the page shows: the ones `views.html` hides too
HIDDEN = frozenset({"script", "style", "head", "title"})
# elements whose text is read but carries no mark
INERT = frozenset({"math"})
# a void element has no end tag, so it must not be pushed
VOID = frozenset(
    {"br", "hr", "img", "input", "meta", "link", "col", "wbr", "area", "base", "embed", "source", "track"}
)
# the elements a head may hold: a start tag of any other ends an unclosed head
HEAD = frozenset({"head", "title", "meta", "link", "style", "script", "base", "noscript", "template"})
_NUMBER = re.compile(r"\d+")


class Marked(NamedTuple):
    """An output's text as `fold` leaves it, and the marks on each of its characters."""
    text: str
    marks: tuple[frozenset[str], ...]
    emitted: bool   # whether some character of the text carries a mark


def fold(s: str) -> str:
    """What a format test compares: the typography fold, NFC, case-folded, with no whitespace."""
    return "".join(unicodedata.normalize("NFC", normalize.typography(s)).casefold().split())


def letters(s: str) -> int:
    """How many letters and digits `s` has once folded: a span of punctuation or combining marks has none."""
    return sum(c.isalnum() for c in fold(s))


def _bold(word: str) -> bool | None:
    """Whether a font weight is bold (True), plain (False) or not one (None)."""
    if word in ("bold", "bolder"):
        return True
    if word in ("normal", "lighter"):
        return False
    return int(word) >= 600 if _NUMBER.fullmatch(word) else None


def style_marks(style: str) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    """What an inline `style` attribute does to marks: the ones it adds, the ones it takes off the text, and
    the ones it takes off the element's own default mark. Bold and italic can be taken off the text
    (`font-weight: normal` inside a `<b>`, and a `font` shorthand that names no weight or style); an
    underline, a strikethrough or a script only off the element that makes it
    (`<u style="text-decoration: none">`), since a browser draws one an ancestor makes whatever the style
    says. `vertical-align` replaces the other script: a `<sup style="vertical-align: sub">` is a subscript."""
    add: set[str] = set()
    drop: set[str] = set()
    own: set[str] = set()
    for decl in style.lower().split(";"):
        name, _, value = decl.partition(":")
        name, value = name.strip(), value.replace("!important", "").strip()
        words = value.split()
        if name == "font-weight" and words:
            (add if _bold(words[0]) else drop if _bold(words[0]) is False else set()).add("bold")
        elif name == "font-style" and words:
            slant = words[0] in ("italic", "oblique")
            (add if slant else drop if words[0] == "normal" else set()).add("italic")
        elif name == "font" and words:
            # Note: the shorthand sets the weight and the style, plain unless it names them; they come
            # before the size, which ends them
            named: set[str] = set()
            for w in words:
                if w[0].isdigit() and not _NUMBER.fullmatch(w):
                    break
                if w in ("italic", "oblique"):
                    named.add("italic")
                elif _bold(w):
                    named.add("bold")
            add |= named
            drop |= {"bold", "italic"} - named
        elif name in ("text-decoration", "text-decoration-line"):
            if "underline" in words:
                add.add("underline")
            if "line-through" in words:
                add.add("strike")
            if "none" in words:
                own |= {"underline", "strike"}
        elif name == "vertical-align" and words:
            if words[0] in ("super", "sup"):
                add.add("sup")
                drop.add("sub")
            elif words[0] == "sub":
                add.add("sub")
                drop.add("sup")
            elif words[0] == "baseline":
                own |= {"sup", "sub"}
    return frozenset(add), frozenset(drop - add), frozenset(own - add)


class _Reader(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        # Note: the text as runs of one set of marks, each run a list of pieces, joined once at the end
        self.runs: list[tuple[list[str], frozenset[str]]] = []
        # Note: each open element as (tag, marks it adds, marks it takes off, marks on its text, inert); the
        # marks on its text are those of the whole stack up to it, worked out once when it opens, so reading
        # is linear
        self.stack: list[tuple[str, frozenset[str], frozenset[str], frozenset[str], bool]] = []
        self.open: collections.Counter[str] = collections.Counter()   # how many of each tag are open
        self.hidden = 0
        self.inert = 0

    def _push(self, tag: str, add: frozenset[str], drop: frozenset[str]) -> None:
        above = self.stack[-1][3] if self.stack else frozenset()
        here = (above | add) - drop
        if tag in HIDDEN:
            self.hidden += 1
        inert = tag in INERT
        self.inert += inert
        self.open[tag] += 1
        self.stack.append((tag, add, drop, frozenset() if self.inert else here, inert))

    def _pop(self) -> tuple[str, frozenset[str], frozenset[str]]:
        tag, add, drop, _, inert = self.stack.pop()
        self.hidden -= tag in HIDDEN
        self.inert -= inert
        self.open[tag] -= 1
        return tag, add, drop

    def _close(self, tag: str) -> None:
        """Pops open elements down to and including the innermost `tag`."""
        while self.open[tag]:
            self._pop()

    def set_cdata_mode(self, elem: str, *args, **kwargs) -> None:
        # Note: only a script and a style hold text the parser must not read as markup. Python 3.13 also reads
        # a title, a textarea and a few more that way, which would hide an unclosed title's whole page;
        # reading them as elements keeps the same page the same on every version
        if elem.lower() in ("script", "style"):
            super().set_cdata_mode(elem, *args, **kwargs)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in VOID:
            return
        # Note: a title holds no tags, and a head only those it may: any other ends it, as the page begins
        if self.open["title"]:
            self._close("title")
        if self.open["head"] and tag not in HEAD:
            self._close("head")
        add, drop, own = style_marks(dict(attrs).get("style") or "")
        default = frozenset({TAGS[tag]} if tag in TAGS else ()) - own
        self._push(tag, default | add, drop)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        pass

    def handle_endtag(self, tag: str) -> None:
        if not self.open[tag]:      # Note: an end tag with no start tag is ignored, with no walk of the stack
            return
        reopen = []
        while self.stack:
            t, add, drop = self._pop()
            if t == tag:
                break
            if t in TAGS:      # Note: a mark element this end tag crossed goes on after it, as a browser does
                reopen.append((t, add, drop))
        for t, add, drop in reversed(reopen[-REOPEN:]):
            self._push(t, add, drop)

    def handle_data(self, data: str) -> None:
        # Note: text in a head that is not a title, a script or a style begins the page
        if self.open["head"] and data.strip() and not self.hidden - self.open["head"]:
            self._close("head")
        if self.hidden or not data:
            return
        marks = self.stack[-1][3] if self.stack else frozenset()
        if self.runs and self.runs[-1][1] == marks:
            self.runs[-1][0].append(data)
        else:
            self.runs.append(([data], marks))


@functools.lru_cache(maxsize=256)
def read(html: str) -> Marked:
    """The output's folded text, and the marks of each of its characters. Block boundaries and whitespace fold
    away, so a mark runs across a space, a line break or a paragraph break when both sides carry it, and
    carries nothing else."""
    r = _Reader()
    r.feed(html)
    r.close()
    text: list[str] = []
    marks: list[frozenset[str]] = []
    for parts, m in r.runs:
        f = fold("".join(parts))
        text.append(f)
        marks.extend([m] * len(f))
    return Marked("".join(text), tuple(marks), any(marks))


def check(out: Marked, before: str, span: str, after: str, wanted: tuple[str, ...],
          absent: tuple[str, ...]) -> tuple[bool, str]:
    """Whether the span carries exactly the wanted marks and the words around it do not, or carries none of
    the `absent` ones. The context (before, span and after, folded) is found as written, anywhere on the
    output. Only letters and digits are looked at: a mark that stops at a punctuation mark (`**Total:**` or
    `**Total**:`) is the same mark, and the words around the span are the letter or digit on each side of it.
    A positive test passes at any place the context is; a negative one only when no place carries a mark, and
    only on an output that has a mark somewhere: with none, nothing shows the system could have written
    one."""
    b, s, a = fold(before), fold(span), fold(after)
    if not s:
        raise ValueError("a format test's span has nothing left after folding")
    if absent and not out.emitted:
        return False, "the output has no marks at all, so it cannot show that a mark is absent"
    t, why, verdicts = out.text, "", []
    context = b + s + a
    i = t.find(context)
    if i < 0:
        return False, "the context is not in the output"
    while i >= 0:
        c0, c1 = i, i + len(context)
        i += len(b)
        j = i + len(s)
        letters = [k for k in range(i, j) if t[k].isalnum()] or list(range(i, j))
        if wanted:
            missing = sorted({m for m in wanted for k in letters if m not in out.marks[k]})
            near = [k for k in (next((k for k in range(i - 1, c0 - 1, -1) if t[k].isalnum()), None),
                                next((k for k in range(j, c1) if t[k].isalnum()), None)) if k is not None]
            spill = sorted({m for m in wanted for k in near if m in out.marks[k]})
            ok = not missing and not spill
            if missing:
                why = f"the span lacks {missing}"
            elif spill:
                why = f"{spill} runs onto the text around the span"
        else:
            carried = sorted({m for m in absent for k in letters if m in out.marks[k]})
            ok = not carried
            if carried:
                why = f"the span carries {carried}"
        verdicts.append(ok)
        i = t.find(context, c0 + 1)
    ok = any(verdicts) if wanted else all(verdicts)
    return ok, ("" if ok else why)
