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
- a page's suite may be null or empty, and is then `"other"` (`data.NO_SUITE`); a page_id must be a
  filename, one path component;
- `opb check` says whether a dataset is one opb can run: its manifest, that every file it names
  exists, and every gold (`unit_tests.check`). A gold without `tests` is a `GoldError`, naming its page;
- `owed` counts what grading will grade over the whole manifest, as `grade_all` does; it counted
  only the selected pages;
- `prepare` writes `settings.json` whole; it merged into what was there;
- an `hf://` address is checked: `hf://datasets/<org>/<name>[@<revision>]`;
- a manifest may carry columns of its own: they're kept on `page.extra`, never refused; and
- `Page` is a frozen dataclass (it was a NamedTuple), with `id`, the page's `page_id`.

Helpers that were public by accident are private: `data.page`, `benchmark.missing`, `retryable`,
`merged`, `grade_page`, `errors_in`, `headline`, `per_adapter`, `tests`, `workers_for`, `write_json`,
`write_text` and `read_json`.

The scoring-code digest changes, so every run is graded again once; no provider is called.
