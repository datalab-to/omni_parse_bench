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

- None on grading: this changes how a run handles two provider replies, not how answers are scored. A page that used to fail as "no usable html" or stop the run now gets a prediction or a refusal instead, so a rerun can score pages that earlier runs lost.

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
