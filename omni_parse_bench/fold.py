"""The Id -> Text fold as a table: each operation, the chain step it belongs to, and whether it keeps
the length.

`FOLD` lists the operations in the order they run. The reader applies `fold_gap` to the text between
quantities (a quantity keeps its spelling), then reads that text into tokens again, so the Text tokens of an
output are fixed once. A length-changing operation may only sit in the Id -> Text step: the laws of the chain
(L1) hold across the later steps because those only map one character to one character or delete whole tokens.
`check()` enforces that.

The operations are the ones `normalize.fold` has always run, in its order, less what the reader now does
itself: a footnote marker is a `Mark` token, a hyphen at a line end is a `Wrap`, the `<sup>` rewrites are the
quantity reader's, and trimming is the reader's (a gap keeps the single space that touches a neighbour).
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable
from typing import NamedTuple

from . import normalize

ID_TEXT, TEXT_CASED, CASED_WORDS = "Id->Text", "Text->Cased", "Cased->Words"


class FoldOp(NamedTuple):
    step: str
    name: str
    fn: Callable[[str], str]
    preserving: bool  # True when every output has the length of its input (one character for one character)
    case: str  # the case id of the operation: what it is for, in a word


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def _nfkc(s: str) -> str:
    return unicodedata.normalize("NFKC", s)


def _invisible(s: str) -> str:
    return normalize._INVISIBLE.sub("", s)


def _bullets(s: str) -> str:
    return normalize._BULLET.sub(r"\1 ", s)


def _leaders(s: str) -> str:
    """A leader run folds to a space, except underscores alone that touch a letter or a digit on either side
    (`token____`, `foo___bar`, `____init`): part of an identifier, which Text keeps."""
    return normalize._LEADERS.sub(normalize._leader_in_word, s)


def _ellipsis_cjk(s: str) -> str:
    return s.replace("…", "...").translate(normalize._CJK_PUNCT)


def _middot(s: str) -> str:
    return normalize._DECIMAL_MIDDOT.sub(".", s)


def _aliases(s: str) -> str:
    return s.translate(normalize._SYMBOL_ALIASES)


def _whitespace(s: str) -> str:
    return normalize._WHITESPACE.sub(" ", s)


def _enumerator_table() -> dict[int, str]:
    """Circled, parenthesized and dotted digits (`①`, `⑽`, `⒈`) and what NFKC makes of each."""
    table = {}
    for cp in range(0x2460, 0x24FF + 1):
        ch = chr(cp)
        d = unicodedata.decomposition(ch)
        if d.startswith(("<circle>", "<compat>")) or d.startswith(("<paren>", "<period>")):
            k = unicodedata.normalize("NFKC", ch)
            if any(c.isdigit() for c in k) and not any(c.isalpha() for c in k):
                table[cp] = k
    return table


_ENUMERATORS = _enumerator_table()


def enumerator_digits(s: str) -> str:
    """A circled or parenthesized digit is the digit (condition A1: a careful reader takes `①` and `1` as the
    same enumerator, and `①` against `②` stays a different number). The reader runs this before it scans for
    quantities, so the digit is a quantity like any other; `FOLD` lists it for the record."""
    return s.translate(_ENUMERATORS) if _ENUMERATORS else s


FOLD: tuple[FoldOp, ...] = (
    FoldOp(ID_TEXT, "enumerators", enumerator_digits, False, "A1: a circled digit is the digit"),
    FoldOp(ID_TEXT, "nfc", _nfc, False, "a letter written as base and accent is one letter"),
    FoldOp(ID_TEXT, "primes", normalize._primes, False, "what NFKC would split or leave alone"),
    FoldOp(ID_TEXT, "nfkc", _nfkc, False, "compatibility forms"),
    FoldOp(ID_TEXT, "invisible", _invisible, False, "invisible, private-use and bidi-control characters"),
    FoldOp(ID_TEXT, "boxes", normalize.boxes, True, "checkbox glyphs and bracket boxes"),
    FoldOp(ID_TEXT, "bullets", _bullets, True, "a bullet glyph starting a line"),
    FoldOp(ID_TEXT, "leaders", _leaders, False, "runs of dots, dashes or underscores"),
    FoldOp(ID_TEXT, "typography", normalize.typography, False, "dash, quote, space and arrow families"),
    FoldOp(ID_TEXT, "ellipsis_cjk", _ellipsis_cjk, False, "the ellipsis and CJK full-width punctuation"),
    FoldOp(ID_TEXT, "middot", _middot, True, "a decimal middle dot"),
    FoldOp(ID_TEXT, "aliases", _aliases, True, "look-alike symbols"),
    FoldOp(ID_TEXT, "whitespace", _whitespace, False, "runs of white space"),
    FoldOp(ID_TEXT, "nfkc_again", _nfkc, False, "the composed map stops at a fixed point"),
)


def check() -> None:
    """The loader's rule: a length-changing operation only in the Id -> Text step."""
    bad = [op.name for op in FOLD if not op.preserving and op.step != ID_TEXT]
    if bad:
        raise ValueError(f"length-changing fold operations outside Id -> Text: {bad}")


check()


def fold_gap(s: str, *, line_start: bool = False) -> str:
    """The Text reading of a stretch of text: every operation of `FOLD` once, in order. A bullet glyph is
    folded only at the start of a line (`line_start`)."""
    for op in FOLD:
        if op.name == "bullets" and not line_start:
            continue
        s = op.fn(s)
    return s
