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
Counts are of the published dataset: 2,937 pages, 16,304 tests.

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
- a number (`{"number"}`): found digit for digit, lenient only on thousands separators; and
- an equation (`{"latex"}`): found by what KaTeX renders it to, or, for an equation plain text
  writes without loss, by its text reading. Its LaTeX must render to at least one symbol, else the
  test doesn't load: LaTeX that doesn't render would fail on every output, and LaTeX that renders
  to nothing (`\quad`) would pass on every output.

A `layout_kind` test's text only labels its place; it is never compared.

| test type | reads | checks | args and settings | family | tests |
|---|---|---|---|---|---:|
| `present` | `html` | this content appears | `content` | text | 7,291 |
| `order` | `html` | A comes before B | `before`, `after` (text) | text | 1,189 |
| `repeat` | `html` | this line appears exactly N times | `content` (text); `expected_count` | text | 35 |
| `table_cell` | `html` | this cell exists with these neighbors, under these headings, in this section and in these row groups; the cell may be one line of a multi-line cell | `cell`, `up`, `down`, `left`, `right`, `top_heading`, `left_heading`, `headings`, `section`, `row_groups` (text) | tables | 5,386 |
| `layout_kind` | `blocks` | the smallest block covering half of this line's place has this kind | `content` (text with a `place`); `kind` | layout | 2,403 |

Of the `present` tests, 3,700 compare text, 3,268 an equation and 323 a number.

A `table_cell` test reads structure from the markup, not from how the page looks. A heading or
row-group label covers the cells it is encoded over: merged (`colspan`, `rowspan`), repeated in each,
or written once beside (a heading) or above (a row-group label) empty cells, as a printed table shows
a merged label.

A `layout_kind` test's kind is one of `views.LABELS`; the dataset tests `text` (1,427), `table`
(598) and `heading` (378). Each adapter maps its vendor's block types onto the labels
([providers.md](./providers.md)); `form` is a form field or a key-value pair, or a region of them,
which Reducto, Extend and LlamaParse give as key-value types ([providers.md](./providers.md#block-labels)).
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

A test has every tag of every piece of content it compares (each a *span*). Tags overlap, so they
select tests and are scored one by one (`per_tag`), never averaged into a score.
[`tagging.md`](./tagging.md) says how they were made.

### Derivations

| derivation | how the answer was established | tests |
|---|---|---:|
| `publisher_markup` | the publisher's JATS XML: table cells with their headings, sections and row groups | 4,919 |
| `upstream_olmocr` | olmOCR-bench's own tests | 4,386 |
| `model_panel` | independent models agree on what the page says; no model in the results table sits on a panel | 3,613 |
| `authored` | we made the page or filled the form, so we know what's on it | 1,402 |
| `extractor_agreement` | independent text extractors (two, or three on `tiny_plans`) agree on the line | 823 |
| `text_layer` | read off the PDF's own text layer: its words, their boxes, their font flags | 521 |
| `source_transcription` | the source's own transcription of a handwritten page (the handwriting_samples suite) | 284 |
| `human_review` | a recorded correction of a test | 180 |
| `model_review` | a vision model read the page, blind to which reading was the test's, and corrected the test, for a test type an audit cleared | 102 |
| `upstream_frbench` | written by fr-bench-pdf2md for its hand-filled forms | 74 |

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
| `suite` | `realdoc_pdfs` | where the page came from; its license is in `licenses/`. `--suites` filters on it |
| `doc_path` | `pages/<page_id>.pdf` | the input, relative to the dataset root: a `.pdf` or a `.png` |
| `gt_path` | `gold/<page_id>.json` | the tests, relative to the dataset root |

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

`gold.py` checks every field against the vocabulary when a test is loaded, and rejects anything
else. A page's output types are the ones its tests read, and aren't stored anywhere else. A test's
suite and document are its page's.

## Predict

```python
predict(provider, page, wants=None, timeout=…, **options) -> record   # page: a .pdf or .png
```

The benchmark asks a provider only for what a page's tests read: it collects the `output_type` of
every test on the page (`gold.wants`) and calls `predict` with those as `wants`. The record holds
the outputs, an error per output that failed or is unsupported, each call (what was sent, its cost
and time) and the vendor's raw answers; [API.md](./API.md) shows one.

## Score

```python
score(outputs, tests, unsupported=()) -> [Verdict(id, result, why)]
summarize(verdicts, tests, pages=None) -> summary
```

A test's text and a provider's text view are compared after `fold` (normalize.py), the same function
on both sides, whose docstring lists every rule. Among them: a LaTeX span reads as the text it
renders, without the spaces math mode doesn't render ("$$2 . 5 5$$" is 2.55, "$U$" is U), and a word
broken by a hyphen at a line end is joined.

The headline is the mean of the families' scores: text (present, order, repeat), tables
(table_cell) and layout (layout_kind), each family's score the share of its tests passed
(`vocab.FAMILIES` maps every test type to one). Weighting by family rather than by test means a
family's weight never depends on how many tests it has: sampling more layout lines makes the layout
score more precise without making layout count more. The families are those the graded tests are
in, so a subset scores on the families it holds. A system with no scored test in some family (every
one unsupported or an error) has no headline.

Each output type also has its own score, the share of its tests passed, with `per_test_type` and
`per_tag`; the summary also gives `per_suite` and `per_derivation`. With the pages the tests belong
to, each score also counts the source documents its tests are from (`documents`). A document's tests
pass or fail together: one misread table fails all its cells, a page's image copy is the same page,
and a form's blank, filled and scanned copies are one form. The manifest's `document` column
records each page's document, set once when the page is added. So a score over few documents says less
than its test count suggests.

No score carries an uncertainty interval yet. An honest one has to account for the dependence above
the document as well as within it (copies across suites, pages built and corrected by one process from
one source), and comparing two systems is a paired question, document by document, rather than one of
overlapping intervals. The `document` column is what such an interval would be built on.

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

- Load: `gold.test` checks the test against the vocabulary and builds the runner's parameters from
  its args and settings. A missing, unknown or misspelled field raises, naming the test's id;
- View: `score` builds each output's view once per page: `views.Html` (the HTML, its text view, and
  its seen view, the text without image alt text) for an HTML output, and the block list for
  `blocks`. Alt text holds an image's printed words or a description of it, so tests that credit
  text read the text view and a test that faults extra text (`repeat`) reads the seen view: printed
  words count wherever an output writes them, and a description never costs;
- Mark: `runner(params, view)` returns `(passed, why)`. A runner is a pure function of its
  parameters and one output's value: it never reads a file, and never sees another output; and
- File: `summarize` groups the verdict by the test's output type, test type, tags and derivation,
  and its page's suite.

Constants sit at the top of the runner module (`TABLE_MIN_RATIO`, `MIN_PLACE_COVER`), and are part of
the test type, not of any test.

A verdict's result is one of four:

- `pass`: the test passed;
- `fail`: it failed, its output is missing, or its output is malformed: HTML that isn't a string, or
  a block that isn't `{label, bbox[, text]}` with a label of `views.LABELS` and a box of four numbers
  from 0 to 1. The view raises `views.MalformedOutput` for these, since they are the provider's fault;
- `unsupported`: the provider can't produce the test's output type; or
- `error`: grading raised anything else on a well-formed output, a scorer bug. The exception is its
  `why`.

`unsupported` and `error` verdicts are left out of every score, so a scorer bug never lowers one;
`summarize` counts each per output type (`unsupported`, `errors`).

## Benchmark

[What a benchmark writes](./API.md#what-a-benchmark-writes) describes a run's files: settings.json,
records/, predictions/, scores.jsonl and summary.json.

## Package

```
omni_parse_bench/
  __init__.py     gold, score, summarize, Verdict
  gold.py         the dataset: loading the manifest and gold files into typed pages and tests
  vocab.py        the closed vocabularies: output types, derivations, families, what each test type reads, tags
  runners.py      one parameter tuple and one runner per test type, and the TYPES registry
  views.py        what a runner reads: views.Html (the HTML, its text and seen views), views.Block
  normalize.py    fold and squeeze, the comparison normal form both sides go through
  tables.py       HTML tables as grids of cells, with neighbors and headings (from olmOCR's parser)
  equations.py    equations compared by what KaTeX renders them to
  katex/          KaTeX (MIT), run in an embedded V8 (mini-racer)
  markdown.py     markdown → HTML, the one converter the harness runs on every provider's markdown
  metric.py       score (one page's verdicts) and summarize (a run's scores)
  harness/        producing predictions:
    contract.py   the adapter protocol (Config, SUPPORTS, requests, call, parse) and Request/Call/Cost
    errors.py     how a call fails, and whether a retry can fix it
    budget.py     one call's share of the clock
    layout.py     a vendor's layout blocks as the `blocks` output
    raster.py     a PDF page as an image
    registry.py   which adapter, at what settings, under what run name
    page.py       predict: one page, one vendor
    providers/    one module per vendor (docs/providers.md)
  benchmark.py    Plan / Run: predict every page, resumably, then grade into scores and a summary
  progress.py     the live table while a benchmark runs
  cli.py          opb score | predict | benchmark | tests | providers | reparse
tests/            including test_dataset.py, the dataset's invariants
docs/
```

Extras: the base install is the scorer; `[harness]` adds the adapters; `[benchmark]` adds Hugging
Face, pyarrow (which `gold.load` needs) and the run orchestration.
