"""The closed vocabularies: output types, derivations, what each test type reads, and the tags.

A gold test whose output type, test type or derivation isn't listed here is invalid. Adding a value
is a design change, recorded in docs/design.md. A test's tags say what its content is, so that tests
can be selected; grading never reads them.
"""
from __future__ import annotations

OUTPUT_TYPES = ("html", "blocks")

DERIVATIONS = (
    "text_layer", "upstream_olmocr", "authored", "publisher_markup", "model_panel",
    "extractor_agreement", "human_review", "model_review",
    "upstream_frbench", "source_transcription",
)

# test type -> the output type it grades
READS = {
    "present": "html",
    "order": "html",
    "repeat": "html",
    "table_cell": "html",
    "layout_kind": "blocks",
}

# test type -> the capability it measures. The headline is the mean of the families' scores (each
# family's flat over its tests), so how many tests a family has never sets its weight (docs/design.md).
FAMILIES = {
    "present": "text", "order": "text", "repeat": "text",
    "table_cell": "tables",
    "layout_kind": "layout",
}

# The tags: what the content a test checks is. Each definition is
# the one text the tagger, the docs and test builders share; tag prompts are filled from it.
ROLES = ("heading", "caption", "footnote", "list", "code", "figure", "header_footer")
YES_NO = ("table", "math", "form", "multi_column", "tiny", "rotated", "handwriting", "degraded")
COMPUTED = ("script", "language")
TAG_DEFINITIONS = {
    "language": "The language the text is written in, as an ISO 639-3 code, one per span. GlotLID's answer "
                "on the text when it has 20 letters or more, GlotLID gives it a probability of 0.9 or more, "
                "and it is the page's dominant language; the page's dominant language for shorter text with "
                "a word in it; else asked. Text that mixes languages takes the one most of its words are in. "
                "Text without letters, or without a word (a code like rt016-a1), may have none.",
    "script": "The writing system of the text's letters, as the ISO 15924 code of their Unicode Script "
              "property. Counts: every script among the letters. Doesn't count: digits, punctuation and "
              "symbols. Computed, never asked.",
    "table": "The content is part of a table: a grid of cells where a heading is shared by several cells, "
             "so a cell is read by the column heading above it, the row label beside it, or both. Counts: "
             "header cells, body cells, row labels and section rows; a grid with no printed headings when "
             "several rows repeat the same columns (a price list, a spec sheet of names and values). "
             "Doesn't count: a form whose fields each have their own label, even when the fields are in "
             "boxes or lined up in rows; the table's caption or notes; two columns of prose.",
    "math": "The content is mathematical notation: an equation, a formula, or a symbol or expression set as "
            "mathematics. Counts: display and inline equations, a lone variable or Greek letter set as "
            "mathematics. Doesn't count: an ordinary number in text, a unit, a chemical formula written as "
            "plain text, or prose that names a quantity.",
    "form": "The content is a field to fill in or a box to tick, or belongs to one: its label, its filled "
            "value, the box, or the blank line. A label names what goes into one particular blank, box or "
            "checkbox next to it. Counts: such fields wherever they are, including a checklist in a manual "
            "or a survey printed in a report. Doesn't count: instructions that tell you how to fill the form "
            "in rather than naming a field, a title heading a section of the form, or cells of a printed "
            "report's table.",
    "figure": "The content is text drawn inside a figure: a chart, plot, diagram, map, drawing or photo. "
              "Counts: axis labels, tick labels, legends, labels on a diagram, text in a photo. Doesn't "
              "count: the figure's caption or body text beside the figure.",
    "header_footer": "The content is a running header or footer: text in the top or bottom margin that "
                     "belongs to the publication rather than to this page's content. Counts: a running "
                     "title, journal name, author names, chapter title, date line or page number in the "
                     "margin. Doesn't count: the article's own title on its first page, footnotes, or a "
                     "table's last row near the bottom of the page.",
    "heading": "The content is a document's title, or a heading that names a section of it, set on its own "
               "line. Counts: a title, section and subsection headings, and numbered headings like \"3.2 "
               "Methods\". Doesn't count: a table's column or row headings, a figure's label, or bold words "
               "at the start of a paragraph.",
    "caption": "The content is the caption of a table or figure: the text that names and describes it, "
               "usually starting \"Table 2\" or \"Figure 3\". Doesn't count: notes under a table, or text "
               "inside the figure.",
    "footnote": "The content is a note keyed to a mark in the text: a footnote at the foot of a page, an "
                "endnote, or a note under a table. Counts: table notes like \"a P < 0.05 versus control\" "
                "and source lines under a table. Doesn't count: a running footer, or an entry of a "
                "reference list.",
    "list": "The content is an item of a list: a bulleted, numbered or lettered list, or an entry of a "
            "reference list or bibliography. Doesn't count: a table row, a numbered heading, or a paragraph "
            "that merely starts with a number.",
    "code": "The content is source code, a command, a configuration or other text set as code, usually in a "
            "monospaced font or a code block. Doesn't count: a variable name or file name in ordinary prose "
            "that isn't set as code.",
    "multi_column": "The content sits inside one column of a page laid out in two or more columns side by "
                    "side: a paragraph, heading, list, table or figure that fits within one column. Counts: "
                    "either column of a two-column article, a sidebar beside body text, either page of a "
                    "scan or photo that shows two facing pages. Doesn't count: content that runs across the "
                    "full width (a title, or a table or figure spanning all columns), or the columns of a "
                    "table on a page that isn't laid out in columns.",
    "tiny": "The content is printed small: noticeably smaller than the page's ordinary body text, as fine "
            "print is, about 6 pt or less on a printed page. Counts: footnotes and legal fine print set "
            "small, dense small type in tables or forms, small labels on drawings. Doesn't count: text set "
            "a little smaller than body text, such as a running header; ordinary body text in a "
            "low-resolution image; or text that only looks small because the whole page is photographed "
            "from far away or, for a large sheet, shrunk to fit the image.",
    "rotated": "The content's text is turned or tilted enough that a reader notices, as seen in the image: "
               "by about 90 or 180 degrees, set vertically, or tilted by about 5 degrees or more. Counts: a "
               "page turned on its side or upside down, vertical text, a table set sideways, a page "
               "photographed at a clear slant. Doesn't count: a slight tilt under about 5 degrees, as a "
               "scanner leaves it, or italic text.",
    "handwriting": "The content is written by hand. Counts: handwritten values in a form, notes in a margin, "
                   "signatures, handwritten letters and manuscripts. Doesn't count: typed text in a "
                   "script-style font, or a printed facsimile of a signature that is clearly typeset.",
    "degraded": "The content is harder to read in the image than in a clean scan, because of the image's "
                "condition. Judge the image's condition, not the writing: handwriting that is also blurred, "
                "faded or noisy counts. Counts: blur, fading, noise or speckle, stains, bleed-through from "
                "the other side, heavy compression artefacts, very low resolution, or a photocopy of a "
                "photocopy. Doesn't count: small print alone, neat handwriting in a clean image, or a clean "
                "scan on a coloured or yellowed background.",
}
assert set(TAG_DEFINITIONS) == {*ROLES, *YES_NO, *COMPUTED}
# The two answers a yes/no tag's question takes, named for the property, so that a model's "yes" can't
# be read as "yes, the text is where it is marked".
ANSWERS = {"table": ("in_table", "not_in_table"), "math": ("math", "not_math"),
           "form": ("form_field", "not_form_field"), "multi_column": ("in_columns", "not_in_columns"),
           "tiny": ("tiny", "not_tiny"), "rotated": ("rotated", "not_rotated"),
           "handwriting": ("handwritten", "not_handwritten"), "degraded": ("degraded", "not_degraded")}
assert set(ANSWERS) == set(YES_NO)
