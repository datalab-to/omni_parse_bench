# ruff: noqa: E501
"""The typed claim contract as one table: what each test type reads, claims, compares, quantifies over and
requires of an output. The code reads this table (`tests.py` for a test's roles, `runners.py` for the gate on
an empty output), and docs/scoring/schema.md is rendered from it (`render`); a test fails when they differ.

A row is a small record:

    reads       the output the test grades (`vocab.READS`)
    roles       the roles of its args; `required` are the ones a test must give
    projection  what the test sees of the output: flat text, the grid, blocks, marks, math
    point       the point of the normalizer chain its claim is read at (`chain.py`); locators read Words
    relation    how witnesses are built from the args
    quantifier  over the witnesses: exists, unique, all, not_exists, count, or a locator and no claim
    budget      where the edit budget comes from
    gate        what an empty (supplied) output means: `fail`, `blank` (a bare negative test passes only on a
                page whose gold holds a `page_near_empty` test) or `count` (the statistic decides)
    unit        what a window of the claim may cross

A missing output (`html` or `blocks` absent or null) fails every row. Rows of one type that differ in a
setting (`present` with `absent`, `blank_after`) are listed separately; `variant` names a test's row.
"""
from __future__ import annotations

from typing import Any, NamedTuple

EXISTS, UNIQUE, ALL, NOT_EXISTS, COUNT, LOCATOR_NOT = (
    "exists", "unique", "all", "not_exists", "count", "locator_and_not_exists")
QUANTIFIERS = (EXISTS, UNIQUE, ALL, NOT_EXISTS, COUNT, LOCATOR_NOT)
FAIL, BLANK, COUNTED = "fail", "blank", "count"
GATES = (FAIL, BLANK, COUNTED)


class Row(NamedTuple):
    type: str                       # the test type
    name: str                       # the row's name: the type, or `type.setting`
    family: str
    reads: str
    roles: tuple[str, ...]
    required: tuple[str, ...]
    projection: str
    point: str
    relation: str
    quantifier: str
    budget: str
    gate: str
    unit: str


_REL = ("up", "down", "left", "right", "top_heading", "left_heading", "right_heading")


def _row(type, name, family, reads, roles, required, projection, point, relation, quantifier, budget, gate,
         unit="block") -> Row:
    return Row(type, name, family, reads, tuple(roles), tuple(required), projection, point, relation,
               quantifier, budget, gate, unit)


ROWS: tuple[Row, ...] = (
    _row("present", "present", "text", "html", ("content", "printed", "stops"), ("content",), "flat",
         "Words (Cased with exact_case)", "match_k(content)", EXISTS, "content", FAIL),
    _row("present", "present.number", "text", "html", ("content", "printed", "stops"), ("content",), "flat",
         "Words", "match_0(one Qty)", EXISTS, "0", FAIL),
    _row("present", "present.latex", "text", "html", ("content", "printed", "stops"), ("content",),
         "math, then flat with math as symbols", "off chain (KaTeX)",
         "contiguous symbol sequence at symbol edges", EXISTS, "0", FAIL),
    _row("present", "present.absent", "text", "html", ("content", "printed", "stops"), ("content",), "flat",
         "Words", "match_k(content)", NOT_EXISTS, "at most a quarter of the content", BLANK),
    _row("present", "present.blank_field", "text", "html", ("content", "printed", "stops"), ("content",),
         "flat + grid", "Text", "anchors = copies of the label; region(label to next stop) eq_0 empty or printed",
         ALL, "0", FAIL),
    _row("order", "order", "text", "html", ("before", "after"), ("before", "after"), "flat", "Words",
         "(w_b, w_a), w_b before w_a, each match at its own budget", EXISTS, "before, after", FAIL),
    _row("repeat", "repeat", "text", "html", ("content",), ("content",), "flat", "Words",
         "match_0(content); selection", COUNT, "0", COUNTED),
    _row("page_near_empty", "page_near_empty", "text", "html", (), (), "flat", "Id", "visible characters",
         COUNT, "", COUNTED),
    _row("verbatim", "verbatim", "text", "html", ("start", "end", "content"), (), "flat", "Text",
         "anchors = copies of start; region(start to its paired end) eq_k content", ALL, "content", FAIL),
    _row("no_excess_repeats", "no_excess_repeats", "text", "html", ("content",), ("content",), "flat minus math",
         "Words", "16-word runs repeated over their gold count; spaced scripts only", NOT_EXISTS, "0", BLANK),
    _row("table_cell", "table_cell", "tables", "html",
         ("cell", "headings", "section", "row_groups", *_REL), ("cell",), "grid", "Words",
         "anchor line eq_k cell; every role has a witness line", EXISTS, "one, shared by the cell and its roles",
         FAIL, "cell"),
    _row("table_cell", "table_cell.shape", "tables", "html",
         ("cell", "headings", "section", "row_groups", *_REL), ("cell",), "grid", "Words",
         "as table_cell, plus a blank side (`empty`) or no text beyond (`end`) for each anchor", ALL,
         "one, shared by the cell and its roles", FAIL, "cell"),
    _row("layout_kind", "layout_kind", "layout", "blocks", ("content",), ("content",), "blocks",
         "off chain (label order)", "the holder of place has label <= expected", UNIQUE, "", FAIL),
    _row("layout_absent", "layout_absent", "layout", "blocks", (), (), "blocks", "off chain (label order)",
         "a block whose label <= a forbidden kind", NOT_EXISTS, "", BLANK),
    _row("format", "format", "format", "html", ("before", "span", "after"), ("span",), "marks", "Words",
         "context match; the span carries the marks; no spill", EXISTS, "0", FAIL),
    _row("format", "format.absent", "format", "html", ("before", "span", "after"), ("span",), "marks", "Words",
         "context match (locator); the span carries a forbidden mark (claim)", LOCATOR_NOT, "0", FAIL),
)

SCHEMA: dict[str, Row] = {r.name: r for r in ROWS}
TYPES = tuple(dict.fromkeys(r.type for r in ROWS))
BASE: dict[str, Row] = {r.type: r for r in reversed(ROWS)}      # the type's first row

assert len(SCHEMA) == len(ROWS)
assert all(r.quantifier in QUANTIFIERS and r.gate in GATES for r in ROWS)


# The label order of the layout tests: a label is at most another when a block labelled the first is also one
# of the second. Only `list` and `form` are at most `text`; `caption` and `footnote` are reading roles of
# their own. Both layout tests apply it (`layout_kind` to the kind it expects, `layout_absent` to the kinds it
# forbids).
LABEL_BELOW = {"text": frozenset({"list", "form"})}


def label_le(label: str, kind: str) -> bool:
    return label == kind or label in LABEL_BELOW.get(kind, frozenset())


def below(kind: str) -> frozenset[str]:
    """Every label at most `kind`, itself included."""
    return LABEL_BELOW.get(kind, frozenset()) | {kind}


def variant(test_type: str, params: Any) -> Row:
    """The row of a test: the type's row, or the one its setting selects."""
    if test_type == "present":
        content = getattr(params, "content", None)
        kind = type(content).__name__
        if getattr(params, "absent", False):
            return SCHEMA["present.absent"]
        if getattr(params, "blank_after", False):
            return SCHEMA["present.blank_field"]
        if kind == "Number":
            return SCHEMA["present.number"]
        if kind == "Latex":
            return SCHEMA["present.latex"]
    if test_type == "table_cell" and getattr(params, "shapes", None):
        return SCHEMA["table_cell.shape"]
    if test_type == "format" and getattr(params, "absent", ()):
        return SCHEMA["format.absent"]
    return BASE[test_type]


def roles() -> dict[str, tuple[str, ...]]:
    return {t: BASE[t].roles for t in TYPES}


def required() -> dict[str, tuple[str, ...]]:
    return {t: BASE[t].required for t in TYPES}


def render() -> str:
    """docs/scoring/schema.md's table, one line per row."""
    head = ("| row | reads | projection | point | relation | quantifier | budget | gate on an empty output |",
            "|---|---|---|---|---|---|---|---|")
    body = (f"| {r.name} | {r.reads} | {r.projection} | {r.point} | {r.relation} | {r.quantifier} | "
            f"{r.budget or '-'} | {r.gate} |" for r in ROWS)
    return "\n".join((*head, *body)) + "\n"
