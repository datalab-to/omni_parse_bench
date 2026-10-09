"""The comparison normal form: both sides of every comparison go through `fold`.

A test's string and a provider's text view are compared only after `fold`, the same function on
both sides, so a rule can never favour one side. `fold` applies, in this order:

    LaTeX spans      $..$ carrying LaTeX markup, one to three letters, or digits -> its text, without
                     the spaces math mode doesn't render ("$c_{\\text{MC}}$" -> "cMC", "$U$" -> "U",
                     "$$2 . 5 5$$" -> "2.55")
    line-end hyphens a word broken by a hyphen at a line end -> joined ("develop-\\ners" and "develop- ers"
                     -> "developers"), when a lowercase letter follows
    superscripts     superscript digits after a digit set apart ("1,240¹" -> "1,240 1"), as views.text
                     sets apart a <sup>, so a footnote marker never joins the number it follows
    NFKC             compatibility forms -> canonical ("ﬁ" -> "fi")
    invisibles       private-use characters and format characters (Unicode category Cf: zero-width,
                     bidi controls, soft hyphen, word joiner, ...) removed, except the visible
                     number signs that are Cf (Arabic, Syriac, Kaithi: `_VISIBLE_FORMAT`)
    checkboxes       every checked glyph -> ☒, every unchecked glyph -> ☐; so are [x], [checked],
                     [ ] and [unchecked]
    markers          a footnote marker [1] or [^1] -> " 1"; a bullet glyph starting a line -> a space
    leaders          runs of 3+ dots, dashes or underscores -> a space
    typography       dash, quote (with primes), space and arrow families unified; the fraction slash
                     -> "/"; "…" -> "..."; CJK full-width punctuation -> ASCII
    case, spacing    lowercased; whitespace collapsed and trimmed

Casing is folded because it isn't what a parse is paid for; digits, letters and their order are.
`squeeze` is `fold` with every space removed, for text layers that glue a footnote marker to its
word ("Probiotic1") where providers write a space or a <sup>.
"""
from __future__ import annotations

import functools
import re
import sys
import unicodedata

from omni_parse_bench import views

# Note: Cf is the whole invisible-formatting category, so a stray one (a zero-width space in "Ac\u200bme")
# never splits a word; but the prepended concatenation marks are Cf and printed (the Arabic number
# sign U+0600 draws under the digits it precedes), so they stay.
_VISIBLE_FORMAT = frozenset("\u0600\u0601\u0602\u0603\u0604\u0605\u06dd\u070f\u0890\u0891\u08e2"
                            "\U000110bd\U000110cd")
_INVISIBLE = re.compile("[\ue000-\uf8ff" + "".join(
    re.escape(c) for c in map(chr, range(sys.maxunicode + 1))
    if unicodedata.category(c) == "Cf" and c not in _VISIBLE_FORMAT) + "]")
_CHECKED = re.compile("[☑☒■▣✓✔✗✘]")
_UNCHECKED = re.compile("[☐□◻◼❏▢⬜]")
_BRACKET_CHECKED = re.compile(r"\[(?:[xX✓✗]|checked)\]", re.I)
_BRACKET_UNCHECKED = re.compile(r"\[ ?\]|\[unchecked\]", re.I)
_FOOTNOTE = re.compile(r"\[\^\s*(\w{1,3})\s*\]|\[\s*(\d{1,3})\s*\]")
# Note: ■ isn't here; it's a checked box (_CHECKED).
_BULLET = re.compile(r"(?m)^([ \t]*)[•‣◦▪▶∙●](?=\s|$)")
_LEADERS = re.compile("(?:[.…·_\\-–—=*]\\s?){3,}")
_DASH = re.compile("[‐-―−]")
_SQUOTE = re.compile("[‘’‚‛ʼ`´′]")
_DQUOTE = re.compile("[“”„‟«»]")
# TeX's quotes, written as doubled single quotes; and a spacing accent typed after its letter, as a
# text layer copies it from TeX ("Cuo´"), which NFKC would split into a space and a loose accent.
_TEX_QUOTE = re.compile("‘‘|’’|``|''")
# Note: ´ between two letters is an apostrophe typed as an accent ("it´s"), not one.
_ACUTE_APOSTROPHE = re.compile("(?<=[^\\W\\d_])´(?=[^\\W\\d_])")
_SPACING_ACCENT = re.compile("(?<=[^\\W\\d_])([´¨˜ˆ˚¸˘ˇ˙˝])")
_COMBINING = {"´": "\u0301", "¨": "\u0308", "˜": "\u0303", "ˆ": "\u0302", "˚": "\u030a", "¸": "\u0327",
              "˘": "\u0306", "ˇ": "\u030c", "˙": "\u0307", "˝": "\u030b"}
_SPACE = re.compile("[\u00a0\u2000-\u200a\u202f\u205f\u3000]")
# Each family of arrow glyphs (double, white, heavy, long, ...) folds to its plain arrow.
_ARROWS = (
    (re.compile("[\u21a0\u21a3\u21a6\u21aa\u21ac\u21b3\u21c0\u21c1\u21c9\u21d2"
                "\u21db\u21dd\u21e2\u21e5\u21e8\u21f0\u21fe\u27a1\u2794\u2798-\u27af"
                "\u27b1-\u27be\u27f6\u27f9\u27fc\u27fe\u2b95\u2b62\u2b6c\u2b72\u2b8a"
                "\u2ba9]"), "\u2192"),
    (re.compile("[\u219e\u21a2\u21a4\u21a9\u21ab\u21b2\u21bc\u21bd\u21c7\u21d0"
                "\u21da\u21dc\u21e0\u21e4\u21e6\u21fd\u27f5\u27f8\u27fb\u27fd"
                "\u2b05\u2b60\u2b6a\u2b70\u2b88]"), "\u2190"),
    (re.compile("[\u219f\u21a5\u21be\u21bf\u21c8\u21d1\u21de\u21e1\u21e7\u21ea"
                "\u2b06\u2b61\u2b6b\u2b71\u2b89]"), "\u2191"),
    (re.compile("[\u21a1\u21a7\u21c2\u21c3\u21ca\u21d3\u21df\u21e3\u21e9\u2b07"
                "\u2b63\u2b6d\u2b73\u2b8b]"), "\u2193"),
)
_WHITESPACE = re.compile(r"\s+")
_SUPERSCRIPT_DIGITS = re.compile("(?<=\\d)([⁰¹²³⁴⁵⁶⁷⁸⁹]+)")
_CJK_PUNCT = str.maketrans({
    "。": ".", "，": ",", "．": ".", "：": ":", "；": ";", "！": "!",
    "？": "?", "（": "(", "）": ")", "、": ",", "％": "%", "＝": "=",
})
_DISPLAY_MATH = re.compile(r"\$\$(.+?)\$\$", re.S)
# \[..\] and \(..\) are the same math as $$..$$ and $..$, written the other LaTeX way.
_BRACKET_MATH, _PAREN_MATH = re.compile(r"\\\[(.+?)\\\]", re.S), re.compile(r"\\\((.+?)\\\)", re.S)
_INLINE_MATH = re.compile(r"\$([^$\n]+?)\$")
_LATEX_MARKUP = re.compile(r"[\\^_{}]")
_LATEX_RESIDUE = re.compile(r"[_^{}\\]")
# A $..$ span is math only if it's short and dense. Prose between two dollar amounts ("$5.00 ... on
# line $1,000") also sits between two "$", and converting it would eat the money's "$".
_MATH_MAX_LEN, _MATH_MAX_SPACES = 120, 4
# Note: and an inline span with this many bare words (three letters or more, outside every brace, not
# a command) is prose ("$____ Date paid ____ Balance $"); math has almost none, however it's spaced.
_PROSE_WORDS = 3
_PROSE_WORD = re.compile(r"(?<![\\\w&])[^\W\d_]{3,}")
_BRACED = re.compile(r"\{[^{}]*\}")
# Note: one to three letters between dollars is a variable ($U$, $d$, $Re$); an amount has digits.
_MATH_LETTERS = re.compile(r"[^\W\d_]{1,3}")
# Note: in math mode a space renders nothing ("$$2 . 5 5$$" is 2.55), except the one ending a
# command name (\pm 0, \alpha b), a control space (x\ y), and those in and after a text group
# (\text{is the} x), which may hold one level of braces.
_MATH_TEXT = re.compile(r"\\(?:text\w*|mbox|operatorname)\s*\{(?:[^{}]|\{[^{}]*\})*\}\s*")
_COMMAND_SPACE = re.compile(r"(\\[A-Za-z]+)\s+")
_CONTROL_SPACE = re.compile(r"(?<!\\)\\\s+")
# Digits spaced out inside the dollars, as a LaTeX writer spaces them ("$$2 . 5 5$$"); a dollar
# amount has a space at the span's edge instead ("$2.7 $2.2": the span is "2.7 "), so it isn't one.
_SPACED_DIGITS = re.compile(r"\d[\d.,]*(?:\s+[\d.,]+)+")
# A word broken at a line end: a hyphen (any of its forms), then the line break, or the space a
# writer joined lines with. Not a dash, which can end a line before a lowercase word.
_LINE_HYPHEN = re.compile(r"(?<=[^\W\d_])[-\u2010\u2011]\s+([^\W\d_])")


def fold(s: str) -> str:
    """The canonical form of `s` for comparison."""
    s = _latex_to_text(s)
    # Note: only before a lowercase letter, so a line ending "-" before a capital or a digit stays.
    s = _LINE_HYPHEN.sub(lambda m: m[1] if m[1].islower() else m[0], s)
    s = _SUPERSCRIPT_DIGITS.sub(r" \1", s)
    s = _INVISIBLE.sub("", unicodedata.normalize("NFKC", _primes(s)))
    s = boxes(s)
    # Note: a space before the marker, so "12.3%[1]" isn't read as "12.3%1"; `squeeze` still
    # matches a text layer's "Probiotic1".
    s = _FOOTNOTE.sub(lambda m: f" {m[1] or m[2]}", s)
    s = _BULLET.sub(r"\1 ", s)
    s = _LEADERS.sub(" ", s)
    s = typography(s)
    s = s.replace("…", "...").translate(_CJK_PUNCT)
    return _WHITESPACE.sub(" ", s).strip().lower()


def boxes(s: str) -> str:
    """`s` with every checked box, a glyph or a bracket, as ☒ and every unchecked one as ☐."""
    s = _BRACKET_UNCHECKED.sub(views.UNCHECKED, _BRACKET_CHECKED.sub(views.CHECKED, s))
    return _UNCHECKED.sub(views.UNCHECKED, _CHECKED.sub(views.CHECKED, s))


def _primes(s: str) -> str:
    """″, ‴ and TeX's doubled quotes as ", and a spacing accent after a letter as a combining one:
    before NFKC, which would split ″ and ‴ into primes and a spacing accent off its letter."""
    s = _TEX_QUOTE.sub('"', s.replace("″", '"').replace("‴", '"'))
    return _SPACING_ACCENT.sub(lambda m: _COMBINING[m[1]], _ACUTE_APOSTROPHE.sub("'", s))


def typography(s: str) -> str:
    """`s` with its character forms unified (compatibility forms, invisibles, dashes, quotes,
    spaces, arrows) and nothing else: markup such as `**` and case are left alone."""
    s = _INVISIBLE.sub("", unicodedata.normalize("NFKC", _primes(s))).replace("⁄", "/")
    s = _DASH.sub("-", s)
    s = _SQUOTE.sub("'", s)
    s = _DQUOTE.sub('"', s)
    s = _SPACE.sub(" ", s)
    for pattern, arrow in _ARROWS:
        s = pattern.sub(arrow, s)
    return s


def squeeze(s: str) -> str:
    """`fold` with every space removed."""
    return _WHITESPACE.sub("", fold(s))


def _latex_to_text(s: str) -> str:
    if "\\[" in s or "\\(" in s:
        s = _PAREN_MATH.sub(lambda m: f"${m[1]}$", _BRACKET_MATH.sub(lambda m: f"$${m[1]}$$", s))
    if "$" not in s:
        return s
    s = _DISPLAY_MATH.sub(_math_span, s)
    return _INLINE_MATH.sub(_math_span, s)


def _math_span(m: re.Match[str]) -> str:
    body = m[1]
    if _MATH_LETTERS.fullmatch(body.strip()): return body.strip()
    dense = _dense(body)
    if _SPACED_DIGITS.fullmatch(body): return dense
    if (dense.count(" ") > _MATH_MAX_SPACES or len(body) > _MATH_MAX_LEN
            or (m.re is _INLINE_MATH and _prose(body))):
        return m[0]
    # Note: math with no LaTeX in it ("$p < 0.05$", <math>T = 20.3</math>) reads as the text it
    # renders, as math with LaTeX does; but only when it hugs its dollars, since prose between two
    # dollar amounts has a space inside one of them ("$2.7 $2.2", "$1,000 to $2,000").
    if not _LATEX_MARKUP.search(body): return body if body == body.strip() else m[0]
    try:
        t = _latex_converter().latex_to_text(dense)
    except Exception:
        # Note: pylatexenc raises on arbitrary malformed LaTeX; the span then compares as written.
        t = body
    return _LATEX_RESIDUE.sub("", t.replace("∘", "°").replace("\\circ", "°"))


def _prose(body: str) -> bool:
    """Whether an inline span's words, outside its braces, are prose's."""
    while (unbraced := _BRACED.sub(" ", body)) != body: body = unbraced
    return len(_PROSE_WORD.findall(body)) >= _PROSE_WORDS


def _dense(body: str) -> str:
    """A math span's LaTeX without the spaces that render nothing."""
    body, held = views.hold(body, _MATH_TEXT)
    body = _COMMAND_SPACE.sub(lambda m: m[1] + "\0", _CONTROL_SPACE.sub("\0", body))
    return views.release(re.sub(r"\s+", "", body).replace("\0", " "), held)


@functools.cache
def _latex_converter():
    from pylatexenc.latex2text import LatexNodes2Text

    return LatexNodes2Text()
