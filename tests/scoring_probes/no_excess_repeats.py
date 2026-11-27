# ruff: noqa: E501
"""Cases for docs/scoring/no_excess_repeats.md."""
from cases import excess, table

A = "The committee met on Monday to review the budget and the plans for the new library downtown."
B = "Members asked for a second estimate before the vote."
PAGE = f"{A} {B}"
SHORT = "Total due on receipt of this invoice."
G = "the page's two sentences"
C8, D8 = "one two three four five six seven eight", "nine ten eleven twelve thirteen fourteen fifteen sixteen"
ROW = "Not applicable, see note one for the details of the lease terms and the fees listed in the annex"
WRAP = "The self-aware system logs each request it serves and the reply it sends back to the client."

TABLES = [
    table(
        "repeats-ignored",
        excess("rx-faithful", "I", "the page as printed", PAGE, f"<p>{A}</p><p>{B}</p>", shown_gold=G),
        excess("rx-reordered", "I", "its blocks in another order", PAGE, f"<p>{B}</p><p>{A}</p>", shown_gold=G),
        excess("rx-markup", "I", "spacing, case and markup", PAGE, f"<p><b>THE COMMITTEE</b> met  on Monday to review the budget and the plans for the new library downtown.</p><p>{B}</p>", shown_gold=G),
        excess("rx-printed-twice", "I", "a passage the page prints twice, written twice", f"{A} {A}", f"<p>{A}</p><p>{A}</p>", shown_gold="the first sentence, twice"),
        excess("rx-short-repeat", "I", "a phrase shorter than 16 words written twice", SHORT, f"<p>{SHORT}</p><p>{SHORT}</p>"),
        excess("rx-dropped", "I", "text left out (other tests miss it)", PAGE, f"<p>{A}</p>", shown_gold=G),
        excess("rx-table", "I", "a table the page prints, as a table", f"{PAGE} {ROW} {ROW}", f"<p>{A}</p><p>{B}</p><table><tr><td>{ROW}</td></tr><tr><td>{ROW}</td></tr></table>", shown_gold="the page's two sentences and its table's two rows"),
        excess("rx-table-pipe", "I", "the same table as a markdown table left in a paragraph", f"{PAGE} {ROW} {ROW}", f"<p>{A}</p><p>{B}</p><p>| {ROW} |\n| {ROW} |</p>", shown_gold="the page's two sentences and its table's two rows"),
        excess("rx-table-flat", "I", "the same table flattened to paragraphs", f"{PAGE} {ROW} {ROW}", f"<p>{A}</p><p>{B}</p><p>{ROW}</p><p>{ROW}</p>", shown_gold="the page's two sentences and its table's two rows"),
        excess("rx-math", "I", "math is not read", PAGE, f"<p>{A}</p><p>{B}</p><p>$x x x x x x x x x x x x x x x x x x x x x x x x x x x x x x x x$</p>", shown_gold=G),
        excess("rx-alt", "I", "an image description is not read", PAGE, f"<p>{A}</p><p>{B}</p><img alt='{A} {A}'>", shown_gold=G),
        excess("rx-figure", "I", "a figure's text is not read, its caption is", PAGE, f"<p>{A}</p><p>{B}</p><figure><p>{A}</p><figcaption>Figure 1.</figcaption></figure>", shown_gold=G),
        excess("rx-wrapped", "I", "a compound broken at a line end, written twice where the page prints it twice", f"{WRAP} {WRAP}", f"<p>The self-<br>aware system logs each request it serves and the reply it sends back to the client.</p><p>{WRAP}</p>", shown_gold="the sentence twice"),
    ),
    table(
        "repeats-blind",
        excess("rx-once-invented", "B", "an invented passage written once", PAGE, f"<p>{A}</p><p>{B}</p><p>The library will open in the spring of next year, and the city will pay for most of it.</p>", shown_gold=G),
        excess("rx-near-copy", "B", "a copy with one word changed in every 16", PAGE, f"<p>{A}</p><p>The committee met on Tuesday to review the budget and the plans for the new library downtown.</p><p>{B}</p>", shown_gold=G),
        excess("rx-tail-restart", "B", "a restart that repeats fewer than 16 words", PAGE, f"<p>{A} to review the budget and the plans for the new library downtown. {B}</p>", shown_gold=G),
        excess("rx-common-words", "B", "a repeat of words the page prints often enough elsewhere", f"{A} {A} {B}", f"<p>{A}</p><p>{A}</p><p>{B}</p><p>{B}</p>", shown_gold="the first sentence twice, the second once"),
        excess("rx-loop-hyphens", "B", "a loop of one word joined by hyphens: one word", PAGE, f"<p>{A}</p><p>{B}</p><p>{'-'.join(['budget'] * 40)}</p>", shown_gold=G),
        excess("rx-loop-counter", "B", "a loop with a number that changes every 8 words", PAGE, f"<p>{A}</p><p>{B}</p><p>{' '.join(f'item {i} and the plans for the library' for i in range(1, 13))}</p>", shown_gold=G),
        excess("rx-short-blocks", "B", "two 8-word blocks each doubled in place (A A B B): no run of 16 repeats", f"{C8} {D8}", f"<p>{C8}</p><p>{C8}</p><p>{D8}</p><p>{D8}</p>", shown_gold="two 8-word blocks"),
    ),
    table(
        "repeats-penalized",
        excess("rx-duplicate", "P", "a sentence written twice", PAGE, f"<p>{A}</p><p>{A}</p><p>{B}</p>", shown_gold=G, why=True),
        excess("rx-loop", "P", "a loop", PAGE, f"<p>{A}</p><p>{B}</p><p>{'and the plans ' * 12}</p>", shown_gold=G, why=True),
        excess("rx-loop-word", "P", "one word repeated", PAGE, "<p>" + "budget " * 40 + "</p>", shown_gold=G),
        excess("rx-page-twice", "P", "the whole page written twice", PAGE, f"<p>{A}</p><p>{B}</p><p>{A}</p><p>{B}</p>", shown_gold=G),
        excess("rx-printed-twice-three", "P", "a passage the page prints twice, written three times", f"{A} {A}", f"<p>{A}</p><p>{A}</p><p>{A}</p>", shown_gold="the first sentence, twice", why=True),
        excess("rx-paragraph-split", "P", "a duplicate split over two blocks", PAGE, f"<p>{A}</p><p>The committee met on Monday to review the budget</p><p>and the plans for the new library downtown.</p><p>{B}</p>", shown_gold=G),
        excess("rx-table-row-twice", "P", "a table row written twice in a table", f"{PAGE} {ROW}", f"<p>{A}</p><p>{B}</p><table><tr><td>{ROW}</td></tr><tr><td>{ROW}</td></tr></table>", shown_gold="the page's two sentences and its table's row"),
        excess("rx-short-blocks-across", "P", "the same two blocks written A B A B: a run of 16 repeats across them", f"{C8} {D8}", f"<p>{C8}</p><p>{D8}</p><p>{C8}</p><p>{D8}</p>", shown_gold="two 8-word blocks"),
    ),
]
