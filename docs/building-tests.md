# How tests are built

What a test is made of, who decides each part and from what evidence, and how to add tests.
[`design.md`](./design.md) is the full specification of each test type, and
[`tagging.md`](./tagging.md) describes how tags are assigned.

1. [The mental model](#the-mental-model): what a test checks, and what its tags say;
2. [Terms](#terms): the words used for a test's parts;
3. [One test, read part by part](#one-test-read-part-by-part): a table test, field by field;
4. [Test types and their roles](#test-types-and-their-roles): each test type's roles and settings, and the kinds it accepts;
5. [How each part is decided](#how-each-part-is-decided): who decides a test's type, kinds, content, settings and tags, and from what;
6. [The suites](#the-suites): each suite's test types and derivations; and
7. [Adding tests](#adding-tests): the steps, starting from the vocabulary.

## The mental model

A parser reads a page and returns HTML and, where it can, layout blocks (each a labeled box). Each
page has a gold file of tests. Each test checks one fact about one of those outputs and passes or
fails.

A test has two halves:

- what it checks, and how: its test type, its args and its settings. This half decides the verdict;
  and
- what the content is: its tags. This half only decides which tests a query selects. Grading never
  reads tags.

The first half is written when the test is built, by whoever builds it. The second half is decided
afterwards, from the page and its sources but never from the test, and then checked against the
first.

## Terms

- page: one PDF page or one image. Its id is `<suite>-<name>-p<n>`;
- suite: the collection a page belongs to (`tables_derived`, `olmo_arxiv_math`, ...). It records
  provenance only and is never evidence for a tag;
- gold file: `gold/<page_id>.json`, which holds a page's tests under `tests`;
- test: one fact checked about one page's output. It has seven keys: `id`, `test_type`,
  `output_type`, `derivation`, `tags`, `args` and `settings`;
- test type: the check. One runner function in `runners.py` per test type. A new test type is added
  only when the check differs, never because the content differs;
- arg: one piece of gold content the test compares with the output, such as a sentence, a number,
  an equation or a table cell's text;
- arg role: the part an arg plays in its test's check: `content`, `before`, `after`, `cell`,
  `top_heading`, and so on. The test type fixes which roles exist (`gold.ROLES`);
- arg kind: how an arg is compared. An arg holds exactly one of three keys, `text`, `number` or
  `latex`, and the key is the kind. A `text` arg may also hold `place`, a box per line on the page;
- settings: values that configure the check as a whole (`expected_count`, or `kind` for a
  block kind). Never content;
- output type: which output the test reads: `html`, or `blocks` for `layout_kind`;
- derivation: how the test's answer was established (the publisher's XML, the PDF's text layer, a
  model panel, ...). A closed list in `vocab.DERIVATIONS`; and
- tag: a word from a closed vocabulary that says what an arg's content is (`table`, `math`, `spa`,
  `Thai`, `handwriting`, ...). A test's tags are the union of its args' tags.

## One test, read part by part

An illustrative test, in the shape of the PubMed Central table tests:

```json
{"id": "...",
 "test_type": "table_cell",
 "output_type": "html",
 "derivation": "publisher_markup",
 "tags": ["Latn", "eng", "table", "multi_column"],
 "args": {"cell":         {"text": "167.8", "max_diffs": 0},
          "headings":     [{"text": "Dry weight (g)", "max_diffs": 0}],
          "section":      {"text": "A. Overall cohort", "max_diffs": 0},
          "row_groups":   [{"text": "HPV-58", "max_diffs": 0}]},
 "settings": {}}
```

It reads as: "some table in the output has a cell `167.8`, under the column heading `Dry weight
(g)`, below the section row `A. Overall cohort`, with `HPV-58` as a row group to its left".

- `test_type: table_cell` says which check runs;
- the four roles say what part each piece of text plays in that check;
- each arg holds `text`, so each is compared as text, here with no edits allowed;
- `derivation: publisher_markup` says the answer came from the article's JATS XML; and
- `tags` were decided later: `Latn` and `eng` from the heading args (the cell is a number, so it has
  no script or language), `table` from the JATS, and `multi_column` from a model panel.

## Test types and their roles

| test_type | roles | settings | passes when |
|---|---|---|---|
| present | `content` | | the arg is in the html |
| order | `before`, `after` | | `before` is found before `after` in the html |
| repeat | `content` | `expected_count` | the arg appears exactly that many times in the html, as whole words |
| table_cell | `cell`; optional `up`, `down`, `left`, `right`, `top_heading`, `left_heading`, `section`; optional lists `headings`, `row_groups` | | some table in the html has the cell, with these neighbors and headings |
| layout_kind | `content`, with its `place` | `kind` | the smallest block covering at least half of the place is labeled `kind` (one of `views.LABELS`); for `text`, a `list` or `form` block (a list item, or a form field or key-value pair) passes too |

The table_cell roles mean:

- `cell`: the cell being checked. Always present;
- `up`, `down`, `left`, `right`: the cell next to it in that direction;
- `top_heading`: the heading over its column;
- `left_heading`: the label at the start of its row;
- `headings`: every heading over its column, from the top down;
- `section`: the nearest row above it that holds one label, such as "A. Overall cohort"; and
- `row_groups`: the cells to its left that span its row and others, from left to right.

The neighbor roles (`up`, `left`, `top_heading`, ...) come from olmOCR-bench's and fr-bench-pdf2md's
table tests. `headings`, `section` and `row_groups` come from the PubMed Central tests (and our
hand-written form grids); they record the structure JATS stores and flattened tables lose.

Which kinds each type accepts (`gold.py`):

- `present`: `text`, `number` or `latex`;
- `order`, `repeat` and `table_cell`: `text`; and
- `layout_kind`: `text` with a `place`. Its text is shown to a reader and never compared.

A layout block's `form` label is a form field or a key-value pair (a label with its value), or a
region of them: Reducto's `Key Value`, Extend's `key_value` and LlamaParse's `key-value-region` are
one pair each, and Datalab's `Form` a whole form. A `text` test passes on a `list` or `form` block,
since a list item or a key-value pair is running text, and vendors differ in whether such a line
gets a block of its own. The label is not the `form` tag, which marks content that sits on a form.

## How each part is decided

### Test type and roles: by the builder, from the check it wants

The builder first picks a fact worth checking, then the test type whose check tests it, and the
type fixes the roles. A builder never picks a type for its content: "this equation is present" and
"this form value is present" are both `present`. What the content is goes in its tags.

The builder fills each role from a source that records what part the text plays:

- `cell`, `headings`, `section`, `row_groups` on PubMed Central pages: the article's JATS XML, which
  marks each cell, each heading cell and the table's structure. The cells tested are those whose
  context is hard to keep: under a merged heading, in a section or in a row group;
- `before`, `after`: two passages whose order on the page is known, from the text layer, extractors
  that agree, a page we authored, olmOCR-bench, or a model panel that agreed on the reading; and
- `content`: the passage, number or equation that must appear, from any of the sources below.

A role is a claim the test makes, for example "this text is a column heading over that cell". It is
checked by tagging (below) and by review.

### Arg kind: by the builder, from where the answer came

- `latex` when the answer is LaTeX source, as for arXiv equations. Compared by what KaTeX renders,
  so `\frac{a}{b}` and `\dfrac{a}{b}` are equal;
- `number` when the content must match digit for digit. Strict on digits, decimal point and sign, and
  an output may not drop a percent sign; lenient on thousands separators: `-4.8%` never matches
  `-4.9%`, and `1,240` matches `1240`; and
- `text` for everything else. Matched after `normalize.fold`, within the arg's `max_diffs` edits.

The kind is never guessed from the characters: "2024" or "x = 1" could be any of the three, and a
guess would make a heuristic part of grading. Every `table_cell` arg is `text`, even a number.

### Arg content and derivation: from the source

The arg's characters come from a source, and `derivation` records which (`vocab.DERIVATIONS`):

| derivation | where the answer came from |
|---|---|
| `publisher_markup` | the publisher's JATS XML |
| `text_layer` | the PDF's own text layer |
| `authored` | we made the page or filled the form, so we know what is on it |
| `upstream_olmocr` | olmOCR-bench's own tests |
| `upstream_frbench` | fr-bench-pdf2md's own tests |
| `source_transcription` | the archive's own transcription of a manuscript (Library of Congress volunteers, HTR-United datasets) |
| `model_panel` | independent models agreed on what the page says |
| `extractor_agreement` | independent text extractors agreed on the line |
| `human_review` | a correction or confirmation by a person, recorded per test |
| `model_review` | a correction by a vision model, used only where a person had not decided and only on test types where it matched a person's decisions |

No model we used to establish or tag an answer is one whose results are reported. A person
correcting a test could see reported systems' readings beside the page, and checked any reading they
took against the page.

### Settings: by the builder

Settings are what the builder knows from the source about the check as a whole: how many times a
phrase appears (`expected_count`), or the block kind a line sits in (`kind`: two models shown the line
boxed on the page, a third on their splits, a person for the rest).

### Tags: after the test is built, from the page, never the test

Tags are decided per arg, for 11 properties: script, language, table, math, form, role (heading,
caption, footnote, list, code, figure, header_footer or none), multi_column, tiny, rotated,
handwriting and degraded. Each is decided from the strongest evidence there is: computed where the
answer is a fact (the Unicode script of the letters, a rotation we applied), from a source where one
says (JATS marks tables), and otherwise by a panel of models shown the arg boxed on the page, with a
person deciding what they can't. The evidence is the page and its sources, never the test: its roles,
kinds and type are never shown. Where the tag and the test share a source (JATS tables), the check
below is not independent.

The tags are then checked against what the test claims: every arg of a `table_cell` test must be in a
table, and a `latex` arg must not be tagged non-math. A disagreement goes to a person, who decides
whether the tag or the test is wrong, so a role that puts text in a table where there is none is
caught.
[`tagging.md`](./tagging.md) has the method.

## The suites

Which test types and derivations each suite holds. Every suite also has `layout_kind` tests, whose
derivation is `model_panel`.

| suite | test types | main derivation |
|---|---|---|
| tables_derived | table_cell, present | publisher_markup |
| olmo_table_tests | table_cell | upstream_olmocr |
| olmo_arxiv_math, olmo_old_scans_math | present (all `latex`) | upstream_olmocr |
| olmo_old_scans | present, order | upstream_olmocr |
| olmo_multi_column | order | upstream_olmocr |
| olmo_long_tiny_text | present | upstream_olmocr |
| synth_copies | present, order, repeat | authored |
| forms_filled | present | authored |
| multilingual | present | text_layer, authored |
| forms_federal | present, table_cell | authored |
| forms_documentcloud, multiling_finepdfs, tiny_plans | present; order on the last two | extractor_agreement |
| realdoc_pages, realdoc_pdfs, docparsing_images | present, order; repeat on realdoc_pdfs | model_panel |
| parsebench_docs | present, order, repeat | text_layer, model_panel |
| handwriting_samples | present | source_transcription |
| frbench_handwriting | present, table_cell | upstream_frbench |
| rotation_skew | present | those of the pages it copies |
| large_format | present | text_layer |

## Adding tests

1. Check the vocabulary first. Does an existing test type check the fact? Does an existing kind
   compare the content correctly? Does an existing tag describe it? If not, extending the vocabulary
   is a design change, recorded in `design.md`, and comes before any data:
   - a new test type only when the check differs, with a runner in `runners.py`;
   - a new arg kind only when the content needs a comparison none of the three gives (for example
     code, compared exactly with its whitespace, or a date, equal across written forms), with a
     comparison function, a validation rule and a line in `design.md`; and
   - a new tag with a definition (what it is, what counts, what doesn't) in `vocab.py`.
2. Pick a source of answers for the pages, and set `derivation` from it. Prefer sources that know
   the structure (publisher XML, form fields, pages you authored) over readings of the image.
3. For each fact, pick the test type, fill its roles from the source, pick each arg's kind, and set
   the settings.
4. Load the dataset with `gold.load` (or `opb tests --dataset <folder>`). It rejects args with the
   wrong keys, roles a type doesn't allow, kinds a role can't compare, values outside the vocabulary
   (a tag must be a vocabulary tag, a language code or a script code), and a `max_diffs` that would
   let any output pass. Fix or drop what it rejects.
5. Tag the new tests from the page and its sources, as [`tagging.md`](./tagging.md) describes, never
   from what the test claims.
