# The chain and the distance

A text claim is read at one point of a chain, and matched by one distance. The code is `omni_parse_bench/chain.py`
(the search) and `omni_parse_bench/fold.py` (the Id to Text fold, as a table of operations). Every rule below is a
named switch (`omni_parse_bench/switches.py`, `OPB_SWITCHES`), off until the rules ship together. With the switch
`chain` on, `present` text tests are matched this way; the rules are the chain's own and are read only then.

## The points

The gold and the output are read at the same point, and the point fixes which edits are free.

| point | what it adds to the one before | free in the distance |
|---|---|---|
| Id | every character the reader holds | nothing |
| Text | typography folded (the reader's fold); footnote marks kept | a wrapped hyphen of the output |
| Cased | footnote marks deleted | a space of the gold; a space between two Hangul syllables or two phrase-spaced clusters (both sides); a line or block break |
| Words | case of words folded, `İ` as `i` first; a quantity keeps its case | the same as Cased |

A claim that needs its case (`exact_case`) is read at Cased with no budget: case-protected edits with a budget
would be defeated by deleting a letter and inserting its other case.

## The distance

OSA (Damerau-Levenshtein without repeated edits of one stretch) over grapheme clusters, with token classes known.

| rule (switch) | what it does |
|---|---|
| `word_edges` | a match starts and ends at token edges: `Total` is not found in `Totally`, nor `cat` in `concatenate` |
| `space_one_sided` | from Cased on a space of the gold is free, a space of the output is not: `Total Due` matches `TotalDue`, `therapist` does not match `the rapist`. Off: spaces are free on both sides |
| `osa` | a swap of two neighbouring characters is one edit; off, two |
| `qty_atomic` | a quantity matches its own spelling for nothing and any other edit touching one costs more than any budget: `10kg` never matches `10mg`, `45` does not match `45%` |
| `marks_free` | from Cased on a footnote mark is deleted from the gold and the output (a gold that is only marks keeps them) |
| `wrap_free` | a hyphen wrapped over a line end is free in the output, or equal to a gold `-` |
| `break_free` | from Cased on a line or block break may be deleted; a break always matches a gold space |
| `cell_windows` | a window stays inside one table cell |

A failed claim names the rules whose switching off alone would have passed it: `[space_one_sided] 'therapist'
not found ...`. Without such a rule the code is `[chain]`.

## Laws

Tokens are fixed per output, so a window at one point is a window at every coarser point (the raw candidates only
grow along the chain). Each law is a test: inclusion of windows across Text, Cased and Words; the fold applied
twice is the fold applied once; a swap of gold and output gives the same whole-string verdict at Text.

## Circled digits, whole units and fold spans

- A circled or parenthesized digit (`①`, `⑩`, `⑴`) is the digit (condition A1: a careful reader takes `①` and `1` as the same enumerator). `fold.enumerator_digits` maps it before the reader scans for quantities and `FOLD` lists it as `enumerators`, so `①` is a quantity like any digit: it matches `1`, and `①` against `②` fails at any budget (relations M215, M216).
- Whole mode (`equal`) compares the entire supplied unit. An empty gold equals an empty unit (free spaces and breaks aside); a unit whose content spans more than one table cell is refused, not narrowed to one cell.
- A token the fold rewrites keeps the markup and source span of the characters it came from, not of the run it sat in: `<p>ﬁ <b>X</b></p>` still reads `X` as bold.
- A parenthesized digit keeps its parentheses: `⑴` reads `(1)`, so it matches `1` as a claim found inside it and equals `(1)` as a whole, but a whole unit `⑴` is not equal to a whole `1` (the punctuation is a symbol of its own). The circled digit has no punctuation and equals the digit either way.

## Scope of this step, and one choice

- The chain change itself moved only a `present` text test onto the chain (the `chain` switch): its content, `absent` included. The claim contract change (`schema.md`) adds `order` (also `chain`) and the `verbatim` region (`region`). `repeat`, number, blank fields, `table_cell` and `format` keep their own readings until later changes move them onto it.
- A gold that is nothing but footnote marks (`[25]`) keeps them at Cased, and so does the output it is read against: with the marks free the gold would be empty and unmatchable. A gold with any other content treats marks as free from Cased on.

## Underscores

A run of three or more underscores (and the other leaders: dots, dashes, equals signs, asterisks) folds to a space at Text, except underscores alone that touch a letter or a digit on either side (`token____`, `foo___bar`, `____init`): part of an identifier, which Text keeps.
