# Omni Parse Bench: design

1. [Mental model](#mental-model): what a test is, and what a provider does;
2. [Vocabulary](#vocabulary): output types, test types, tags and derivations;
3. [Data layout](#data-layout): the manifest, the page files and the gold files;
4. [Predict](#predict): what a provider is asked for;
5. [Score](#score): how a test is graded, and the headline;
6. [Benchmark](#benchmark): what a run writes; and
7. [Package](#package): the modules, and what each holds.

## Mental model

The benchmark works page by page, not document by document. Each page has a number of tests, and
each test is a yes/no question about it.

Each test has:

- an output type: which output of a prediction it reads, the page's HTML or its layout blocks;
- a test type: how that output is checked, for instance "this string appears";
- tags: what the content it checks is, for instance in a table, handwritten, French. Tags select
  tests and never change a verdict; and
- a derivation: how its answer was established, for instance the publisher's markup or a panel of
  models.

A provider makes whatever calls it needs to fill the outputs a page's tests read.

## Vocabulary

Output types, test types, derivations and tags (bar script and language codes) are closed sets
(`vocab.py`, `runners.TYPES`). New data is first checked against them; a value is added only when
the existing ones can't describe it.
Counts are of the published dataset: 2,937 pages, 16,288 tests.

### Output types

| output type | asked for | value | tests |
|---|---|---|---:|
| `html` | transcribe the page, keeping everything on it | an HTML string | 13,901 |
| `blocks` | the page's layout blocks, with boxes, kinds and text | a list of blocks | 2,403 |

Providers deliver each value in exactly this form.

### Test types

A test type is one mechanism of checking; its parameters are only what differs from test to test.

A test compares pieces of content, its args. An arg is one of three kinds, and its kind says how it
is found in an output (`runners.found`):

- text (`{"text", "max_diffs"}`, and optionally `place`, its boxes on the page): found within
  `max_diffs` edits, after both sides are folded;
- a number (`{"number"}`): found digit for digit, with its separators as written (`1,240` is not found as
  `1240`, `1 240` or `1.240`). A number the scorer cannot read as one number, such as `12,5`, whose comma could be
  a decimal or a thousands mark, doesn't load; and
- an equation (`{"latex"}`): found by what KaTeX renders it to, or, for an equation plain text
  writes without loss, by its text reading. Its LaTeX must render to at least one symbol, else the
  test doesn't load: LaTeX that doesn't render would fail on every output, and LaTeX that renders
  to nothing (`\quad`) would pass on every output.

A `layout_kind` test's text only labels its place; it is never compared.

Case is folded by default: it isn't what most parses are paid for. A text arg of a `present` test may set
`exact_case: true` (false when omitted), for content whose case is the point (`iPhone`, `NASA`, `Co` and `CO`, a German noun). The
arg then passes only when its text is found with its case kept: `normalize.fold_cased` applies every other fold
(glyphs, spacing, quotes, dashes, hyphens) and leaves case alone, on both sides, in every path of `found`
(footnote markers, hyphen wrapping, squeezed text). `exact_case` and a `max_diffs` above 0 exclude each other: a changed letter's case costs one edit, so a budget would let the wrong case pass, and the loader refuses the pair (use `max_diffs: 0`, or drop `exact_case`). Numbers and equations have no case, and the other test types do not read it yet, so the field is refused
there when the test loads. The text must also have a cased letter (`123` has no case to keep), or the field is refused.

`exact_case` keeps the case of letters only, and it compares the page's text, not how it looks. Limits:
- Two folds that are not case still apply: a checkbox mark (`[x]` and `[X]`, `[checked]` and `[Checked]`,
  `[unchecked]` and `[UNCHECKED]` are one box each, since the checkbox patterns ignore case) and the glyph
  unification of NFKC (`µ` micro sign and `μ` Greek mu are one letter).
- Styling that changes how text looks, not what it is, is not read: `text-transform: uppercase` or small caps
  on lowercase text leaves the text lowercase, so an uppercase gold fails on a page that only looks uppercase,
  and a lowercase gold passes on it (cases `text-exact-case-css-upper`, `text-exact-case-small-caps`,
  `text-exact-case-css-lower`).
- Image descriptions (`alt`) are part of the text, so a string there counts, in its case
  (`text-exact-case-alt`).

A `repeat` test counts a text or a number: its content is the same kind of arg, and `expected_count` says how
many copies the page holds. A text is counted as whole words after folding; a number is counted as `present`
finds it (digit for digit, `runners._number_copies`), line by line and without the digits a footnote mark or a
list adds; the count, not the kind, is what a `repeat` test adds.

Text presence also accepts an exact match through an ambiguous wrapping hyphen:
`মানু- হৰ` can match `মানুহৰ`. The hyphen must follow a letter or its combining marks,
have whitespace after it, and precede a letter that is neither uppercase nor titlecase (or, in a heading in
capitals, a capital after a word in capitals).
The rule applies to the gold and the prediction alike, as the existing Latin line-break rule does.
The original hyphenated interpretation remains available, so a wrapped compound still
matches its hyphenated gold. An unspaced compound hyphen remains required; dashes and
numeric signs receive no new exemption. This fallback must actually omit a continuation
hyphen inside the match, or retain one that the Latin line-break rule would remove,
and does not add fuzzy letter edits. Order, repetition and table-cell comparisons accept the same exact
reading where their own comparison fails, and add no other way to pass; numbers and equations retain their
existing rules.

| test type | reads | checks | args and settings | family | tests |
|---|---|---|---|---|---:|
| `present` | `html` | this content appears | `content` | text | 7,275 |
| `order` | `html` | A comes before B | `before`, `after` (text) | text | 1,189 |
| `repeat` | `html` | this line, or this number, appears exactly N times | `content` (text or number); `expected_count` | text | 35 |
| `page_near_empty` | `html` | a blank page yields at most N non-space characters (not invisible format characters, nor the marks the text view writes for an element that holds nothing) | no args; `max_chars` | text | 0 |
| `table_cell` | `html` | this cell exists with these neighbors, under these headings, in this section and in these row groups; the cell may be one line of a multi-line cell | `cell`, `up`, `down`, `left`, `right`, `top_heading`, `left_heading`, `right_heading`, `headings`, `section`, `row_groups` (text) | tables | 5,386 |
| `layout_kind` | `blocks` | the smallest block covering half of this line's place has this kind | `content` (text with a `place`); `kind` | layout | 2,403 |
| `format` | `html` | this span of text carries these marks (bold, italic, underline, strikethrough, superscript, subscript) and the words around it do not; or carries none of them | `span`, optional `before`, `after` (text, `max_diffs` 0); `marks` or `absent` | format | 0 |

Of the `present` tests, 3,684 compare text, 3,268 an equation and 323 a number.

What each test type reads, ignores and penalizes, with the probes behind each statement, is in the
[scoring reference](scoring/README.md).

A `table_cell` test reads structure from the markup, not from how the page looks. A heading or
row-group label covers the cells it is encoded over: merged (`colspan`, `rowspan`), repeated in each,
or written once beside (a heading) or above (a row-group label) empty cells, as a printed table shows
a merged label.

A `layout_kind` test's kind is one of `views.LABELS`; the dataset tests `text` (1,427), `table`
(598) and `heading` (378). Each adapter maps its vendor's block types onto the labels
([providers.md](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/providers.md)); `form` is a form field or a key-value pair, or a region of them,
which Reducto, Extend and LlamaParse give as key-value types ([providers.md](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/providers.md#block-labels)).
For a `text` test, a block labelled `list` or `form` passes too
(`runners.AS_TEXT`): a list item or a key-value field is running text, and vendors differ in whether
they give such a line a block of its own, which the test doesn't ask about.

### Tags

A test's tags say what the content it checks is (`vocab.TAG_DEFINITIONS` defines each):

- roles: heading, caption, footnote, list, code, figure and header_footer;
- yes/no properties: table, math, form, multi_column, tiny, rotated, handwriting and degraded; and
- script and language: the script of its text (an ISO 15924 code, such as `Latn`), computed from
  Unicode, and its language (an ISO 639-3 code, such as `eng`), from a language identifier or, when
  that is unsure, the model panel.

A test has every tag of every piece of content it compares (each a span). Tags overlap, so they
select tests and are scored one tag at a time (summarize the tests of one tag), never averaged into a score.
[`tagging.md`](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/tagging.md) says how they were made.

### Derivations

| derivation | how the answer was established | tests |
|---|---|---:|
| `publisher_markup` | the publisher's JATS XML: table cells with their headings, sections and row groups | 4,919 |
| `upstream_olmocr` | olmOCR-bench's own tests | 4,386 |
| `model_panel` | independent models agree on what the page says; no model in the results table sits on a panel | 3,613 |
| `authored` | we made the page or filled the form, so we know what's on it | 1,402 |
| `rendered_source` | we rendered the page from markup we hold (a document written with its marks), so each mark is known | 0 |
| `extractor_agreement` | independent text extractors (two, or three on `tiny_plans`) agree on the line | 823 |
| `text_layer` | read off the PDF's own text layer: its words, their boxes, their font flags | 521 |
| `source_transcription` | the source's own transcription of a handwritten page (the handwriting_samples suite) | 284 |
| `human_review` | a recorded correction of a test | 180 |
| `model_review` | a vision model read the page, blind to which reading was the test's, and corrected the test, for a test type an audit cleared | 102 |
| `upstream_frbench` | written by fr-bench-pdf2md for its hand-filled forms | 74 |
| `computed` | computed from a definition (a function at the arguments printed on the page) or matched to a digital twin of the page, kept only where it agrees with the print | 0 |

## Data layout

The dataset is the source of truth. A correction is an edit to it: a test is fixed or removed in
its gold file, and a page is removed with its files and its manifest row.

```
manifest.parquet       one row per page
pages/<page_id>.pdf    the page that gets sent: a one-page PDF,
pages/<page_id>.png    or an image
gold/<page_id>.json    the page's tests
```

### A manifest row

| column | example | what it's for |
|---|---|---|
| `page_id` | `realdoc_pdfs-0103655f_docs_finance_2-p1` | the key; the files carry it |
| `document` | `realdoc_pdfs:0103655f_docs_finance_2` | the source document: a page's copies and siblings share one, since their tests pass or fail together |
| `suite` | `realdoc_pdfs` | where the page came from; its license is in `licenses/` |
| `doc_path` | `pages/<page_id>.pdf` | the input: a path inside the dataset, named `<page_id>.pdf` or `.png` |
| `gt_path` | `gold/<page_id>.json` | the tests: a path inside the dataset, named `<page_id>.json` |
| `outputs` | `["html", "blocks"]` | what to predict for the page: the output types its tests read, so planning a run reads the manifest alone. Made from the gold when the dataset is published, and checked against it whenever the gold is read; a manifest from before the column has it read from the gold |

A dataset holds `manifest.parquet`, and may hold others (`--manifest`): a sample of its pages, or the same
pages with a gold of another kind in another folder. Each manifest names its pages and where their gold is,
so a page file is never copied. A path's folder is free; its name must be the page's.

A manifest may carry other columns of its own (a language, a tag, a gold of another kind, for a scorer of
your own): omni-parse-bench reads none of them, refuses none of them, and keeps them on each page, read-only,
as `page.extra`.

The 2,937 pages come from 2,343 documents.

### `pages/<page_id>.pdf` or `.png`

The page the provider is sent, and nothing else. It's one of two kinds:

- a one-page PDF, cut from its source document when the dataset is made. 94% of the 1,889 source
  documents of PDF pages have one tested page; the 108 with several become several files; or
- an image, kept as it is: 788 pages (27%) are scans, page photos and composed pages that only
  exist as images. Wrapping them in PDFs would make providers that render PDFs resample the image.

### `gold/<page_id>.json`

The page's tests, as a JSON object (the two below are from different pages, to show both output
types). Each test carries everything its runner needs, so a test can be read, moved or filtered on
its own:

```json
{
  "tests": [
    {
      "id": "realdoc_pdfs_5ef783ea_p1_layer_0",
      "test_type": "present",
      "output_type": "html",
      "derivation": "human_review",
      "tags": ["Latn", "eng"],
      "args": {"content": {"text": "FILE THIS RETURN WITH THE DIRECTOR OF REVENUE, DIVISION OF COLLECTION, INCOME TAX UNIT,",
                           "max_diffs": 1}},
      "settings": {}
    },
    {
      "id": "olmo_arxiv_math-2503.08077_pg42-p1_line0_kind",
      "test_type": "layout_kind",
      "output_type": "blocks",
      "derivation": "model_panel",
      "tags": ["Grek", "Latn", "eng"],
      "args": {"content": {"text": "grates to a ﬂow φ.", "max_diffs": 0, "place": [[0.20706, 0.80399, 0.33729, 0.81846]]}},
      "settings": {"kind": "text"}
    }
  ]
}
```

| field | what it does |
|---|---|
| `id` | identifies the test; verdicts are keyed by it |
| `test_type` | how the test is marked: which runner grades it |
| `output_type` | what the test reads: which output of the prediction the runner opens |
| `derivation` | how the test's answer was established |
| `tags` | what the content it checks is |
| `args` | the content it compares, by role (`content`, `before`, `cell`, ...) |
| `settings` | the test type's other parameters (`kind`, `expected_count`) |

`scorers/unit_tests/tests.py` checks every field against the vocabulary when a test is loaded, and rejects anything
else. A page's output types are the ones its tests read, and aren't stored anywhere else. A test's
suite and document are its page's.

## Predict

```python
omni_bench_core.adapter.predict(system, task.Input(doc, wants)) -> record   # doc: a PDF of any length, or a .png
record["output"] == {"pages": [{"html": ..., "blocks": [...]}, ...]}         # one entry per page; a row is one
```

The benchmark asks a provider only for what a page's tests read: the page's `outputs` in the
manifest are the `wants`, and the adapter asks its system for those it can produce (`SUPPORTS`). A page
that wants none of them is not sent: its answer holds no outputs, with no call, no cost and no error.
There is no task-level or scorer-level choice of outputs. The record holds the outputs, the error
when the page failed, each call's answer as received (what was sent and the raw answer), and the
cost and time. A page fails, every test failed, only when the adapter says, on purpose, that the system failed, by
raising `SystemFailed` (the core's one rule, [omni-bench-core's "The rules"](https://github.com/datalab-to/omni-bench-core/blob/main/OVERVIEW.md#the-rules)); the record's
`error` keeps its `traceback`. An answer the adapter says it can't read is recorded as `Unreadable`, which
fails the page, keeping the raw answer. Any other exception is a bug and stops the run; a bug in reading an
answer keeps it unread (`"unread": true`), and the same command reads it again after the fix, with no
call. A fix to reading that gave wrong outputs without raising reaches a finished run with `opb reread`.

## Score

The scorer is `scorers/unit_tests`, a package that owns the shape of its gold: what a unit test is
(`tests.py`), how each test type is run (`runners.py`), and the functions every scorer has:

```python
gold(page) -> tests                              # the page's tests, from its gold file, checked
score(pred, gold) -> [Verdict(id, result, why)]
lines(verdicts, tests, page) -> [score line]     # each verdict beside its page and its test
summarize(lines) -> summary                      # over test lines: the headline and the families
check(pages) -> tests                            # every test of a dataset, and the dataset as a whole
```

A test's text and a provider's text view are compared after `fold` (normalize.py), the same function
on both sides, whose docstring lists every rule. Among them: a LaTeX span reads as the text it
renders, without the spaces math mode doesn't render ("$$2 . 5 5$$" is 2.55, "$U$" is U), and a word
broken by a hyphen at a line end is joined. A run of three or more dots, dashes or underscores (a leader) is a
space and never spans a block break; a present text test also retries with a footnote marker, written in brackets or set as a
superscript, dropped where it falls inside a phrase (order, repeat and table_cell do not). [The scoring reference](scoring/internals.md) lists each rule with a case that
shows it.

The headline is the mean of the families' scores: text (present, order, repeat, page_near_empty), tables
(table_cell) and layout (layout_kind), each family's score the share of its tests passed
(`vocab.FAMILIES` maps every test type to one). A fourth family, format (`format`), is reported beside
the headline and excluded from it when a headline family is present (`vocab.HEADLINE_FAMILIES`): it asks whether the output keeps a page's
bold, italic, underline, strikethrough, superscript and subscript, which every other test is certified
not to see (M7a), and adding it would change every published score. A dataset with no headline family has the mean of the families it has. Weighting by family rather than by test means a
family's weight never depends on how many tests it has: sampling more layout lines makes the layout
score more precise without making layout count more. The families are those the graded tests are
in, so a subset scores on the families it holds, and the summary lists them in a fixed order: text,
tables, layout (`vocab.FAMILY_ORDER`). A page whose call failed counts with every test
failed (`UnitTests.score_failure`, the omni-bench-core hook for a failed row's score), so it costs its tests, not a
page's share, and a run where every page failed has headline 0. The families and their mean are over every
page, a failed one's tests included.

The summary holds `score` (the headline), the families and an `auxiliary` map beside the core's counts. A suite may mix format and headline tests: its score pools only headline tests, and the top-level `auxiliary.format.per_suite` map reports format separately. Any other breakdown (by output type, test type,
arg kind, tag, suite or derivation) is computed from each test's verdict, kept in the run's
`details/<page_id>.jsonl` as a test line (its page, suite, document, test type, tags, derivation, and its args and
settings as the gold stated them, so a run's details say what each test looked for), and
from `opb tests`
([API.md](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/API.md#a-slice-of-the-benchmark)): it is the same summary over the tests selected.
Each family also counts the source documents its tests are from (`documents`, a raw count), read off its lines,
and `effective_documents`, what they are worth as equal-sized documents (scores are pooled over tests, so a
document with many tests weighs more). A tag or arg kind that has the same tests as another (by a 64-bit digest of their
ids) carries `same_tests_as` naming it, so a report can show the pair once. A document's tests
pass or fail together: one misread table fails all its cells, a page's image copy is the same page,
and a form's blank, filled and scanned copies are one form. The manifest's `document` column
records each page's document, set once when the page is added. So a score over few documents says less
than its test count suggests.

`opb intervals` puts an interval on each score, and `opb compare` compares two systems, both by resampling
documents: a document's tests pass or fail together, so the documents, not the tests, are the sample. Pages
with the same `document` are one cluster. Its limits are the dependence it can't see: copies of a page, or
one source document under several `document` values (across suites, or built and corrected by one
process), count as separate documents unless the manifest gives them one value. Scores are pooled over tests, so a
document with many tests weighs more, and the resampling already reflects that; `documents` is a raw count and
`effective_documents` is what the tests are worth as equal-sized documents. An interval says how much
one system's score on this dataset moves with its choice of documents; it does not reach past this dataset,
to other documents or to a change in the system. A comparison is paired, document by document, over the
documents both runs have, not a comparison of two overlapping intervals. The summary itself carries no
interval.

`opb reliability` asks, for each slice, whether it ranks several systems reproducibly. It splits the documents in
two at random many times and compares the two halves' rankings of the systems (`agreement`). It then does the
same with what is left of each system's slice pass rate after taking out what its pass rate on the other tests
predicts (`beyond_headline`): whether the slice ranks the systems by something the other tests don't. A slice
with a low `beyond_headline` is flagged, as `noisy` when its `agreement` is low too (it can't rank these systems
reproducibly at all) and `redundant` otherwise (it ranks them, but only as the other tests do). The halves are balanced by test count, since scores are pooled over tests (a document with many tests weighs
more) and a slice needs `min_documents` *effective* documents, the count its test counts are worth as equal-sized
documents, not the raw count. A flag is about
this dataset and these systems, not about whether the slice's tests are right. It depends on which systems are
in the set (at least 5, and near-identical ones rank by noise), a half of few documents is noisy, and nothing
corrects for looking at many slices at once.

### Going from a test JSON to running the test

`test_type` is the only link between a gold file and code. It's a key into one registry, which
pairs each test type's parameters with its runner:

```python
class Present(NamedTuple):
    content: Arg        # Text | Number | Latex

def present(t: Present, v: views.Html) -> tuple[bool, str]: ...

TYPES: dict[str, tuple[type[NamedTuple], Runner]] = {
    "present": (Present, present),
    "layout_kind": (LayoutKind, layout_kind),
    ...
}
```

A test runs in four steps:

- Load: `tests.test` checks the test against the vocabulary and builds the runner's parameters from
  its args and settings. A missing, unknown or misspelled field raises, naming the test's id;
- View: `score` builds each output's view once per page: `views.Html` (the HTML, its text view, and
  its seen view, the text without image alt text) for an HTML output, and the block list for
  `blocks`. Alt text holds an image's printed words or a description of it, so tests that credit
  text read the text view and tests that fault extra text (`repeat`, `page_near_empty`) read the
  seen view: printed words count wherever an output writes them, and a description never costs;
- Mark: `runner(params, view)` returns `(passed, why)`. A runner is a pure function of its
  parameters and one output's value: it never reads a file, and never sees another output; and
- File: the page's verdicts are counted per family on its line of `scores.jsonl`, for `summarize`, and
  written whole, with each test's type, tags and derivation, to the page's details.

Constants sit at the top of the runner module (`TABLE_MIN_RATIO`, `MIN_PLACE_COVER`), and are part of
the test type, not of any test.

A verdict's result is one of two:

- `pass`: the test passed; or
- `fail`: it failed, its output is missing, or its output is malformed: HTML that isn't a string, or
  a block that isn't `{label, bbox[, text]}` with a label of `views.LABELS` and a box of four numbers
  from 0 to 1. The view raises `views.MalformedOutput` for these, since they are the provider's fault.

A system that can't produce an output is graded on every test: that output's tests fail as "no <output>
output", and the page isn't counted as failed. The families map onto outputs (html: text and tables;
blocks: layout), so an html-only system shows a layout family of 0, and its text and tables families say
how it reads. Grading that raises anything else on a
well-formed output is a scorer bug: it is raised, naming the page and the test, and no scores or summary
are written, so a bug never passes as a score. A prediction that isn't an object of outputs is the
system's failure: `UnitTests.prediction` raises `SystemFailed`, and the page fails, every test failed, with the traceback on
its line of `scores.jsonl`; anything else `prediction` raises stops grading as a bug.

## Benchmark

A benchmark is an omni-bench-core `Benchmark` (`benchmark.default()`): the `Parse` task, the dataset and
`UnitTests`. omni-bench-core plans, predicts, resumes and grades, and writes a run's files: settings.json,
records/, predictions/, and the scorer's folder with scores.jsonl, summary.json and details/.

A run is one system, and its folder answers one exact question, named for it: the system and its options, the dataset,
the manifest, the task and the pages chosen. What happens in each case (a failed page, a missing key, a model server that isn't running, an
unfinished run) is the core's three rules: see [omni-bench-core's "The rules"](https://github.com/datalab-to/omni-bench-core/blob/main/OVERVIEW.md#the-rules).
Comparing systems is one run per system with the same choice of pages, so each is graded on the same pages.

## Package

```
omni_parse_bench/
  __init__.py     data, scorers, and the scorer's UnitTests, score, lines, summarize and Verdict
  data.py         the dataset: downloading it, reading its manifest into pages, choosing pages to run
  scorers/
    unit_tests/   the scorer: UnitTests, and gold, check, score, lines, summarize
      tests.py    what a unit test is: a gold file read into typed, checked tests
      runners.py  one parameter tuple and one runner per test type, and the TYPES registry
      compare.py  one page: every test run against its outputs (score, Verdict)
      unit_tests.py  a dataset: gold, check, lines, summarize, and UnitTests
  vocab.py        the closed vocabularies: output types, derivations, families, what each test type reads, tags
  views.py        what a runner reads: views.Html (the HTML, its text and seen views), views.Block
  normalize.py    fold and squeeze, the comparison normal form both sides go through
  tables.py       HTML tables as grids of cells, with neighbors and headings (from olmOCR's parser)
  equations.py    equations compared by what KaTeX renders them to
  katex/          KaTeX (MIT), run in an embedded V8 (mini-racer)
  markdown.py     markdown → HTML, the one converter the harness runs on every provider's markdown
  harness/        producing predictions:
    adapter.py    Parser: an omni-bench-core adapter for a document, written for one page (SUPPORTS, keys,
                  requests, send, parse), and the help of options many adapters share
    contract.py   Request, Call and Cost: one call and its answer
    errors.py     how a call fails, whether a retry can fix it, and the note for a model server not running
    budget.py     one page's share of the clock
    layout.py     a vendor's layout blocks as the `blocks` output
    raster.py     a PDF page as an image
    registry.py   which adapter a provider name means, made from options
    providers/    one module per vendor (docs/providers.md)
  task.py         the Parse task, and Input: a page in, its html and layout blocks out
  benchmark.py    the benchmark: the Parse task on a dataset, graded by UnitTests
  cli.py          opb init | run | grade | score | predict | check | tests | systems
tests/            including test_dataset.py, the dataset's invariants
docs/
```

Extras: the base install scores, and grades and checks a dataset folder (it includes omni-bench-core,
with pyarrow, which `data.read_manifest` needs); `[harness]` adds the adapters' packages (httpx, openai,
markdown-it-py, pypdfium2, pillow); `[benchmark]` adds both the harness and the Hugging Face client
(omni-bench-core's `[hub]` extra), which downloading the published dataset needs.
