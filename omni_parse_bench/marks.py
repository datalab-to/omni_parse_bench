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
marked), `<mark>`, `<a>`, `<kbd>`, Unicode superscript characters, and LaTeX, except a subscript or
superscript written inside inline or display maths (`$V_1$`, `\\(x^{2}\\)`, `$\\mathrm{LC}_{50}$`):
`maths` reads it as `V<sub>1</sub>`, the base before the script plain, when the whole span is simple (letters,
digits, signs, `\\mathrm{}`/`\\text{}` groups, argument-less commands such as `\\mu` and `\\times`, scripts of
those); a span with a command that takes an argument (`\\frac`, `\\sqrt`), a nested script or no script is
left as written, and maths in code is not read. Text inside `<math>` carries
no mark, and what `views.html` hides is not read: a comment, a doctype, and a `<script>`, `<style>`, `<head>`
or `<title>` that an end tag closes, with everything in it. One that is never closed hides nothing, as in
`views.html`, so its text is read like any other.

The text is compared as the fold of the character forms (`normalize.typography`: dashes, quotes, spaces,
compatibility forms), case-folded, NFC, with no whitespace: the fold `format` uses is that and no more (no
footnote, hyphen, bullet or math rule), so a character's marks are easy to keep through it. A run is
folded as a whole, so a character form that spans two runs (a combining accent, two apostrophes that fold
to a quotation mark, an arrow written in two characters) is read as written when a mark boundary falls
inside it: a known limitation (M57b)."""
from __future__ import annotations

import collections
import functools
import html as _html
import re
import unicodedata
from html.parser import HTMLParser
from typing import NamedTuple

from omni_parse_bench import mathspans, normalize, views

KINDS = ("bold", "italic", "underline", "strike", "sup", "sub")
# Note: on a character whose script `maths` read from LaTeX, beside its "sub" or "sup"; never a kind
FROM_MATHS = "~maths"
# Note: the most mark elements an end tag that crosses them puts back on: a page of 20,000 is not read twice
REOPEN = 16

# element -> the mark it makes
TAGS = {"b": "bold", "strong": "bold", "i": "italic", "em": "italic", "u": "underline", "ins": "underline",
        "s": "strike", "strike": "strike", "del": "strike", "sup": "sup", "sub": "sub"}
# elements whose text is read but carries no mark
INERT = frozenset({"math"})
# a void element has no end tag, so it must not be pushed
VOID = frozenset(
    {"br", "hr", "img", "input", "meta", "link", "col", "wbr", "area", "base", "embed", "source", "track"}
)
_IMPORTANT = re.compile(r"!\s*important")   # CSS allows white space after the `!`
_NUMBER = re.compile(r"\d+")
_NOT_A_TAG = re.compile(rf"<(?!{views._TAG[1:]})")


class Marked(NamedTuple):
    """An output's text as `fold` leaves it, and the marks on each of its characters."""
    text: str
    marks: tuple[frozenset[str], ...]
    emitted: bool   # whether some letter or digit of the text carries a mark
    # whether some letter or digit carries a mark the markup makes, not one `maths` read from a script
    written: bool = True


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
    says. `vertical-align` replaces the other script: a `<sup style="vertical-align: sub">` is a subscript.
    A later declaration replaces an earlier one, unless the earlier is `!important` and it is not; a CSS-wide
    keyword (`inherit`, `unset`, `revert`) takes an earlier declaration back and `initial` is the plain
    value; a variable changes nothing."""
    bold: bool | None = None
    italic: bool | None = None
    deco: list[str] | None = None
    vertical: str | None = None
    # the properties an `!important` declaration has set: a later plain one loses
    important: set[str] = set()

    def wins(prop: str, imp: bool) -> bool:
        if prop in important and not imp:
            return False
        if imp:
            important.add(prop)
        return True

    for decl in style.lower().split(";"):
        name, _, value = decl.partition(":")
        name = name.strip()
        imp = _IMPORTANT.search(value) is not None
        words = _IMPORTANT.sub("", value).split()
        if not words or "var(" in value:
            continue
        # Note: a CSS-wide keyword replaces an earlier declaration: `initial` is the property's plain value,
        # the others leave it to the parent's (all four properties here are inherited or drawn through)
        keyword = words[0] if words[0] in ("inherit", "initial", "unset", "revert", "revert-layer") else None
        plain = keyword == "initial"
        if name == "font-weight" and wins("weight", imp):
            weight = _bold(words[0])
            bold = False if plain else None if keyword else weight if weight is not None else bold
        elif name == "font-style" and wins("style", imp):
            if keyword:
                italic = False if plain else None
            elif words[0] in ("italic", "oblique", "normal"):
                italic = words[0] != "normal"
        elif name == "font":
            # Note: each half of the shorthand loses alone to an earlier `!important` on that half
            set_weight, set_style = wins("weight", imp), wins("style", imp)
            if keyword:
                if set_weight:
                    bold = False if plain else None
                if set_style:
                    italic = False if plain else None
                continue
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
            if set_weight:
                bold = "bold" in named
            if set_style:
                italic = "italic" in named
        elif name in ("text-decoration", "text-decoration-line") and wins("deco", imp):
            deco = ["none"] if keyword in ("initial", "unset") else None if keyword else words
        elif name == "vertical-align" and wins("vertical", imp):
            vertical = "baseline" if keyword in ("initial", "unset") else None if keyword else words[0]
    add: set[str] = set()
    drop: set[str] = set()
    own: set[str] = set()
    if bold is not None:
        (add if bold else drop).add("bold")
    if italic is not None:
        (add if italic else drop).add("italic")
    if deco is not None:
        add |= {m for w, m in (("underline", "underline"), ("line-through", "strike")) if w in deco}
        if "none" in deco:
            own |= {"underline", "strike"}
    if vertical in ("super", "sup"):
        add.add("sup")
        drop.add("sub")
    elif vertical == "sub":
        add.add("sub")
        drop.add("sup")
    elif vertical == "baseline":
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
        self.inert = 0

    def _push(self, tag: str, add: frozenset[str], drop: frozenset[str]) -> None:
        above = self.stack[-1][3] if self.stack else frozenset()
        inert = tag in INERT
        self.inert += inert
        self.open[tag] += 1
        self.stack.append((tag, add, drop, frozenset() if self.inert else (above | add) - drop, inert))

    def _pop(self) -> tuple[str, frozenset[str], frozenset[str]]:
        tag, add, drop, _, inert = self.stack.pop()
        self.inert -= inert
        self.open[tag] -= 1
        return tag, add, drop

    def set_cdata_mode(self, elem: str, *args, **kwargs) -> None:
        # Note: no element holds text the parser must not read as markup. A script or a style an end tag
        # closes is gone before the parser sees the page (`read`), and one never closed is read like the text
        # view reads it, its tags as tags; Python 3.13 also reads a title and a textarea as text, and the
        # versions before it do not, so this keeps the same page the same on every version
        return

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in VOID:
            return
        add, drop, own = style_marks(dict(attrs).get("style") or "")
        default = frozenset({TAGS[tag]} if tag in TAGS else ()) - own
        # Note: a script `maths` read from LaTeX is flagged, so it is no evidence for any other mark
        read = tag in ("sub", "sup") and dict(attrs).get("data-opb-maths") == ""
        flag = frozenset({FROM_MATHS}) if read else frozenset()
        self._push(tag, default | add | flag, drop)

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
        if not data:
            return
        marks = self.stack[-1][3] if self.stack else frozenset()
        if self.runs and self.runs[-1][1] == marks:
            self.runs[-1][0].append(data)
        else:
            self.runs.append(([data], marks))


_WRAP = re.compile(r"\\(?:mathrm|mathit|mathbf|mathsf|mathtt|mathnormal|text|textrm|textit|textbf|textsf|"
                   r"operatorname)(?![A-Za-z])\s*\{")
_COMMAND = re.compile(r"\\([A-Za-z]+)")
_ESCAPED = re.compile(r"\\([%&#$_{}])")
_SPACING = re.compile(r"\\(?:[,;:! ]|quad(?![A-Za-z])|qquad(?![A-Za-z]))")
# Note: the commands that take no argument and stand for a symbol or a word: read as that text, so the scripts
# around them are read. One that takes an argument (\frac, \sqrt, \bar, \begin) is not here: the span is left.
_SYMBOLS = {"times": "×", "pm": "±", "mp": "∓", "cdot": "·", "div": "÷", "leq": "≤", "le": "≤", "geq": "≥",
            "ge": "≥", "neq": "≠", "ne": "≠", "sim": "∼", "approx": "≈", "infty": "∞", "to": "→",
            "rightarrow": "→", "propto": "∝", "ell": "ℓ", "hbar": "ℏ", "partial": "∂", "nabla": "∇",
            "prime": "′", "circ": "°", "ast": "*", "star": "*", "bullet": "•", "ldots": "…", "cdots": "…",
            "dots": "…", "angstrom": "Å", "degree": "°", "perp": "⊥", "parallel": "∥"}
_WORDS = frozenset({"sin", "cos", "tan", "log", "ln", "exp", "max", "min", "lim", "sup", "inf", "det", "arg",
                    "dim", "deg", "gcd", "sinh", "cosh", "tanh"})
_SIZES = frozenset({"left", "right", "big", "Big", "bigg", "Bigg", "bigl", "bigr", "Bigl", "Bigr", "biggl",
                    "biggr"})
_GREEK = {n.lower(): n for n in (
    "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi pi rho sigma tau upsilon phi "
    "chi psi omega").split()}


def _greek(name: str) -> str | None:
    """The Greek letter a command names (`\\mu`, `\\Delta`, `\\varepsilon`), or None."""
    base = name[3:] if name.startswith("var") else name
    low = _GREEK.get(base.lower())
    if low is None or (name.startswith("var") and base != base.lower()):
        return None
    name = "LAMDA" if low == "lambda" else low.upper()      # Note: Unicode spells it without the b
    return unicodedata.lookup(f"GREEK {'CAPITAL' if base[0].isupper() else 'SMALL'} LETTER {name}")


_PLAIN = re.compile(r"[^\\{}^_$\s]")


def _seq(body: str, i: int, closing: bool, scripts: bool) -> tuple[list[str], int, bool] | None:
    """The items of `body` from `i`, as HTML pieces: up to the `}` that closes a group (`closing`) or the end.
    A script (`_` or `^` and its argument) becomes `<sub>`/`<sup>`, unless `scripts` is False (inside a
    script's own argument, where one is not read). Returns the pieces, where it stopped (after the closing
    brace), and whether a script was met; None for anything this doesn't read."""
    out: list[str] = []
    scripted = False
    while i < len(body):
        c = body[i]
        if c.isspace():
            i += 1
        elif c == "}":
            return (out, i + 1, scripted) if closing else None
        elif c == "{":
            got = _seq(body, i + 1, True, scripts)
            if got is None:
                return None
            out += got[0]
            i, scripted = got[1], scripted or got[2]
        elif c in "_^":
            if not scripts:
                return None
            arg = _argument(body, i + 1)
            if arg is None:
                return None
            tag = "sub" if c == "_" else "sup"
            out.append(f'<{tag} data-opb-maths="">{arg[0]}</{tag}>')
            i, scripted = arg[1], True
        elif c == "\\":
            if m := _SPACING.match(body, i):
                i = m.end()
            elif m := _ESCAPED.match(body, i):
                out.append(_html.escape(m[1], quote=False))
                i = m.end()
            elif m := _WRAP.match(body, i):
                got = _seq(body, m.end(), True, scripts)
                if got is None:
                    return None
                out += got[0]
                i, scripted = got[1], scripted or got[2]
            elif m := _COMMAND.match(body, i):
                name, i = m[1], m.end()
                if name in _SIZES:
                    if name in ("left", "right") and body[i:i + 1] == ".":
                        i += 1     # `\left.` and `\right.` draw no delimiter
                elif (text := _SYMBOLS.get(name) or _greek(name)) is not None:
                    out.append(text)
                elif name in _WORDS:
                    out.append(name)
                else:
                    return None
            else:
                return None
        else:
            out.append(_html.escape(c, quote=False))
            i += 1
    return (out, i, scripted) if not closing else None


def _argument(body: str, i: int) -> tuple[str, int] | None:
    """The text of the script argument at `body[i]`: one character, one command, or a `{..}` group, none of
    them with a script of their own; and where it ends. None when it is empty or not read."""
    while i < len(body) and body[i].isspace():
        i += 1
    if i >= len(body):
        return None
    if body[i] == "{":
        got = _seq(body, i + 1, True, False)
    elif body[i] == "\\":
        if m := _WRAP.match(body, i):
            got = _seq(body, m.end(), True, False)
        elif m := _COMMAND.match(body, i) or _ESCAPED.match(body, i):
            got = _seq(body[:m.end()], i, False, False)
            got = got and (got[0], m.end(), got[2])
        else:
            return None
    elif _PLAIN.fullmatch(body[i]):
        return _html.escape(body[i], quote=False), i + 1
    else:
        return None
    return ("".join(got[0]), got[1]) if got and got[0] else None


def maths(body: str) -> str | None:
    """A maths span's body as HTML where its scripts are `<sub>` and `<sup>`, or None when it holds no script
    or anything this reads no further than: a command that takes an argument (`\\frac`, `\\sqrt`), a nested
    script, a script with nothing in it. `V_1` is `V<sub>1</sub>`, `\\mathrm{LC}_{50}` is `LC<sub>50</sub>`,
    `1.5 \\times 10^{-3}` is `1.5×10<sup>-3</sup>`, `{}^{14}C` is `<sup>14</sup>C`."""
    # Note: a span that holds a tag straddles elements ("<b>$5 _</b><i>$"), so it is no maths of one
    # place; the entities of the rest are read as the text they stand for.
    if "<" in body or ">" in body:
        return None
    got = _seq(_html.unescape(body), 0, False, True)
    return "".join(got[0]) if got and got[2] else None


_CODE = re.compile(r"<(code|pre|kbd|samp)\b[^>]*>", re.I)


def _code_ranges(html: str) -> list[tuple[int, int]]:
    """Where `<code>`, `<pre>`, `<kbd>` and `<samp>` hold text: what is written there is not maths. One never
    closed holds the rest of the page, as in a browser."""
    out, i = [], 0
    while m := _CODE.search(html, i):
        j = html.lower().find(f"</{m[1].lower()}", m.end())
        out.append((m.start(), len(html) if j < 0 else j))
        i = out[-1][1]
    return out


def _delimited(html: str, opener: str, closer: str) -> list[tuple[int, int, str]]:
    """The `opener..closer` spans of `html` (start, end, body), found in one pass: an opener with no closer
    after it ends the search, so a page of unclosed ones is read once."""
    out, i = [], 0
    while (a := html.find(opener, i)) >= 0:
        b = html.find(closer, a + 2)
        if b < 0:
            break
        out.append((a, b + 2, html[a + 2:b]))
        i = b + 2
    return out


def with_scripts(html: str) -> str:
    """`html` with each inline or display maths span (`$..$`, `$$..$$`, `\\(..\\)`, `\\[..\\]`) that `maths`
    reads written as its markup, so `read` sees `V<sub>1</sub>` where the output has `$V_1$`. Maths in code is
    left alone."""
    if "$" not in html and "\\(" not in html and "\\[" not in html:
        return html
    code = _code_ranges(html) if _CODE.search(html) else []
    inside = lambda a: any(s <= a < e for s, e in code)  # noqa: E731
    edits: list[tuple[int, int, str]] = []
    taken: list[tuple[int, int]] = []
    for opener, closer in (("\\(", "\\)"), ("\\[", "\\]")):
        for a, b, body in _delimited(html, opener, closer):
            taken.append((a, b))
            if not inside(a) and (r := maths(body)) is not None:
                edits.append((a, b, r))
    for sp in mathspans.find(html, apart=tuple(taken)):
        d = 2 if sp.display else 1
        if sp.read and not inside(sp.start) and (r := maths(html[sp.start + d:sp.end - d])) is not None:
            edits.append((sp.start, sp.end, r))
    for a, b, r in sorted(edits, reverse=True):
        html = html[:a] + r + html[b:]
    return html


@functools.lru_cache(maxsize=256)
def read(html: str) -> Marked:
    """The output's folded text, and the marks of each of its characters. Block boundaries and whitespace fold
    away, so a mark runs across a space, a line break or a paragraph break when both sides carry it, and
    carries nothing else."""
    # Note: what `views.html` hides is hidden here, by its own patterns, so the two readers see the same text
    html = views._COMMENT.sub("", html)
    html = views._SCRIPT.sub(" ", views._DOCTYPE.sub(" ", html))
    # Note: a "<" that starts no tag is text, as in the text view: an unclosed comment, "<![CDATA[", "<?xml",
    # "</ 3" and a tag left open at the end must not hide what follows from this reader alone
    html = _NOT_A_TAG.sub("&lt;", html)
    html = with_scripts(html)
    r = _Reader()
    r.feed(html)
    r.close()
    text: list[str] = []
    marks: list[frozenset[str]] = []
    for parts, m in r.runs:
        f = fold("".join(parts))
        text.append(f)
        marks.extend([m] * len(f))
    flat = "".join(text)
    pairs = list(zip(flat, marks, strict=True))
    return Marked(flat, tuple(marks), any(m and c.isalnum() for c, m in pairs),
                  any(c.isalnum()
                      and (m - {FROM_MATHS} if FROM_MATHS not in m else m - {FROM_MATHS, "sub", "sup"})
                      for c, m in pairs))


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
    # Note: a script read from maths shows only that a script could have been written, so it is evidence
    # for an absent `sub` or `sup` and for no other kind
    if absent and not (out.emitted if set(absent) <= {"sub", "sup"} else out.written):
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
