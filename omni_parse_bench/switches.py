"""Named switches: each rule of the scorer that changes a verdict can be turned on or off by name, so a
regrade of saved outputs can say which rule moved which verdict.

A switch is on when, in this order of precedence:

1. a `using(...)` block (or `set_all`) in this process says so;
2. the `OPB_SWITCHES` environment variable says so: `all`, `none`, or a comma list of names where `-name`
   turns one off (`all,-alt_text_out`; `visibility,cell_windows`);
3. its default says so.

Every default is off until the rules are released together; that is one change, to `DEFAULT_ON` below. A rule
that is off behaves as the scorer did before it.

    with switches.using(visibility=True): ...
    switches.on("visibility")
"""

from __future__ import annotations

import contextlib
import contextvars
import os
from collections.abc import Iterator, Mapping
from types import MappingProxyType
from typing import NamedTuple

# Set to True when the rules ship: every switch then defaults to on.
DEFAULT_ON = False


class Switch(NamedTuple):
    name: str
    what: str  # the rule, in a sentence
    step: int  # the step of the work that makes it do something (1 reader, 2 chain, 3 contract)
    wired: bool  # True when the scorer in this tree consults it; False when only the reader library does


_SWITCHES = (
    Switch(
        "visibility",
        "Text the page hides (`hidden`, `display:none`, `visibility:hidden`, `<template>`, "
        "`<noscript>`, `<input type=hidden>`) is not read.",
        1,
        True,
    ),
    Switch(
        "alt_text_out", "Image alt text is not page text; a figure contributes only its caption.", 1, True
    ),
    Switch(
        "cell_windows", "A window of text stops at a table cell: two cells never form one window.", 1, False
    ),
    Switch(
        "sup_exponent",
        "A `<sup>` (or Unicode superscript) right after a digit is an exponent, part of "
        "the quantity, never a footnote mark.",
        1,
        False,
    ),
    Switch(
        "tokens",
        "Text is read as tokens at grapheme-cluster edges, by script class (Word, Qty, Sym, "
        "Mark, Wrap, ...), not as characters.",
        1,
        False,
    ),
    Switch(
        "text_fold",
        "The Id to Text fold (compatibility forms, typography, invisible characters, leaders, look-alike "
        "symbols) is applied once, between the quantity scan and word tokenization.",
        2,
        False,
    ),
    Switch(
        "chain",
        "A `present` text test is matched on the normalizer chain (Id, Text, Cased, Words) by the one "
        "distance, in place of the old fold, squeeze retries and number guard. The rules below are the "
        "chain's own; with `chain` off none of them is read.",
        2,
        True,
    ),
    Switch("word_edges", "A match starts and ends at token edges: `Total` is not in `Totally`.", 2, False),
    Switch(
        "space_one_sided",
        "From Cased on a space of the gold is free, a space of the output is not: `Total Due` matches "
        "`TotalDue`, `therapist` does not match `the rapist`. Off: spaces are free on both sides.",
        2,
        False,
    ),
    Switch(
        "osa",
        "A swap of two neighbouring characters is one edit (OSA); off: it is two (Levenshtein).",
        2,
        False,
    ),
    Switch(
        "qty_atomic",
        "A quantity is atomic: any edit that touches one costs more than any budget, so `10kg` never "
        "matches `10mg`. Off: its characters are edited like any others.",
        2,
        False,
    ),
    Switch("marks_free", "From Cased on a footnote mark is deleted from gold and output.", 2, False),
    Switch(
        "wrap_free", "A hyphen wrapped over a line end is free in the output, or equals a gold `-`.", 2, False
    ),
    Switch(
        "break_free",
        "A line or block break matches a gold space at no cost, and from Cased on may be deleted.",
        2,
        False,
    ),
)
SWITCHES: dict[str, Switch] = {s.name: s for s in _SWITCHES}

_override: contextvars.ContextVar[Mapping[str, bool]] = contextvars.ContextVar(
    "opb_switches", default=MappingProxyType({})
)


def _environment() -> dict[str, bool]:
    """The state `OPB_SWITCHES` asks for; names it does not mention are absent (they keep their default)."""
    out: dict[str, bool] = {}
    for part in os.environ.get("OPB_SWITCHES", "").replace(" ", "").split(","):
        if not part:
            continue
        if part in ("all", "none"):
            out = dict.fromkeys(SWITCHES, part == "all")
            continue
        name = part.removeprefix("-")
        if name not in SWITCHES:
            raise ValueError(f"OPB_SWITCHES: unknown switch {name!r}; known: {sorted(SWITCHES)}")
        out[name] = not part.startswith("-")
    return out


def on(name: str) -> bool:
    """Whether the rule `name` is in force."""
    if name not in SWITCHES:
        raise KeyError(f"unknown switch {name!r}; known: {sorted(SWITCHES)}")
    state = _override.get()
    if name in state:
        return state[name]
    env = _environment()
    if name in env:
        return env[name]
    return DEFAULT_ON


def state() -> dict[str, bool]:
    """Every switch and whether it is on."""
    return {name: on(name) for name in SWITCHES}


@contextlib.contextmanager
def using(**named: bool) -> Iterator[None]:
    """Sets the named switches for the block; the others keep their state."""
    for name in named:
        if name not in SWITCHES:
            raise KeyError(f"unknown switch {name!r}; known: {sorted(SWITCHES)}")
    token = _override.set({**_override.get(), **named})
    try:
        yield
    finally:
        _override.reset(token)


@contextlib.contextmanager
def set_all(value: bool) -> Iterator[None]:
    """Every switch on (or off) for the block."""
    with using(**dict.fromkeys(SWITCHES, value)):
        yield
