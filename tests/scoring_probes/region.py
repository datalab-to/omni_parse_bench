# ruff: noqa: E501
"""Cases for docs/scoring/region.md."""
from cases import region, table, text

D, P = "Date of birth:", "Place of birth:"
FORM = "<p>Name: Ann Lee</p><p>Date of birth: {}</p><p>Place of birth: Paris</p>"
TABLE = "<table><tr><td>Rent</td><td>100</td></tr><tr><td>Fuel</td><td>70</td></tr></table>"

TABLES = [
    table(
        "region-ignored",
        region("rg-blank", "I", "a blank field", D, P, None, FORM.format("")),
        region("rg-blank-line", "I", "a line to write on (three or more underscores or dots, which fold removes)", D, P, None, FORM.format("______")),
        region("rg-blank-leader", "I", "a run of dots", D, P, None, FORM.format(".........")),
        region("rg-blank-markup", "I", "an empty element, a line break, a zero-width space", D, P, None, FORM.format("<span></span><br>​")),
        region("rg-mask", "I", "the printed mask, as html", D, P, "__/__/____", FORM.format("__/__/____")),
        region("rg-mask-lost", "I", "the mask's underscores left out: a printed line is not compared", D, P, "__/__/____", FORM.format("//")),
        region("rg-mask-markdown", "I", "the printed mask written as markdown, which reads its underscores as emphasis", D, P, "__/__/____", "Name: Ann Lee\n\nDate of birth: __/__/____\n\nPlace of birth: Paris", from_markdown=True),
        region("rg-spacing", "I", "spacing, case and markup inside the region", "Abstract", "Introduction", "We study parsing. It is hard.", "<h2>ABSTRACT</h2><p>We  study <b>parsing</b>.<br>It is hard.</p><h2>Introduction</h2>"),
        region("rg-hyphen", "I", "a compound broken at a line end", None, None, "A self-aware system", "A self-<br>aware system"),
        region("rg-hyphen-joined", "I", "a word broken at a line end, joined in the gold", None, None, "Our developers", "Our develop-<br>ers"),
        region("rg-across-table", "I", "the region runs across a table, cell by cell", "Table 2. Costs", "The costs fell", "Rent 100 Fuel 70", f"<p>Table 2. Costs</p>{TABLE}<p>The costs fell.</p>"),
        region("rg-table-end", "I", "nothing after a table's last cell", "Fuel 70", "The costs fell", None, f"{TABLE}<p>The costs fell.</p>"),
        region("rg-two-copies-clean", "I", "the page written twice, both copies right", D, P, None, FORM.format("") * 2),
        region("rg-within-budget", "I", "a misread letter within the budget", "Table 3", "Mean", "Results of the trial", "<p>Table 3 Results of the trail</p><p>Mean</p>", md=2),
        region("rg-whole-page", "I", "no anchors: the whole page", None, None, "Page intentionally left blank", "<p>Page intentionally<br>left blank</p>"),
    ),
    table(
        "region-blind",
        region("rg-alt", "B", "an image description in the region is not read", D, P, None, FORM.format("<img alt='12/03/1985'>")),
        region("rg-before-start", "B", "text before the start is outside the region", D, P, None, "<p>12/03/1985 Date of birth:</p><p>Place of birth: Paris</p>"),
        region("rg-header-row", "B", "a header-row table reads its labels first, then its values", D, P, None, "<table><tr><td>Date of birth:</td><td>Place of birth:</td></tr><tr><td>12/03/1985</td><td>Paris</td></tr></table>"),
        region("rg-budget-letters", "B", "letters added within the budget", "Table 3", "Mean", "Results of the trial", "<p>Table 3 Results of the trial a</p><p>Mean</p>", md=2),
    ),
    table(
        "region-alt",
        text("rg-alt-present", "I", "`present` reads an image description", "a bar chart of rates by year", "<p>Figure 2</p><img alt='A bar chart of rates by year'><p>Source: WHO</p>"),
        region("rg-alt-region", "P", "`region` does not: author regions only where no figure is", "Figure 2", "Source: WHO", "A bar chart of rates by year", "<p>Figure 2</p><img alt='A bar chart of rates by year'><p>Source: WHO</p>"),
    ),
    table(
        "region-penalized",
        region("rg-filled", "P", "a value in a blank field", D, P, None, FORM.format("12/03/1985"), why=True),
        region("rg-filler", "P", "a filler for a blank", D, P, None, FORM.format("N/A"), why=True),
        region("rg-dash", "P", "a dash for a blank", D, P, None, FORM.format("—")),
        region("rg-mask-filled", "P", "the mask filled in", D, P, "__/__/____", FORM.format("12/03/1985")),
        region("rg-second-copy", "P", "the page written twice, one copy filled", D, P, None, FORM.format("") + FORM.format("1985"), why=True),
        region("rg-second-cell", "P", "a value two cells right of the label", D, P, None, "<table><tr><td>Date of birth:</td><td></td><td>1985</td></tr><tr><td>Place of birth:</td><td>Paris</td></tr></table>"),
        region("rg-split-table", "P", "a value in a second table", D, P, None, "<table><tr><td>Date of birth:</td></tr></table><table><tr><td>1985</td></tr></table><p>Place of birth: Paris</p>"),
        region("rg-row-after", "P", "a row added after a table, as a paragraph or a second table", "Fuel 70", "The costs fell", None, f"{TABLE}<p>Total 170</p><p>The costs fell.</p>", why=True),
        region("rg-duplicate-sentence", "P", "a sentence written twice (a loop)", "Abstract", "Introduction", "We study parsing. It is hard.", "<p>Abstract</p><p>We study parsing. It is hard. It is hard.</p><p>Introduction</p>", why=True),
        region("rg-caption-added", "P", "a sentence added to a caption", "Table 3", "Mean", "Results of the trial", "<p>Table 3 Results of the trial. Source: WHO</p><p>Mean</p>", md=2),
        region("rg-number-in-budget", "P", "a number changed, within the budget", "Table 3", "Mean", "Results of 2019", "<p>Table 3 Results of 2018</p><p>Mean</p>", md=2, why=True),
        region("rg-number-split", "P", "a number split by a space", None, None, "Total 12500", "Total 12 500", why=True),
        region("rg-missing-text", "P", "text of the region left out", "Abstract", "Introduction", "We study parsing. It is hard.", "<p>Abstract</p><p>We study parsing.</p><p>Introduction</p>"),
        region("rg-no-start", "P", "the start not on the page", D, P, None, "<p>Place of birth: Paris</p>", why=True),
        region("rg-no-end", "P", "the end not on the page", D, P, None, "<p>Date of birth:</p>", why=True),
        region("rg-end-first", "P", "the end only before the start", D, P, None, "<p>Place of birth: Paris</p><p>Date of birth:</p>", why=True),
        region("rg-glued", "P", "words glued together: a space is text", "Abstract", "Introduction", "We study parsing.", "<p>Abstract WeStudyParsing. Introduction</p>"),
        region("rg-split-word", "P", "a word split in two", None, None, "Please sign into the portal", "Please sign in to the portal", why=True),
        region("rg-hyphen-dropped", "P", "a hyphen inside a word dropped (`re-sign` is not `resign`)", None, None, "re-sign the lease", "resign the lease", why=True),
        region("rg-underscore", "P", "an underscore inside a name dropped", None, None, "set max_rows", "set maxrows"),
        region("rg-hyphen-space", "P", "a hyphen a line broke after, read as a space", None, None, "A self aware system", "A self-<br>aware system", why=True),
        region("rg-sign", "P", "a sign changed, within the budget", None, None, "Net -12.5", "Net +12.5", md=2, why=True),
        region("rg-decimal", "P", "a decimal point written as a comma, within the budget", None, None, "Rate 1.25", "Rate 1,25", md=2),
        region("rg-longer-label", "P", "the start inside a longer label opens a region too: a start must be unique on the page", D, P, None, "<p>Date of birth:</p><p>Place of birth: Paris</p><p>Mother's Date of birth: 1960</p><p>Mother's Place of birth: Rome</p>", why=True),
        region("rg-footnote", "P", "a footnote marker the content does not hold", "Abstract", "Introduction", "We study parsing.", "<p>Abstract</p><p>We study parsing.<sup>1</sup></p><p>Introduction</p>"),
        region("rg-whole-page-extra", "P", "no anchors: a line added to the page", None, None, "Page intentionally left blank", "<p>Page intentionally left blank</p><p>This page is empty.</p>", why=True),
    ),
]
