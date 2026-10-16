# Changelog

## 1.0.0 (unreleased)

Breaking changes throughout, so omni-parse-bench and omni-extract-bench share one layout: the same
modules, the same names, at the same levels. Only the row's type differs (`Page` here, `Doc` there).
`docs/API.md` has the full surface.

The modules:

- `data` (new) reads a dataset: `Page`, `download_dataset` (the whole dataset, at one commit),
  `read_manifest` (every page, with `doc_path` and `gt_path` as full local paths), `select`,
  `dataset_id` and `ManifestError`. It replaces `gold.manifest`, `gold.load`, `benchmark.manifest`,
  `benchmark.pages`, `benchmark.page_file` and `benchmark.dataset_root`;
- `scorers/unit_tests` is the scorer, a package that owns the shape of its gold: `gold(page)`,
  `check(pages)`, `score`, `lines` and `summarize`, with `tests.py` (what a unit test is; was
  `gold.py`) and `runners.py` (was `runners.py`). It replaces `metric.py`. The text tools any scorer
  can use (`views`, `normalize`, `tables`, `equations`, `vocab`) stay at the top;
- `benchmark` is the loop, as before; and
- `harness` gains `add_adapter`, and loads adapters declared under the entry-point group
  `omni_parse_bench.adapters`.

The scorer:

- `score(pred, gold, unsupported=())`: the prediction, then the page's tests;
- `lines(verdicts, tests, page)`: each line carries its page's `suite` and `document`;
- `summarize(lines)` needs nothing but the lines, so a `scores.jsonl`, or any part of one, is
  summarized as it is; and
- `summary["headline"]` is the number (it was a dict), beside `families` and `documents`.

Grading:

- `grade(run, pages)` replaces `grade(run, dataset)`;
- grading is fresh every time: every page is graded again, and `scores.jsonl` and `summary.json` are
  written whole when it finishes, so they're always one grading's. An interrupted grading writes
  nothing. `--rescore` is gone, and so is the refusal of a run graded with another scorer or gold;
- a page with no prediction is pending only when the run never attempted it (no record either, in a
  folder that keeps `records/`); otherwise every test of it fails. So a page left out of a folder of
  your own predictions now fails. `opb grade --suites` grades part of a dataset on purpose;
- score lines carry only the `scorer` stamp; the prediction and gold digests are gone;
- `summary.json`'s `pages_pending` is `pending`, as in omni-extract-bench;
- `benchmark.read_scores(run)` reads a run's lines back; and
- `scorers.unit_tests.check(pages)` (was `gold.load`) checks a whole dataset, for publishing and
  `opb tests`. Grading doesn't use it.

Datasets:

- a dataset may hold several manifests: `read_manifest(dataset, manifest="manifest.parquet")`, and
  `--manifest` on `benchmark`, `grade` and `tests` (as in omni-extract-bench). A sample, or the same pages
  with a gold of another kind, is a manifest of its own; `settings.json` records which. A `doc_path` may be
  any path inside the dataset, and pages may share one; a `gt_path` may be any path inside the dataset
  named for its page, `<page_id>.json` (both were exactly `pages/...` and `gold/...`), and `unit_tests.check` no longer refuses a gold file its manifest doesn't name;
- `record(run, page_id, result)`: the argument is what `harness.predict` returned (it was `new`);
- `plan` warns when a run made at one commit of its dataset is planned at another, and carries on;
- `plan` refuses an empty selection;
- `execute` grades what was predicted when predicting fails part way, but not when it is interrupted
  (Ctrl-C); `--score-only` grades it then;
- page ids must be unique ignoring case, since each names files;
- `opb benchmark` and `opb grade` print each run's whole summary (its summary.json), as
  omni-extract-bench does; they printed a digest with each output's score flattened (`html` is now
  `html.score`);
- a mistake on the command line (a ValueError or a missing file) prints `opb <command>: <message>` and
  exits 1, instead of a traceback;
- `opb grade <folder>` takes the dataset and manifest from the folder's settings.json when they aren't
  given, and refuses another dataset than the run's; `--suites` on a run's folder warns that it replaces
  the full summary; a missing folder is named;
- grading says which files in predictions/ match no page (left out) and which couldn't be read or hold
  no output type (graded as failed); a prediction's other keys are ignored, as `score` ignores them; it
  refuses an empty selection; scores.jsonl and summary.json are moved into place together;
- `opb check` refuses a manifest with no pages; `--manifest` outside the dataset is refused, and one given
  as a path on disk is pointed at `--dataset`; `hf:/...` (one slash) is named as a typo;
- output names are checked where they are given (`opb score --unsupported`, `opb predict --wants`,
  `harness.predict(wants=...)`); an option value of the wrong type is refused, naming the option;
- `plan` and `select` refuse a bare string where a list of names goes, a negative or non-integer count,
  a negative `timeout` and a `workers` that isn't a number or a mapping; `only` takes any iterable;
- `registry.resolve` gives an adapter of yours the name it was filed or declared under (ours keep their
  short module name), so `--workers '{"mine": 2}'` names a plugin's adapter;
- a gold file that isn't JSON, isn't an object, or holds a test that isn't an object is a `GoldError`
  naming its page; `opb score` names a prediction that isn't an object, or is a whole record;
- `opb reparse` refuses a folder without records/, and checks every record before rewriting any;
- a page's suite may be null or empty, and is then `"other"` (`data.NO_SUITE`); a page_id must be a
  filename, one path component;
- `opb check` says whether a dataset is one opb can run: its manifest, that every file it names
  exists, and every gold (`unit_tests.check`). A gold without `tests` is a `GoldError`, naming its page;
- `owed` counts what grading will grade over the whole manifest, as `grade_all` does; it counted
  only the selected pages;
- `prepare` writes `settings.json` whole; it merged into what was there;
- an `hf://` address is checked: `hf://datasets/<org>/<name>[@<revision>]`;
- while any page is pending, summary.json's `headline` is null and the closing line prints `—` for
  each score: a run has a headline only once it is finished;
- summary.json gains `failed` (pages with an output missing or null that the system can produce) and
  `suites` (pages, failed and pending per suite); `credits` is null when no call reported any; the
  closing line says how many failed, and that `--retry-failed` and `opb reparse` may help;
- a run folder holds one manifest, as it holds one dataset: `plan` and `opb grade` refuse another;
  `--score-only` into a folder never predicted is refused;
- `opb grade` on a folder of your own writes its dataset, manifest and `unsupported` to settings.json once
  a grading succeeds (a failed one writes nothing), so later gradings need no flags and refuse another
  dataset or manifest; `--unsupported` is refused on a run's folder; `--suites` on any folder already
  graded warns that it replaces the summary;
- a prediction is read only under its exact name, case too, so a folder grades the same on every disk;
  files of pages outside `--suites` aren't reported as stray;
- an option given as a whole number for a float setting is that float, so it names the same run;
- an account failure, a missing key and Ctrl-C (exit 130) are one line on the command line, not a
  traceback; `opb check` names the page and column of a missing file; a `--pages` file skips blank
  lines and `#` comments; `unit_tests.score` refuses an unknown output name in `unsupported`;
  `read_scores` refuses a folder that doesn't exist; `opb reparse` says to regrade;
- a manifest may carry columns of its own: they're kept on `page.extra`, never refused; and
- `Page` is a frozen dataclass (it was a NamedTuple), with `id`, the page's `page_id`.

Helpers that were public by accident are private: `data.page`, `benchmark.missing`, `retryable`,
`merged`, `grade_page`, `errors_in`, `headline`, `per_adapter`, `tests`, `workers_for`, `write_json`,
`write_text` and `read_json`.

The scoring-code digest changes, so every run is graded again once; no provider is called.
