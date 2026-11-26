# Changelog

All notable changes to omni-parse-bench (`opb`) are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/), with one exception: 1.2.0 broke the summary's shape in a minor release.

Each heading carries the date of its git tag, in UTC. From 1.0.0 on, every release starts with **Score impact**:
whether scores from the previous release are comparable, which test types changed verdicts and in which direction,
and whether the published leaderboard was regraded. Verdict counts quoted below come from each pull request's own
regrade of saved predictions. Each PR used its own set of systems, so the counts do not add up across PRs.

## [Unreleased]

### Score impact

- Not comparable with 1.8.0: verdicts only move from fail to pass. Regraded on saved predictions of the 40 official public runs, 992 tests go from fail to pass and none from pass to fail. All 992 are `present` tests with a LaTeX argument (text family).
- Headline change per system: +0.04 to +0.25 points (median +0.05); no system loses. The top 12 ranks are unchanged; the only rank swaps are near-ties below that.
- Which changes drove it (fail to pass, all systems): `\bar`/`\overline` 341, big operators 94, transpose 86, double bars 75, triangles 75, arrows 71, double brackets 37, `\vec` 4, subsets 2.
- No `format`, number or table verdict changed on those runs; the format and decimal changes below only affect outputs that use those spellings.
- Text with a digit: a `present` text test whose gold holds a digit now fails, at any `max_diffs`, when the only match changes, adds, drops, splits or joins a number (at `max_diffs` 0 the squeezed retry no longer joins `2 1` into `21`). This rule moves verdicts only from pass to fail, so the first line above (fail to pass only) predates this change. Regraded on the saved public predictions of 27 published systems: 405 tests move from pass to fail and none from fail to pass, all `present` text; text drops 0.08 to 0.27 points and the headline 0.03 to 0.09 points per system; tables and layout do not move; no text rank changes, and the only headline change is a 0.01-point tie at ranks 15 and 16.
- Fold: `◼` (U+25FC, black medium square) is a checked box, as `■` is; it was read as unchecked. `⊠` (U+22A0) is left as written: it is also the squared-times operator, and fold cannot tell a box from maths typed as text (deferred). Regraded on saved predictions of 26 published systems (all of the 27 except unlimited-ocr-2, whose saved predictions lack 3 rows), old main d2a6216 against this change: no verdict moves and no score changes. An audit of the 10,294 public text, order, repeat and table_cell tests found neither glyph in any of their strings.
- Fold: a vulgar fraction after a digit is set apart before NFKC (`1½` reads `1 1/2`, not `11/2`). This moves verdicts both ways, in every test that folds text, number args and repeat counts included: `present` `1½` passes on `1 1/2`, `½` on `1½` and `1` on `a 1½` (fail to pass), while `11/2` on `1½` fails (pass to fail); a number arg `11` no longer matches `1½` and `1` now does; a repeat of the number `1` counts 2 on `1½`, not 0.
- LLM harness (#108): no effect on grading; it changes how a run handles two provider replies, not how answers are scored. A page that used to fail as "no usable html" or stop the run now gets a prediction or a refusal instead, so a rerun can score pages that earlier runs lost.
- `table_cell` args `{"empty": true}` and `{"end": true}` (below): no verdict moves, because no published test uses them. Regraded on saved predictions of the 27 published systems (unlimited-ocr-2 with `--partial`), old main 416c17b against this change: 439,776 verdicts, none changed, no headline changed.
- `present` setting `{"blank_after": true}` (below): no verdict moves, because no published test uses it. Regraded on saved predictions of the 27 published systems (unlimited-ocr-2 with `--partial`), old main 222f0cd against this change: 439,776 verdicts, none changed.
- `table_cell` `section`: a section label written in every cell of its row (`<td>Cohort 1</td><td>Cohort 1</td>`) now reads as the section row a merged cell (`colspan`) already did, for a test that names it: a row whose cells all fold to one string that matches the test's section (within its `max_diffs`, as a merged label does), start in the row and span no other, is read as that section in a second reading (the first still passes what it passed, so no verdict goes from pass to fail). Any other repeated row (`Yes | Yes`, `0 | 0`) stays data. Remaining tradeoff: a test that names `Yes` as its section passes on a `Yes | Yes` row, and, as a merged label does, a repeated value within the test's `max_diffs` of the section; copies that differ from each other stay data; published tests name real section labels (case cell-section-repeated-value). Regraded on the saved predictions of the 27 published systems (unlimited-ocr-2 holds 2,934 of 2,937 pages; the 3 missing hold no `table_cell` test, so each system has all 5,386), old main 24adb7e against this change, `table_cell` tests only (`section` is read nowhere else): 145,422 verdicts, none changed, no score changed.

### Added

- Provider: Docling (`docling`, docling 2.153.0), its standard PDF pipeline at its defaults, with a server image that runs on Docling's default device (the GPU when there is one, else the CPU): html from its own HTML export and layout blocks from its items (#117).

### Changed

- Indra OCR: update the CPU adapter to `indra-ocr==1.2.0` and model revision `v1.2.0`. Math is enabled by default; the full public run scores 78.8 (text 68.0, tables 75.8, layout 92.6) on 2,937 pages (#129).
- Tables: a section row may repeat its label in every cell, not only be merged or sit in the first column beside empty cells; the test must name that label (docs/scoring/table_cell.md, cases cell-section-repeated, cell-section-then-data, cell-section-data-row, cell-section-repeated-value). The M120 relation now holds.
- Equations: marks a reader cannot tell apart in print now compare equal: a transpose superscript (`^\top`, `^T`, `^\intercal`, `^{-T}`), `||` and `\|`, `\llbracket`/`\rrbracket` and doubled brackets, `\bar` and `\overline` (or `\vec` and `\overrightarrow`) over one symbol, short and long arrows, binary and big operators when the big one carries limits, `Σ`/`∑` and `Π`/`∏` with an explicit relation in the lower limit, triangle and subset variants, stretchy angle fences, Unicode mathematical letters, Unicode primes, `ϱ ϰ`, `\iint`/`\iiint`, top-level row breaks, empty scripts and a raw `%`. Each is limited as described in docs/scoring/present-latex.md; script, blackboard and fraktur letters, Greek and Latin lookalikes, check and breve, `ϖ` and `π`, `=` and `≡` stay distinct.
- Text: a `present` text gold that holds a digit keeps its numbers exact, at any `max_diffs`. Each maximal run of digits (after fold) is one token that must match the same number on the page; letters and punctuation still cost one edit each (docs/scoring/present-text.md, "Numbers are exact").
- Fold: a vulgar fraction after a digit (`1½`, `10¾`) is set apart from it, so NFKC no longer glues the whole number to the numerator (`1½` -> `1 1/2`).
- Text: a raised decimal point before a digit (`·79`, `p<·05`) reads as `.` unless a letter, digit or closing bracket comes right before it (`A·1`, `(a)·1`, `太原·2020` are unchanged).
- Format: a subscript or superscript written in maths (`$V_1$`, `$\mathrm{LC}_{50}$`, `$x^{2}$`, `${}^{a}$`) counts as the `sub` or `sup` mark on that text, and is evidence only for `sub`/`sup` and their absent forms. Maths inside code is not read. Unicode sub/superscript digits are still not marks.

### Added

- `present`: the setting `{"blank_after": true}` makes the content a form field's label and passes when nothing is written after it (white space and `_ . · …` only, one copy of an optional `printed` placeholder allowed), up to the next of the optional `stops` (the page's other labels). A label in a table cell reads the rest of its cell, then the cell to its right, or below when that is another field's label or missing. It catches invented values in fields the page leaves blank, and passes only where plain `present` does. See docs/scoring/present-text.md, "Blank fields", and relations M98 to M103 (M103: a test without the setting keeps its old verdict, with a real-test check).
- `table_cell`: the neighbor args `up`, `down`, `left` and `right` also take `{"empty": true}` (that side of the cell is blank, read without the stand-in a text arg uses, so a copied value fails; a short row's missing trailing cell is blank) and `{"end": true}` (no text in any row below, column to the right, row above or column to the left). They catch invented table content. Refused on any other role or test type. See docs/scoring/table_cell.md, "Empty cells and the end of a table", and relations M93 to M97 (M97: a test without the new args keeps its old verdict, with a real-test check).
- Providers: `pdftotext` (poppler-utils), a local CPU text-layer parser at its documented default: html only, no OCR, so image pages are empty (#109).
- Provider: pdftext (`pdftext`), the PDF text layer with no OCR, html only. No verdict changes (#110).
- Providers: `markitdown` (microsoft/markitdown 0.1.9, MIT), a local CPU text-layer parser at its defaults: html only, no OCR; scanned PDFs without a text layer are empty, and images may return EXIF metadata when `exiftool` is installed (#111).
- Providers: `pdf-inspector` (pdf-inspector 1.27.1, local; html only), as a text-mode row and, with `ocr=auto`, an OCR-mode row (PP-OCRv6 Small); image inputs use lossless PDF wrapping (#112).
- Providers: `pymupdf4llm` and `pymupdf4llm-ocr` (PyMuPDF4LLM 2.1, AGPL-3.0), local CPU rows with html and layout blocks; the OCR row uses RapidOCR or tesseract only when available (#113).
- Provider: `opendataloader` (OpenDataLoader PDF 2.5.24, Apache-2.0), local Java engine; html and blocks, no OCR (#114).
- Providers: `liteparse` (LiteParse 2.21.1, local; html and blocks), as a text-layer row and, with `ocr=true`, a Tesseract row (`liteparse-tesseract`) and, with `ocr_backend=ocria-nano`, a row for LiteParse's own OCR and table models (`liteparse-ocria-nano`; its weights are under their own license, which allows benchmarking). Replaces #80 (#115).

### Fixed

- LLM harness: an empty reply (after the provider's own stripping) is a valid prediction of an empty page, not a failure after retries. This matters for blank pages, where empty is the right answer.
- LLM harness: a provider safety block (for example an HTTP 403 "blocked the request: SAFETY") is a per-page refusal, like `content_filter`, instead of an account error that stops the whole run. Real key and credit errors still stop the run.

## [1.8.0] - 2026-11-23

### Score impact

- Comparable with 1.7.x. Headline, family, suite, tag, argument-kind and derivation scores are unchanged. #103 checked this on two full public runs (MiniCPM-OCR 1.0, Surya OCR 2.5), and every number matched exactly.
- `format` verdicts are unchanged. Only where the format score is reported has moved (see Changed).
- Leaderboard: the README results were regraded with 1.7.0 in this release window, from saved predictions with no new model calls (#98). 1.8.0 gives the same numbers, since the headline is unchanged.
  - Most rows moved up 0.1 to 0.4 points against their 1.5.0 scores. HunyuanOCR-1.5 (+4.2) and PaddleOCR-VL-1.6 (+2.6) gained the most.
  - GPT-6.1 Sol and Claude Opus 5.5 were not regraded, and keep their 1.5.0 scores (marked § in the README).
  - Some rows come from new runs, not regrades: Gemini 4 Argon and Carbon (a full pass, plus a rerun of the pages it failed), Indra OCR (indra-ocr 1.1.2), and the layout of Gemini 3.8 Flash and GPT-5.6 Sol.
  - The hard slices were recomputed as plain pass rates.
- Refusal counts for Gemini 3.8 Flash (4) and Claude Sonnet 5.5 (6) were updated from their regraded runs (#101).

### Changed

- `format` tests may now share suites and pages with headline tests, so each page is predicted once for both (#103).
- The format score is reported as an auxiliary score, `auxiliary.format` (overall and `per_suite`), beside the headline (#103).
- `format` stays out of the headline and out of every headline slice. A format-only run keeps its fallback headline: the mean of the families it has (#103).
- The top-level `per_suite` pools headline-family tests only. A suite that holds only format tests appears only under `auxiliary.format.per_suite` (#103).
- `opb intervals`, `opb compare` and `opb reliability` report the auxiliary format score and its per-suite entries (#103).

### Data and format

- `vocab.AUXILIARY_FAMILIES = ("format",)`. Existing `format_*` suites keep working (#103).

## [1.7.1] - 2026-11-19

### Score impact

- No scorer change. Scores from 1.7.0 are comparable.
- Indra OCR runs made with this release use a newer model, so they are not comparable with earlier Indra OCR runs. On a 400-page sample, the new model scored 70.3 and the old one 64.4 (#99).

### Changed

- The Indra OCR server image installs `indra-ocr==1.1.2`, which loads models `v1.1.0`. It was `0.3.2`, which loaded `v3.1.1`. The adapter's default `served.revision` is now `v1.1.0` (#99).

## [1.7.0] - 2026-11-18

### Score impact

- Comparable with 1.6.0. Every existing test keeps its verdict, and the headline families (text, tables, layout) are unchanged.
- The new features are opt-in, so no published test changes verdict:
  - `exact_case` defaults to false;
  - a number argument on `repeat` is new;
  - `format` is a family of its own, outside the headline.
- Leaderboard: not regraded at release. The README was regraded with 1.7.0 later (#98), in the 1.8.0 release window.

### Added

- `exact_case` on a `present` text argument: when true, the text must be found with its case kept. It requires `max_diffs: 0` (#92).
- `exact_case` is refused on other test types, on numbers and LaTeX, and on text with no cased letter (#92).
- `repeat` takes a number argument, counted line by line with the strict number reading of `present` (separators and trailing zeros as written) (#90).
- A space-grouped number keeps its footnote markers when `repeat` counts it, so a marker can't join two digit groups (#95).
- A `format` test type: whether a span carries bold, italic, underline, strikethrough, superscript or subscript, with positive and negative tests (#96).
- `format` reads markdown and HTML alike, including CSS weight, style, decoration and vertical alignment (#96).
- A negative `format` test fails when the output carries no marks at all (#96).
- `format` is its own family and stays out of the headline. In this release it is refused in suites that hold headline tests (#96).
- Scoring reference pages `docs/scoring/repeat.md` (number counting) and `docs/scoring/format.md` (#90, #96).
- Scorer self-checks: the invariants now generate a `page_near_empty` answer, and relation M14 states the leader rule as fold applies it (#91, #94).
- The metamorphic certificate now holds 109 relations: 100 hold and 9 deviate, each deviation documented (#90, #92, #96).

### Data and format

- New derivation `computed`: values computed from a definition, kept only where they agree with the print (#93).
- New derivation `rendered_source`: pages rendered from markup we hold, so each formatting mark is known (#96).
- New test type `format`, with output type `html`, in family `format`. `vocab.HEADLINE_FAMILIES` names the headline families (#96).
- A `repeat` gold may hold text or a number, but not LaTeX. A number that reads as two numbers (`12,5`) is refused when the gold is loaded (#90).

## [1.6.0] - 2026-11-17

### Score impact

- Not comparable with 1.5.0. The scorer changed in both directions, so regrade saved predictions with 1.6.0 or later before you compare runs.
- Fewer passes:
  - `present` number tests: thousands and decimal separators must match the gold as written, so gold `1,240` no longer passes on `1240` (#84).
  - `present` text tests with `max_diffs` > 0: the edit budget is now counted exactly. A small share of budgeted tests went from pass to fail, which lowers a text score by well under 0.1 point (#84).
  - `present` and `order`: an exact match cut out of a longer number no longer passes. On saved predictions, 15 tests (#73) and 16 results (#75: 7 `order`, 9 `present`) went from pass to fail.
  - `table_cell` with `top_heading`: a spanning cell no longer lends the heading of another column (#84).
  - Equation and math-read text tests: 23 went from pass to fail under the single dollar-math reader (22 `present`, 1 `repeat`), all on outputs that pad their math with spaces (#72).
- More passes:
  - Glyph folds (#59, #60, #65): mostly `table_cell` and `present`. #59 gave 83 fail-to-pass, all `table_cell`. #65 gave 87 fail-to-pass, mostly Romanian `ş`/`ţ`.
  - Misgrade fixes for two prices, form blanks, leaders and alt text: 19 fail-to-pass across 8 systems (#61).
  - The dollar-math reader: 94 fail-to-pass (39 `table_cell`, 48 `present`, 6 `order`, 1 `repeat`) (#72).
  - `present` accepts an ambiguous wrapping hyphen: a few fail-to-pass on multilingual runs (#52).
  - `table_cell` allows exactly `max_diffs` edits: 3 fail-to-pass (#82). A middle dot in `\text{}` now renders: 1 fail-to-pass (#79).
  - The hyphen fallback in `order`, `repeat` and `table_cell`, the capitals line-end hyphen and the quote pair added only passes on the cached re-runs (#84).
- Not measured: the equation matcher fixes (#68) give no verdict counts.
- No effect on the published gold today: `right_heading` and `page_near_empty` (no gold tests use them yet), and the `\dfrac` fold (no gold `table_cell` holds a fraction) (#83, #85, #58).
- Leaderboard: not regraded at this release. The README was regraded with 1.7.0 later (#98, in the 1.8.0 release window).

### Added

- `opb intervals RUN`: a 95% interval on every score from a bootstrap over documents, one shared draw per run (#86).
- `opb compare RUN_A RUN_B`: the paired gap between two systems on their shared documents, with an interval and `excludes_zero` (#86).
- `opb reliability RUN ...` (5 or more runs): a flag for each slice, `noisy` or `redundant`, from split-half rank agreement (#87).
- New module `omni_parse_bench.uncertainty` with `intervals`, `paired` and `reliability`. It uses the standard library only (#86, #87).
- New summary slices `per_tag`, `per_suite`, `per_test_type` and `per_derivation`, each `{score, tests, documents}` (#70).
- A `per_arg_kind` slice (`text`, `number`, `latex`) in the summary, and `arg_kinds` on `opb tests` rows (#76).
- `effective_documents` on every summary entry, and `same_tests_as` on slice keys that select the same tests (#88).
- `table_cell` gains a `right_heading` role (#83).
- The `page_near_empty` test type: a page passes when its visible text stays within `max_chars`. It is in the text family (#85).
- A scoring reference in `docs/scoring/`: one page per test kind, with case tables checked against the scorer by `tests/test_scoring_reference.py` (#84).
- Hypothesis property tests for the scorer, with a `ci` and a `deep` profile. `hypothesis` joins the `dev` extra (#64).
- A metamorphic test suite with a generated `CERTIFICATE.md`: 68 relations, 60 hold and 8 deviate, each documented (#84).
- Providers: Xiaomi-OCR-0 (`xiaomi_ocr`) (#53), and OvisOCR, OvisOCR2 and OvisOCR3 (`ovisocr`, `ovisocr2`, `ovisocr3`) (#51).
- `docs/gemini4-2026-11-10.md` and `scripts/reproduce_gemini4.py` record the Gemini 4 Argon and Carbon runs (#66).

### Changed

- The text path and the equation path read dollar-delimited math with one reader, the new `omni_parse_bench/mathspans.py` (#72).
- Both paths read the same spans from the same text (#77). A `$$` display that holds inline math in `\text{}` stays one display (#74).
- `present` and `order` apply a digit-edge rule: an exact match may not sit glued to a longer number (#73, #75).
- When the digit edge rejects a match, the `why` says "found only inside a longer number" (#79).
- A failed `present` test's `why` ends with the closest text found, `; closest '...'`, up to 120 characters (#70).
- `present` counts its `max_diffs` budget exactly. A substitution, insertion, deletion or adjacent swap each costs one edit (#84).
- `present` accepts either reading of an ambiguous line-wrapping hyphen, in both gold and prediction (#52).
- `order`, `repeat` and `table_cell` accept a hyphenated word that is broken after its hyphen (#84).
- A line-end hyphen between two words in capitals now joins them (#84).
- Number tests match separators as the gold writes them. A gold with one `.` and exactly three decimals (`8.455`) now reads as a decimal (#84).
- A table heading walk stays inside the cell's own columns (for `top_heading`) or rows (for the row roles) (#84).
- A `<th>` with no other heading on its walk reads the cell at the edge (#84).
- `left`, `right`, `left_heading` and `right_heading` follow the html's cell order, so right-to-left tables read in reading order (#83).
- Fold: middle dots between digits become decimals only in context, `♢` → `◊` and `≦` → `≤` (#59).
- Fold: CJK middle dots, Romanian cedilla to comma-below, `〜` → `~`, `∗` → `*` and `״` → `"` (#65).
- Fold: the saltillo and IPA stress mark become an apostrophe (#60), and `\dfrac`, `\tfrac` and `\cfrac` fold as `\frac` (#58).
- Fold: CJK middle dots beside NFKC digits or zero-width characters are not folded into decimals (#67).
- Equation matching:
  - a match is a whole expression, and `\tag` and `\label` are ignored (#68);
  - the matcher recognizes more delimiters, and reads old-book conventions (rows of dots as an ellipsis, `°`, `≦`) (#68);
  - `\coloneq` renders as `\coloneqq`, and the matcher has a plain-text fallback (#68).
- Leader runs no longer cross a paragraph or cell break. A run of ideographic full stops counts as a leader (#84).
- A footnote mark set as a superscript, or `[n]` inside a phrase, is ignored for a text test (#84).
- Two single quotes in a row read as a double quote (#84).
- The LLM layout reader accepts `bbox` as a box key (#66).
- `fuzzysearch` is pinned to `>=0.8.1,<0.9` (#84).

### Fixed

- Two prices read as one math span, and form blanks (`__`) read as subscripts (#61).
- Prose between dollars took the `$` that opens real math, and a price before display math hid the equation (#61).
- A negative number after leaders lost its sign (#61).
- A full stop before a blank was dropped (#61).
- Image alt text beside a cell's text counted against the cell (#61).
- `Number('12.5')` passed inside `12.55`, `12.5.7` or `12.5,3` (#79).
- `\text{kJ/(kg·K)}` failed to render, and the span was read as empty (#79).
- An NFD letter before a line-end hyphen blocked the join (#78).
- A layout block covering exactly half a place decided its verdict by float rounding (#78).
- Prices in a markdown table row merged across `|` into one math span (#78).
- `table_cell` failed at exactly `max_diffs` edits by float rounding (#82).
- An `order` verdict depended on the Python hash seed (#84).
- Equal-area layout blocks tied by rounding (#84).
- Text view: a stray `<` erased text, comments left a space, namespaced tags were kept, and `>` in a quoted attribute ended a tag (#84).
- `page_near_empty` no longer counts invisible format characters, an empty `<math>`, a blank `<li>` or a hidden input (#84).
- The process hung at exit on Python 3.13. The KaTeX context now closes at exit (#64).

### Data and format

- Score lines gain per-slice counts, test-id digests and `row.suite`. Runs graded earlier have empty slices until they are graded again (#70, #76, #88).
- Tag definitions:
  - a table drawn inside a figure is `table`, and a figure's sub-caption is `caption` (#84);
  - a figure's title is `figure` inside the image and `caption` outside it (#84);
  - `tiny` is anchored at about 6.5 pt (#84).
- New test type `page_near_empty`: output `html`, family `text`, settings exactly `{max_chars}`, no args (#85).
- `table_cell` relations include `right_heading`, and `docs/building-tests.md` documents it (#83).

## [1.5.0] - 2026-11-02

### Score impact

- No score or summary changes. Scores from 1.4.0 are comparable (#56).

### Changed

- Each test line in a run's details (`details/<page_id>.jsonl`, `unit_tests.lines`) records the test's `args` and `settings` as its gold file states them (#56).
- `Test` holds `args` and `settings` once. `params`, what its runner reads, is now a property built from them (#56).

## [1.4.0] - 2026-11-02

### Score impact

- No scorer change. Headlines and every other number are unchanged (#55).

### Removed

- The summary's `answered` entry, added in 1.3.0. Every row's numbers and `status` remain in `scores.jsonl` (#55).

### Changed

- Requires omni-bench-core 0.14 (#55).

## [1.3.0] - 2026-11-02

### Score impact

- No scorer change. Headlines and every other number are unchanged (#54).

### Added

- Each summary gains `answered`: the summary of the answered rows alone, for diagnosis, not ranking (#54).

### Changed

- Requires omni-bench-core 0.13 (#54).
- A grading is refused when its failed rows' result keys differ from its scored rows' (#54).

## [1.2.0] - 2026-10-29

### Score impact

- Headlines and family scores are unchanged from 1.1.0 (#49).
- `coverage` now means the share of pages scored. It drops below 1 when pages fail (#49).
- Leaderboard:
  - OXR-1.0 (85.3) and Surya OCR 2.5 (85.9) rows added (#43, #48);
  - Claude Opus 5.5 marked `*`, as used in creating some tests (#38);
  - the hard-slices table moved into the README (#38).

### Added

- Providers: OXR-1.0 (`oxr`) (#43) and Surya OCR 2.5 (`surya-ocr-2.5`) (#48).

### Changed

- Requires omni-bench-core 0.12. This breaks code that reads a summary or subclasses a scorer, although it ships as a minor version (#49).
- `UnitTests.score_failure(tests)` takes the tests, and `UnitTests.headline` is `"score"` (#49).
- `unit_tests.summarize(lines)` returns `score` where it returned `headline` (#49).
- The summary is flat: families at the top, no `scored` or `zeroed`, and `failed` counted by cause (#49).
- An option an adapter applies itself is marked `metadata={"local": True}` and is not sent to its server (#47).
- `docs/results.md` is folded into the README (#38).

### Fixed

- `chandra-ocr` sent `headers_footers` to its server, so every page failed with HTTP 500 in 1.1.0 (#47).

## [1.1.0] - 2026-10-29

### Score impact

- Not comparable with 1.0.0 for runs with failed pages. A failed page's tests now count as failed, in their families. The headline is no longer multiplied by page coverage (#39).
- Runs with no failed pages are unchanged.
- Leaderboard: rescored under the new rule (#39). Only the five LLM runs' headlines moved:
  - Opus 5.5: 90.75 → 90.00;
  - GPT-6.1 Sol: 91.41 → 91.50;
  - Gemini 3.8 Flash: 92.74 → 92.89;
  - GPT-5.6 Sol: 87.73 → 87.83;
  - Sonnet 5.5: unchanged at 88.67.
- Held text released recursively (#44): 0 verdicts changed on three full regrades.
- New leaderboard rows:
  - Opus 5.5 and GPT-6.1 Sol, with refusal counts (#32);
  - Unlimited-OCR 2 (81.2) (#41);
  - prices beside scores, and new cost and latency charts (#33–#36).

### Added

- `markdown` as an output type a page can ask for (#37). No published test asks for it yet.
- `datalab` and `chandra-ocr` return markdown, with a `headers_footers` option that defaults to true, as before (#45).
- Providers: Unlimited-OCR 2 (#40) and MiniCPM-OCR 1.0 (#42).

### Changed

- `UnitTests.zero` scores a failed page as a prediction with no outputs, and writes its details like a scored page's (#39).
- `detail_fields` adds `page_id`, `suite` and `document` to each detail line (#39).
- Requires omni-bench-core 0.11 (#45).

### Fixed

- Nested holds leaked a placeholder, which crashed grading (`IndexError`) or swapped in the wrong text (#44).
- Private-use characters in the page's own text are no longer read as placeholders (#44).

## [1.0.0] - 2026-10-26

These are the changes since 1.0.0rc1. Read 1.0.0rc1 too when upgrading from 0.2.0.

### Score impact

- Not comparable with 1.0.0rc1 for runs with failed pages. The headline becomes the scored pages' family mean × page `coverage`, where rc1 failed every test of a failed page. 1.1.0 reverted this (#39).
- The `unsupported` verdict is gone. A test whose output the system can't produce fails ("no <output> output"), so an html-only system has a layout family of 0. The README shows such systems with headline "none".
- Table neighbours are read off the grid (#27). Of 76,858 `table_cell` tests, 0 verdicts flipped, and an `IndexError` that stopped scoring is gone.
- `opb grade` and `opb reread` read the dataset at the commit the run used (`dataset_commit`). Before, an old run was graded against the latest revision.
- Leaderboard:
  - the README gains a Results section with every system's scores (#26);
  - Nemotron 3.5 Parse added at 80.0 (#26);
  - Datalab rows from a rerun of the production API: accurate 94.1, balanced 92.6 (#29).

### Added

- Built on omni-bench-core (0.10). `opb init <system>` writes one config per system, and `opb run --config` runs it (#30).
- `opb resume <run>` continues a run with its own `config.yaml`, with `--set`. `opb run` always starts a new run (#30).
- `opb reread` reads saved answers again (#30).
- `opb systems` lists systems and their options (#30, #31).
- Served models report what they serve (`GET /served`: weights and revision), and a run checks it before any call (#30).
- Provider: Nemotron 3.5 Parse (`nemotron-parse`) (#26).

### Changed

- One run is one system answering one question. Each page asks for the outputs its tests read (#30).
- The summary is the headline plus a per-family breakdown, with `headline_is` and `scored` (#30).
- Grading reports a finished run only, unless `--partial` (#30).
- A run folder is `<label>-<time>-<4 hex>` and keeps its `config.yaml`. Details live at `<run>/unit_tests/details/` (#30).
- Serve folders are renamed `providers/oss/` → `providers/serve/` and named after their systems, and they take `WEIGHTS` and `REVISION` (#25, #30).

### Removed

- `opb benchmark` is replaced by `opb init`, `opb run` and `opb resume` (#30).
- Its flags (`--system`, `--options`, `--sample` and the rest) are gone. Some pre-1.0 flags still work, with a deprecation warning (#30).
- `opb providers` and `opb reparse` remain as deprecated aliases of `opb systems` and `opb reread`. `--outputs` and `--unsupported` are ignored (#30).

### Data and format

- `settings.json` names the dataset's commit as `dataset_commit`. A page's suite is optional and defaults to `other` (#30).

## [1.0.0rc1] - 2026-10-16

### Score impact

- On the Nemotron 3.5 Parse run, 1.0.0rc1 and 0.1.2 give the same 16,288 verdicts (#26).
- The `error` verdict is gone. A test that raises on a well-formed output is a scorer bug, and it stops grading with nothing written (#23).
- The scoring-code digest changed, so every run is graded again once, with no provider calls (#23).

### Added

- `opb check`: whether a dataset is one opb can run (#23).
- `harness.add_adapter` and the `omni_parse_bench.adapters` entry-point group for adapters of your own (#23).
- `benchmark.read_scores` (#23).
- Provider: Indra OCR, with a CPU server image (#21).

### Changed

- New module layout, aligned with omni-extract-bench:
  - `data` for datasets, `scorers/unit_tests` for the scorer (it was `metric.py`, with `gold.py` and `runners.py`), and `errors` (#23);
  - `score(pred, gold, unsupported=())`, `lines(verdicts, tests, page)`, and `summarize(lines)`, which needs nothing but the lines (#23);
  - `grade(run, pages)` (#23).
- Grading is fresh every time. Every predicted page is graded again, and `--rescore` and the refusal of another gold or scorer are gone (#23).
- A page with no prediction fails every test, unless the run never attempted it (#23).
- CLI results print to stdout as JSON. A `UsageError` or `Stop` exits 1, and Ctrl-C exits 130 (#23).

### Removed

- The pre-1.0 public names (`gold.Page`, `gold.manifest`, `gold.load`, `benchmark.manifest`, the `metric` module and others) are removed without shims (#23).

### Data and format

- A dataset may hold several manifests (`--manifest`, `read_manifest(dataset, manifest)`). A manifest may also be given whole as `hf://datasets/<org>/<name>/<path>` (#23).
- A manifest's extra columns are kept on `page.extra` and never refused (#23).
- `doc_path` may be any relative path inside the dataset, and pages may share one (#23).
- `gt_path` is named `<page_id>.json`. A page id is a filename, unique ignoring case (#23).
- `Page` is a frozen dataclass with `id` (#23).
- `summary.json` gains `failed` and per-suite `pages`, `failed` and `pending`. The headline is null while any page is pending (#23).

## [0.2.0] - 2026-10-14

### Added

- `opb grade DIR [--unsupported ...]` grades any folder of predictions, such as your own model's (#18).
- 13 open-weight providers, each with a pinned server image (#17): chandra-ocr, deepseek-ocr, dots-mocr, glm-ocr, hunyuan-ocr, infinity-parser2, lightonocr, mineru, nanonets-ocr, olmocr, paddleocr-vl, surya-ocr and unlimited-ocr.

### Changed

- Grading reads only `predictions/<page_id>.json`. `records/` adds only cost (#18).
- A page with a record but no readable prediction is predicted again (#18).
- `unsupported` is set once per run in `settings.json`. A prediction that leaves out an output its page asks for fails those tests (#18).
- An OpenAI-compatible `base_url` other than OpenRouter takes its key from `OPB_ENDPOINT_KEY`. `OPENROUTER_API_KEY` and `OPENAI_API_KEY` go only to OpenRouter (#17).

### Removed

- `benchmark.read_record`. Use `recorded(run, page_id)` and `predicted(run, page_id)` instead (#18).

### Data and format

- `settings.json` must state `unsupported`. Grading refuses a folder without it (#18).
- In `scores.jsonl`, the `record` stamp is renamed `prediction`. Old lines are graded again once, with the same verdicts (#18).

## [0.1.2] - 2026-10-14

### Added

- Public run bookkeeping for loops of your own: `prepare`, `needs`, `record`, `recorded` and `grade` (#7).
- `--workers` takes a JSON object of calls at once per adapter, such as `{"datalab": 8, "llm": 4}` (#12).

### Changed

- Grading refuses a run graded with another gold or other scoring code, unless `--rescore`. The gold revision is a digest of what grading reads (#9, #15).
- CLI errors are raised as Python exceptions. A command whose extra is missing raises `ImportError` with the install to run (#13).
- A run no longer notices a changed page file, because the page digest was removed (#7).
- `settings.json` records only what the run asks for (#7, #9).

### Data and format

- The manifest's `outputs` column is required. Older dataset revisions are refused, with how to get the current one (#8, #14).
- `gold.Page` has a required `outputs` field (#8).

## [0.1.1] - 2026-10-09

### Changed

- `opb` names the extra a command needs when an install lacks it. The README installs from PyPI (#5).

## [0.1.0] - 2026-10-09

### Added

- Initial release: a scorer for document parsing, built on unit tests.
- Five test types: `present`, `order` and `repeat` (text family), `table_cell` (tables) and `layout_kind` (layout).
- The headline is the mean of the families' pass rates.
- Verdicts are `pass`, `fail`, `unsupported` or `error`. `unsupported` and `error` are left out of every score.
- The `opb` command: `score`, `predict`, `benchmark`, `tests`, `reparse` and `providers`.
- Providers: Azure, Datalab, Extend, LlamaParse, LLMs over an OpenAI-compatible endpoint (OpenRouter), Mistral, Reducto and Tesseract.
- A release workflow that publishes to PyPI on a `v*` tag (#4).
- README: the design, test types, families and tags (#1, #2, #3).

### Data and format

- Output types `html` and `blocks`, a closed set of derivations, and tag definitions (roles, yes/no tags, script, language) in `vocab.py`.

[Unreleased]: https://github.com/datalab-to/omni_parse_bench/compare/v1.8.0...HEAD
[1.8.0]: https://github.com/datalab-to/omni_parse_bench/compare/v1.7.1...v1.8.0
[1.7.1]: https://github.com/datalab-to/omni_parse_bench/compare/v1.7.0...v1.7.1
[1.7.0]: https://github.com/datalab-to/omni_parse_bench/compare/v1.6.0...v1.7.0
[1.6.0]: https://github.com/datalab-to/omni_parse_bench/compare/v1.5.0...v1.6.0
[1.5.0]: https://github.com/datalab-to/omni_parse_bench/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/datalab-to/omni_parse_bench/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/datalab-to/omni_parse_bench/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/datalab-to/omni_parse_bench/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/datalab-to/omni_parse_bench/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/datalab-to/omni_parse_bench/compare/v1.0.0rc1...v1.0.0
[1.0.0rc1]: https://github.com/datalab-to/omni_parse_bench/compare/v0.2.0...v1.0.0rc1
[0.2.0]: https://github.com/datalab-to/omni_parse_bench/compare/v0.1.2...v0.2.0
[0.1.2]: https://github.com/datalab-to/omni_parse_bench/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/datalab-to/omni_parse_bench/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/datalab-to/omni_parse_bench/releases/tag/v0.1.0
