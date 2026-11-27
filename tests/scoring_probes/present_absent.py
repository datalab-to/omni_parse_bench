# ruff: noqa: E501
"""Cases for docs/scoring/present-absent.md."""
from cases import absent, table

H = "Johnathan Quincy Smithers"     # the name under a synthetic redaction, 25 characters after fold
NEXT = "Chapter 4. The harbor at night"      # the first line of the next page
SIGN = "North station opens Tuesday"     # a synthetic notice's two lines, read in the other order

TABLES = [
    table(
        "absent-ignored",
        absent("ab-faithful", "I", "the page as printed: the box is left out", H, "<p>Patient name:</p><p>Date: 12 May 2021</p>", md=3),
        absent("ab-box", "I", "the box written as a mark", H, "<p>Patient name: ████</p>", md=3),
        absent("ab-redacted-word", "I", "the box named", H, "<p>Patient name: [REDACTED]</p>", md=3),
        absent("ab-over-budget", "I", "a reading further off than the budget", H, "<p>Patient name: John Smith</p>", md=3),
        absent("ab-part", "I", "part of the text, short of the budget", NEXT, "<p>Chapter 4.</p>", md=2),
        absent("ab-number-changed", "I", "a digit changed: numbers are exact, as in `present`", "Account number 4417 1234 5678 9113", "<p>Account number 4417 1234 5678 9112</p>", md=2),
        absent("ab-alt", "I", "in an image description, which is not read (`present` reads it)", H, "<img alt='Patient name: Johnathan Quincy Smithers'>", md=3),
        absent("ab-text-order", "I", "a two-line notice in the order its text layer reads", SIGN, "<p>Opens Tuesday</p><p>North station</p>", md=3),
    ),
    table(
        "absent-blind",
        absent("ab-paraphrase", "B", "a paraphrase or a translation of it", NEXT, "<p>Kapitel 4. Der Hafen bei Nacht</p>", md=2),
        absent("ab-split", "B", "its words apart, with other text between", H, "<p>Patient name: Johnathan</p><p>Signed by Quincy Smithers</p>", md=3),
    ),
    table(
        "absent-penalized",
        absent("ab-read-through", "P", "the hidden text read through the box", H, "<p>Patient name: Johnathan Quincy Smithers</p>", md=3, why=True),
        absent("ab-near", "P", "a near copy, within the budget", H, "<p>Patient name: Jonathan Quincy Smithers</p>", md=3),
        absent("ab-case-spacing", "P", "another case and spacing", H, "<p>PATIENT NAME:JOHNATHAN QUINCY SMITHERS</p>", md=3),
        absent("ab-table", "P", "in a table cell", H, "<table><tr><td>Patient name:</td><td>Johnathan Quincy Smithers</td></tr></table>", md=3),
        absent("ab-markdown", "P", "in markdown", H, "**Patient name:** Johnathan Quincy Smithers", md=3, from_markdown=True),
        absent("ab-next-page", "P", "the next page's first line", NEXT, "<p>The end of the chapter.</p><p>Chapter 4. The harbor at night</p>", md=2),
        absent("ab-line-hyphen", "P", "a word broken at a line end", NEXT, "<p>Chapter 4. The har- bor at night</p>", md=0),
        absent("ab-other-order", "P", "the same notice, faithful, in its other reading order: why a test is authored only where no reading holds it", SIGN, "<p>North station</p><p>Opens Tuesday</p>", md=3, why=True),
    ),
]
