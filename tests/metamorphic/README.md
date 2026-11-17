# What the scorer promises

This folder checks the OPB scorer ([datalab-to/omni_parse_bench](https://github.com/datalab-to/omni_parse_bench))
against a list of promises, and publishes the result in [CERTIFICATE.md](CERTIFICATE.md).

Each promise is a *relation*: change a page, or a test, in a way that should not matter (or should matter in one
known way), and the verdict should follow. Example: putting a passing answer in bold must not make its test
fail.

- The certificate lists the 68 relations its authors selected: 58 hold and 10 deviate. It is not every
  relation of the scorer (see [Not covered](#not-covered)). Four of the 10 (M1a to M1c and M1e) are about
  folding a string twice, which the scorer never does and no document promises, so they change no score.
- It is generated from the tests. CI fails if it is out of date, or if a status disagrees with its test.
- This page is enough to read it. Links to `docs/scoring` add detail only.

**How the edges were found.** A fuzz sweep compared the scorer with a reference, written from `docs/scoring`
and not published, for every rule in it. It covered fold, the text view, present (text and number), the equation test, order, repeat,
table_cell, layout_kind, markdown against HTML, and adding blocks, reordering blocks and batching tests. Most
edges it found are rows here: fixed ones as HOLDS, open ones as DEVIATES ('Not covered' lists the rest).
Apart from the changes named below, the fixes changed no verdict on the cached leaderboard re-runs (an
observation on those outputs, measured by the authors and not re-runnable here, not a guarantee for every output). Its limit: it tried sampled inputs only, so a property with no disagreement
means none among its samples.

Two deliberate changes can turn a pass into a fail. Number tests match separators as the gold writes them (M12c),
and a heading walk stays in the cell's own columns (`top_heading`) or rows (`left_heading`, `right_heading`), no longer through a cell that spans others. On the
cached leaderboard re-runs, a few number passes and a few `top_heading` passes became fails; each was judged a
real error on review. A few fail-to-pass changes came from the other fixes (a leader run or a footnote mark had
hidden text the page did write).

## Run it

From the repository root:

    uv sync --extra dev
    PYTHONPATH=. uv run pytest tests/metamorphic -q

A healthy run gives:

| | passed | skipped | xfailed |
|---|---|---|---|
| this folder, no dataset | 82 | 11 | 12 |
| this folder, with dataset | 92 | 1 | 12 |
| whole suite, no dataset | 1186 | 21 | 12 |
| whole suite, with dataset | 1201 | 6 | 12 |

All four rows come from runs of this version.

CI does not set the dataset, so it skips every check over real tests. To include them, download the dataset
and point `OPB_DATASET` at it:

    uv run python -c "from huggingface_hub import snapshot_download as get; print(get('datalab-to/omni_parse_bench', repo_type='dataset', revision='d70182b9f901d1660a27e60bf6be6d6e6ea83013'))"
    export OPB_DATASET=<the folder it prints>

Python 3.12 or later (CI runs 3.12, 3.13 and 3.14).

## Read a certificate row

Each row has: the relation's label, its promise, its status, the evidence, and the tests.

**Status**

- **HOLDS**: the test passes. No counterexample in the sampled examples, and none in the checks over every real
  test when the dataset is set. It is not a proof.
  - Each test tries at most 300 examples in CI, and 5,000 in the deep profile, which CI does not run.
  - It tries fewer when its input space runs out. The evidence then gives the count run in CI.
- **DEVIATES**: the scorer does not keep the relation. Its test is a strict xfail that fails on its first example.
  - A strict xfail accepts any failed assertion, so a second cause could hide under an old label.
  - M23a has a passing check that pins its cause: it breaks if the cause changes.

**Evidence** is some of: the examples tried ("at most" a number, or the exact count when the input space runs
out), the loaded tests drawn from, fixed cases, and the checks over every real test (with how many each relation
lists as deviating).

**A DEVIATES row** also gives:

- a counterexample;
- why it has its label;
- the effect on scores: *none seen*, *small* (a small share of the tests it can touch change verdict; the basis says what was measured) or *unknown*;
- how common it is;
- who is affected.

**Labels.** Each deviation has an entry in [known_deviations.json](known_deviations.json) with one of three labels:

- *intended and documented*: a scorer docstring, doc page or code comment says the scorer does this.
- *bug*: the scorer contradicts its own docs in a way that can change a verdict.
- *known limitation*: the docs do not promise it either way. It may still cost a correct answer.

The label says what the docs say, not whether the behaviour is good. Each entry's `why_this_status` cites the
lines it rests on.

**`enumerated_over_real_tests`** is true when a test checks every real test for that relation, and the deviating
ids are then listed. False does not mean unmeasured: `effect_basis` says what was measured.

## What you can re-run

- From this package: every status, every real-test count and deviating id (with the dataset set), every pool size,
  every example count.
- Not from this package: the *effect on scores* and *how common* figures marked "Measured on
  cached leaderboard re-runs". Those runs are not included.
- A deviation whose effect is *unknown* (or *not measured*) is one that could change a score. Treat it as open.

The real-test counts and deviating ids are constants recorded in the source (`common.py`,
`known_deviations.json` and the test files). They are checked only when the dataset is set. Then `--run`, and
the check of the counts, also check by its sha256 that the dataset's `manifest.parquet` is revision d70182b's.
That pins the list of pages, not the gold files.

## Audit procedure

    PYTHONPATH=. uv run python tests/metamorphic/render_certificate.py --run    # with and without OPB_DATASET

This runs the package under pytest and prints:

1. the scorer's `git describe` and commit;
2. the Python, pytest and Hypothesis versions;
3. the dataset folder (or none), and whether its manifest is revision d70182b's;
4. one row per relation.

It exits non-zero on any mismatch, and when `OPB_DATASET` holds another revision than d70182b. It includes the checks that CERTIFICATE.md is the fresh render and that every
status matches its test's xfail marker.

- A row reads `passed` when the checks that ran passed. It says how many other checks were skipped.
- Without the dataset, every check over real tests is skipped, so `passed` covers the sampled examples only.

When you certify a release, save the `--run` output next to the certificate. Its first rows look like this:

    relation             certificate status                 result in this run
    M1a                  DEVIATES (known limitation)        expected failure (1 other check skipped)
    M1b                  DEVIATES (known limitation)        expected failure (1 other check skipped)
    M1c                  DEVIATES (known limitation)        expected failure (1 other check skipped)
    M2a                  HOLDS                              passed

Other commands:

- `HYPOTHESIS_PROFILE=deep` before the pytest command runs the deep profile.
- `PYTHONPATH=. uv run python tests/metamorphic/render_certificate.py --write` regenerates the certificate.

## When a certified relation fails

- **A HOLDS test fails.** The scorer broke a promise. Fix the scorer. If the change is deliberate:
  1. mark the test `@deviation(label)`;
  2. give `@relation` the new status;
  3. add the entry to `known_deviations.json`;
  4. regenerate the certificate.
- **A DEVIATES test passes.** The scorer now keeps the relation. Remove the marker and the entry, set HOLDS,
  and regenerate.
- **A check over every real test reports new ids, or ids that no longer deviate.** Fix the scorer, or update that
  entry's `real_ids` and regenerate.

## Not covered

- score aggregation: family scores and the headline;
- equation tests on real golds: M17 uses 8 handmade equations, and M10 compares readings, not real equations;
- table_cell relations `section`, `row_groups` and `left_heading` beyond M27's mirror check (`down` only inside M6a's agreement check);
- number tests' sign and percent rules (M12 and M20 cover digits, separators and tails only);
- repeat's reading without image descriptions, and the equation test's plain-text fallback;
- markdown beyond pipe tables and paragraphs;
- missing or malformed outputs;
- a batch where some test fails: M19 draws only pages where every test passes;
- layout_kind's list-or-form-as-text rule;
- these steps of fold: no relation fails when one is removed or changed (each was tried on a copy of the
  scorer):
  - compatibility forms (NFKC: ligatures, full width, sub- and superscripts);
  - a superscript digit after a digit set apart (`1,240¹`);
  - invisible and private-use characters removed;
  - the quote and arrow families;
  - full-width punctuation made ASCII;
  - a decimal middle dot made a point;
  - the minimum run of 3 for dots, dashes, `=` and `*` (the one for `_` is pinned by M22a's check);
- these rules of the tests, tried the same way:
  - present's retry without spaces (squeeze);
  - table_cell's floor ratio (`TABLE_MIN_RATIO`, 0.5);
  - a number test's sign, and layout_kind's list-or-form-as-text rule (both named above);
- M14 restates fold's rules in its own code, to skip deletions that cannot count; it does not call the
  scorer's rules, so it does not check them;
- edges the sweep found that no row states:
  - a dollar's padding evidence read across a paragraph break;
  - punctuation between a math span and a price read as math (`$2x$, ($5)`), which the documented rules give;
  - a later colspan running into an earlier rowspan, which no doc covers;
  - a bare `<` or `>` that a browser would read another way, which no doc covers;
- anything not named in a certificate row.

## Glossary

Reference only; the sections above do not need it until a term is unfamiliar.

### The benchmark

- **scorer**: the code that grades a system's outputs (`omni_parse_bench/scorers/unit_tests`).
- **page**: one document page sent to a system.
- **output**: what a system returns for a page: `html`, and `blocks` for layout. Markdown is converted to HTML.
- **gold**: what a test expects, written by the dataset's authors.
- **test**: one check of one page's output: a test kind and its gold.
- **verdict**: pass, or fail with a *why* (the short failure reason the verdict carries).
- **test kinds**:
  - *present, text arg* (the *text test*): this string is on the page.
  - *present, number arg*: this number is on the page, digit for digit.
  - *present, latex arg* (the *equation test*): this equation is in the page's math, compared as rendered symbols.
  - *order*: this string comes before that one.
  - *repeat*: this line appears exactly N times.
  - *table_cell*: a table has this cell, with these neighbours and headings.
  - *layout_kind*: the block that holds this place has this label.
- **score**: a family's score is the share of its tests that pass.
- **headline**: the plain mean of the family scores.
- **families**:
  - present (all args), order and repeat score into *text*.
  - table_cell scores into *tables*.
  - layout_kind scores into *layout*.
  - Detail: [docs/scoring/README.md](../../docs/scoring/README.md).

### The data

- **real tests**: the 16,288 tests on 2,937 pages of the published dataset, Hugging Face
  `datalab-to/omni_parse_bench` at revision d70182b.
- **fixtures**: the 17 tests in `tests/fixtures/invariants/`, used when no dataset is set (as in CI).
  They are 3 text, 2 number, 3 equation, 1 order, 1 repeat, 4 table_cell and 3 layout_kind.
- **loaded tests**: the fixtures, or the real tests when the dataset is set.
- **answer page**: the page holding exactly a test's own answer (`answer` in `tests/test_invariants.py`).
- **test id**: the dataset's own name for a test.
  - It often starts with its source document's name, and its form varies between the dataset's suites.
  - The scorer never reads it.
  - `<test id>#<n>` here is the n-th text string of that test, counting from 0, in the order `text_strings` in
    [common.py](common.py) lists them.
- **cached runs**: system outputs saved from leaderboard re-runs. They are not in this
  package, so figures measured on them cannot be re-run here.
- **helpers from sibling files**:
  - `answer` in `tests/test_invariants.py` writes the page that holds exactly what a test asks for.
  - `tests/test_properties.py` loads the tests (`TESTS`, and `LIVE` when the dataset is set) and gives the word
    and mark strategies (`WORD`, `MARK`).
  - This package imports both.

### Matching text

- **fold**: the plain form in which gold and page text are compared. Steps, in this order:
  1. math spans (`$..$`, `\(..\)`, `<math>`) are read as text;
  2. a word broken by a hyphen at a line end (`develop- ers`) is joined, when a lowercase letter follows or the
     letters on both sides are all capitals (`DEVELOP- ERS`), even across a paragraph break (M22b); a capital
     after a word in lower or mixed case keeps the hyphen (`Anglo- Saxon`);
  3. compatibility forms are unified (ligatures, full width);
  4. invisible and private-use characters are removed;
  5. checkboxes are made ☒ or ☐;
  6. footnote brackets `[1]` are removed, leaving a spaced number; present retries with the page's markers
     dropped, except a marker between two digits (M7d), and with its `<sup>` footnote marks dropped too (one to
     three digits or footnote symbols, not right after a digit) (M7e);
  7. bullets starting a line are removed;
  8. runs of 3 or more dots (ideographic full stops `。` too, M2g), dashes of any kind (M2f), `_`, `=` or `*`
     (*leaders*) are made a space; white space may sit inside a run, but not a paragraph break (M22a);
  9. dash, quote, space and arrow families are each made one character, then two single quotes in a row (TeX's
     ` `` ` and `''`, or a mixed pair `'’`) are read as a double quote;
  10. text is lowercased and white space collapsed (not removed).
- **squeeze**: fold with every space removed. Present and order retry with it when fold fails; table_cell
  also compares cells with their spaces removed.
- **text matching**: a text test looks for its folded string in the folded page.
  - It allows up to `max_diffs` edits, by a fuzzy match.
  - Present adds a float slack EPS (1e-9), so k substitutions in n characters pass at the ratio 1 - k/n they
    produce.
  - Order uses edit distance.
  - table_cell has the same slack.
- **max_diffs** (the *edit budget*): the edits a test allows, after fold. Each matcher counts them its own way:
  - order: a character substituted, inserted or deleted is one edit (M3). A larger budget never fails a page
    that passed (M25a, M25b);
  - present: a substituted character is one edit (M3). An inserted one can cost less, and so can one deleted
    at the end of the text or from a page that holds only the text: 3 inserted letters can pass with
    `max_diffs` 2 (M23a). Two swapped letters, or a letter moved a few places, count as one edit. A text that
    starts or ends the page text gets about 1.5 times its budget for substituted letters (M23a);
  - table_cell: a substituted character is one edit (M3); an inserted or deleted one costs about half (M23b).
- **line-end hyphen**: a letter, a hyphen, then white space (`develop- ers`). Fold joins it when a lowercase
  letter follows, or when the letters before the hyphen and after the white space are all capitals (a heading
  in capitals, `DEVELOP- ERS`), so a word folds the same in upper case as in lower case (M2e). Where their own
  comparison fails, present, order, repeat and table_cell also read such a hyphen, on the page or in the gold,
  kept or dropped, exactly (a hyphenated compound broken after its hyphen: M11a, M11b).
- **text view**: a page's HTML as plain text.
  - Tags are dropped, namespaced ones (`<o:p>`) too; a `>` inside a quoted attribute does not end a tag (M24c,
    M24d).
  - A `<` before a letter that starts no tag stays as text (M24a).
  - Comments are removed with nothing in their place (M24b).
  - Block tags (paragraphs, cells, list items) end a line, written as U+2029 (the Unicode paragraph separator).
  - An opening `<sup>` tag becomes a space. The closing tag becomes a space before a number (a digit, or a sign or
    point and a digit), and is dropped elsewhere, so a mark joins no number on either side (M7b, M7c).
  - An image reads as its alt text.
  - Entities are unescaped.

### Math

- **stray dollar** (or price dollar): a `$` that opens no math, as in `$5.00`.
  - A dollar pairs with the next one unless the text between is not math (two prices, prose).
  - A dollar left over is a stray.
  - A dollar never pairs across a `\(..\)` span, nor with a dollar inside one. A `\(..\)` that holds a dollar
    of its own is no such span: its `\(` is a stray.
- **equation test matching**: the equation test takes its spans from `equations.spans` and renders them with KaTeX.
  In M10, *found* means a span with the same body (white space and `\(` `\)` `\[` `\]` aside) or the same
  rendered symbols.

### Tables

- **table_cell relations**:
  - `up`, `down`, `left`, `right`: neighbour cells.
  - `top_heading`, `left_heading`: the heading cells of its column and row.
  - `headings`: all headings over its column.
  - `section`: the nearest section row above it.
  - `row_groups`: cells to its left that span its rows.

### Layout

- **block**: a box `[x0, y0, x1, y1]` in fractions of the page, with a label, in a system's `blocks`.
- **block labels**: text, heading, page_furniture, list, caption, footnote, equation, code, table, form, figure.
  The dataset's layout tests use text, table and heading. A list or form block passes a text test.
- **place**: the boxes of the printed line a layout_kind test is about.
  - A block covers a place when it overlaps at least half of it.
  - The smallest covering block *holds* it.

### Test machinery

- **CI and deep profiles** (Hypothesis settings in `tests/conftest.py`):
  - CI tries at most 300 examples per test, the same ones every run.
  - `HYPOTHESIS_PROFILE=deep` tries 5,000 new ones. CI never runs it.
- **strict xfail**: a test marked as expected to fail. If it passes, pytest reports a failure.
  Each of the 9 deviations gives one expected failure.
