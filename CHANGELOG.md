# Changelog

## 1.0.0 (unreleased)

Breaking changes throughout, so omni-parse-bench and omni-extract-bench share one layout: the same
modules, the same names, at the same levels, and the same rules. Only the row's type differs (`Page`
here, `Doc` there). `docs/API.md` has the full surface.

Modules:

- `data` (new) reads a dataset: `Page`, `download_dataset` (the whole dataset, at one commit),
  `read_manifest`, `select`, `dataset_id`, `commit` and `ManifestError`. It replaces `gold.manifest`,
  `gold.load`, `benchmark.manifest`, `benchmark.pages`, `benchmark.page_file` and
  `benchmark.dataset_root`;
- `scorers/unit_tests` is the scorer, a package that owns the shape of its gold: `gold(page)`,
  `check(pages)`, `score`, `lines` and `summarize`, with `tests.py` (what a unit test is; was `gold.py`)
  and `runners.py`. It replaces `metric.py`. The text tools any scorer can use (`views`, `normalize`,
  `tables`, `equations`, `vocab`) stay at the top;
- `errors` (new) holds the two kinds of error a user meets: `UsageError` (a `ValueError`: what was asked
  is wrong) and `Stop` (a run can't go on). `ManifestError` and `GoldError` are `UsageError`s;
  `AccountFailure`, `MissingCredential` and `MissingDependency` are `Stop`s;
- `benchmark` is the loop. New public functions: `settled` and `declare` (a folder's settings.json,
  read and checked, and written), `gradable` (refuses a folder grading can't read), `is_run` (whether a
  folder's settings are a run's), `restore` (a lost prediction rebuilt from its record), `pools` (each
  adapter's calls at once), `write_json` and `read_scores`;
- `harness` gains `add_adapter`, loads adapters declared under the entry-point group
  `omni_parse_bench.adapters`, and exports `VendorUnreachable`; `registry.adapter_names()` lists the
  names `--workers` takes; and
- the package exports `data`, `scorers`, `gold`, `score`, `lines`, `summarize`, `check` and `Verdict`.

Helpers that were public by accident are private: `data.page`, `benchmark.missing`, `retryable`,
`merged`, `grade_page`, `headline`, `per_adapter`, `tests`, `workers_for`, `write_text` and
`read_json`.
A module imports modules, not names, so it no longer holds names it only imported:
`benchmark.UsageError` (and `Stop`, `counted`) is `errors.UsageError`.

The scorer:

- `score(pred, gold, unsupported=())`: the prediction, then the page's tests; an unknown output name in
  `unsupported` is refused;
- `lines(verdicts, tests, page)`: each line carries its page's `suite` and `document`;
- `summarize(lines)` needs nothing but the lines, so a `scores.jsonl`, or any part of one, is summarized
  as it is. `headline` is the number (it was a dict), beside `families` and `documents`; `per_suite` is
  one block per suite, its `headline` and `score` (it was the pass rate alone);
- a gold file that is missing, a folder, isn't JSON, isn't an object, has no `tests` list or no tests,
  or holds a test that isn't an object is a `GoldError` naming its page; repeat's settings are exactly
  `{expected_count}`;
- a verdict is `pass`, `fail` or `unsupported`: a test whose run raises on a well-formed output is a bug
  of ours, so `score` raises it, naming the test, and grading stops with no scores or summary written (the `error`
  verdict, the `errors` count and exit 2 are gone); with several runs, those graded before the
  crash keep their new files, and `--score-only` grades again after the fix;
- an output type every test of which is unsupported keeps its block, with `score` null; and
- the scoring-code digest changes, so every run is graded again once; no provider is called.

Grading:

- `grade(run, pages, say=print, *, settings=None)` replaces `grade(run, dataset)`. It always covers the
  whole manifest (`grade_all` passes it), so `--limit` and `--suites` narrow what is predicted, never
  what is scored; `opb grade` has no `--suites`;
- grading is fresh every time: every page is graded again, and `scores.jsonl`, then `summary.json`, are
  written when it finishes; an interrupted grading writes no scores or summary. `--rescore` is gone, and so is the
  refusal of a run graded with another scorer or gold;
- a page with no prediction is pending only when a run never attempted it (no record, in a folder whose
  settings.json names a provider); otherwise every test of it fails, so a page left out of a folder of
  your own fails, records/ or not;
- a folder of your own none of whose files names a page of the manifest is refused, writing nothing, so
  a forgotten `--dataset` can't grade it against ours; grading fewer pages than the folder's manifest
  warns that the summary covers only those;
- while any page is pending, `headline` is null, overall and for each suite with pending pages: a run
  has a headline only once it is finished;
- summary.json starts with `run`, `provider` and `settings`; it gains `failed` (pages with an output
  missing, null or malformed that the system can produce) and, per suite, `pages`, `failed` and
  `pending`; `pages_pending` is `pending`; `usd` and `credits` are each null when no call reported it;
- a prediction is read only under its exact name, case too, so a folder grades the same on every disk;
  any JSON object is a prediction, keys other than output types ignored, and a UTF-8 byte-order mark is
  read through. Grading warns once about files
  named for no page (with "did you mean" for a slip of case), predictions it couldn't read, predictions
  holding no output type, and predictions with a malformed output (all graded as failed);
- `owed` counts what grading will grade over the whole manifest, by the same rule as `grade`; and
- score lines carry only the `scorer` stamp; the prediction and gold digests are gone.

Runs and folders:

- a folder holds one dataset and one manifest: `plan` and `opb grade` refuse another, in one wording.
  `opb grade` reads them from the folder's settings.json when not given; a folder of your own gets them
  there, with `unsupported` (required on its first grading), once its first grading succeeds (a
  failed one writes no settings, scores or summary); another `--unsupported` is refused too. A folder of
  your own's refusal says its settings.json can be deleted to start over; a run's says to use another
  `--out`, since its records are answers for its own dataset's pages. The rule is per run folder;
  `--out` is only their parent. `--unsupported` is refused on a run's folder; a manifest's path is
  spelled one way (`./manifest.parquet` is `manifest.parquet`, `data.normal`), and one outside the
  dataset is refused before anything is compared;
- the record is the source of truth for an answer: a prediction lost or unreadable beside its record is
  rebuilt from it, with no call, whenever the run is graded (`--score-only` and `opb grade` too) and by
  `opb reparse`;
- `prepare` writes settings.json whole; `record(run, page_id, result)` takes what `harness.predict`
  returned (it was `new`);
- `plan` warns when a run made at one commit of its dataset is planned at another, and carries on; it
  refuses an empty selection, a run asked for twice, `--score-only` into a folder never predicted, a
  negative `timeout` or `workers` (a `workers` of the wrong type is a `TypeError`);
- `--retry-failed` predicts again a timeout, an outage (`VendorUnreachable`) or a 429, 5xx or 52x; an
  answer that arrived and couldn't be used, with no HTTP status, is no longer retried;
- a `Stop` stops its adapter's queued pages at once, set by the worker that hit it;
- `--workers` is keyed by adapter: one of yours by the name it was filed or declared under; an option
  given as a whole number for a float setting is that float, so it names the same run; one of the wrong
  type is refused; and
- `execute` grades what was predicted when predicting fails part way (an account failure included),
  but not when it is interrupted; `--score-only` grades it then. A bug in an adapter stops its runs, with
  a note naming the run, the page and the adapter.

Datasets:

- a dataset may hold several manifests: `read_manifest(dataset, manifest="manifest.parquet")` and
  `--manifest` (a path inside the dataset) on `benchmark`, `grade`, `check` and `tests`;
- a manifest may also be given whole, `hf://datasets/<org>/<name>[@<revision>]/<path>`, as
  omni-extract-bench took it before 1.0: `data.located` splits it into its dataset and its path;
- a `doc_path` is any relative path inside the dataset to a .pdf or .png, and pages may share one; a
  `gt_path` is a relative path inside the dataset named `<page_id>.json` (both were exactly `pages/...`
  and `gold/...`); a page_id is a filename, unique ignoring case; a null or empty suite is `"other"`
  (`data.NO_SUITE`); an empty manifest is refused;
- `Page` is a frozen dataclass (it was a NamedTuple) with `id`, the page's `page_id`; its `doc_path` and
  `gt_path` are `Path`s; a manifest's columns of its own are kept on `page.extra`, never refused;
- `select` reads `suites` and `only` once, so any iterable works, and refuses a bare string;
- an `hf://` address is checked (`hf://datasets/<org>/<name>[@<revision>]`; `hf:/...` is named as a
  typo); a download is tried again up to five times, each retry logged, and one that would fail the
  same way every time (no access, a missing revision, offline with nothing cached) is refused at once;
- page ids that differ only in case are named with both spellings; and
- `unit_tests.check` no longer refuses a gold file its manifest doesn't name.

The command line:

- results go to stdout as JSON: `opb benchmark` and `opb grade` print each run's whole summary (its
  summary.json; `html` is now `html.score`), after a `Stop` too; the closing line and messages go to
  stderr. There is no `-q`;
- a `UsageError` or a `Stop` prints `opb <command>: <message>` and exits 1 (`benchmark` adds that a
  rerun resumes); Ctrl-C exits 130; anything else is a traceback, a bug of ours. A bad `--workers` is
  one of these, not an argparse error;
- the closing hint counts only the pages `--retry-failed` would predict again;
- `opb benchmark -y`, and `--score-only`, which spends nothing, print the plan and don't ask; a declined
  plan prints `nothing run`; the question goes to stderr; with no terminal to ask (a pipe, a notebook,
  CI), `opb benchmark` goes ahead without asking, as before;
- a bug of ours is a traceback and exits 1, as a `UsageError` or a `Stop` does; stderr tells them apart;
- `opb check` (new) says whether a dataset is one opb can run: its manifest, every file it names, and
  every gold; it names the page and column of a missing file;
- `opb score` names the flag and file of a missing or non-object prediction, and a record passed as
  one, or a folder; `opb reparse` refuses a folder without records/ or a file that isn't a record,
  checks every record before rewriting any, rebuilds lost predictions, and says to regrade; an unknown
  option is named, with the nearest one; a folder of loose `<page_id>.json` files is told to move them
  into `predictions/`; and
- a `--pages` file skips blank lines and `#` comments; `--options` says when a path doesn't exist; files
  given to the command line may start with a UTF-8 byte-order mark; an option of NaN or infinity is
  refused; `--workers` takes 0 for one adapter as its default; and `opb score --pred` given a gold file
  says so.

Providers:

- the open models' servers are in `providers/serve/<model>/` (was `providers/oss/<model>/`), so an image
  is built with `docker build -t opb-<model> omni_parse_bench/harness/providers/serve/<model>`; and
- a request no longer records the server folder it goes to: `dots`, `unlimited`, `chandra_ocr`,
  `indra_ocr` and `olmocr` sent `"server": "oss/<model>"`, so those five name new runs.
