# ruff: noqa: E501
"""Cases for docs/scoring/layout_absent.md. The kinds are the blank-page set (`cases.BLANK`) unless a case says otherwise."""
from cases import layout_absent, table

TOP = (0.4, 0.02, 0.6, 0.05)
MID = (0.2, 0.4, 0.8, 0.5)
PAGE = (0, 0, 1, 1)

TABLES = [
    table(
        "layout-absent-ignored",
        layout_absent("la-none", "I", "no blocks at all: a blank page read as blank", []),
        layout_absent("la-folio", "I", "a page number as page furniture", [("page_furniture", TOP, "7")]),
        layout_absent("la-text", "I", "a text block (`page_near_empty` reads text)", [("text", MID, "a synthetic note")]),
        layout_absent("la-figure", "I", "a figure (a stain, a stamp, a plate)", [("figure", PAGE, "")]),
        layout_absent("la-form", "I", "ruled lines read as a form", [("form", PAGE, "")]),
        layout_absent("la-other-kinds", "I", "a heading, when the test forbids only tables", [("heading", MID, "SAMPLE HEADING")], kinds=("table",)),
    ),
    table(
        "layout-absent-blind",
        layout_absent("la-heading-as-text", "B", "a heading labeled text", [("text", MID, "SAMPLE TITLE")]),
        layout_absent("la-text-unread", "B", "the text of an allowed block is not read", [("page_furniture", TOP, "An invented sentence")]),
    ),
    table(
        "layout-absent-penalized",
        layout_absent("la-heading", "P", "a heading block", [("heading", MID, "SAMPLE HEADING")], why=True),
        layout_absent("la-table", "P", "an empty table", [("table", MID, "")], why=True),
        layout_absent("la-list", "P", "a list block (labels are compared as written: a list is not text here)", [("list", MID, "- item")]),
        layout_absent("la-many", "P", "several forbidden blocks: the first is named", [("text", TOP, "7"), ("caption", MID, "Fig. 1"), ("equation", MID, "x")], why=True),
        layout_absent("la-tiny", "P", "a forbidden block however small", [("code", (0.5, 0.5, 0.51, 0.51), "")]),
    ),
]
