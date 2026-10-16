# API

This is the public API of the toolkit. `score` and `predict` are the primitives `benchmark` is
built from; each works in your code and from the CLI. The CLI is a thin wrapper, except that
`benchmark` shows the plan and, in a terminal, waits for a yes; nothing in the library reads stdin.

1. [score](#score): one page's outputs against its tests;
2. [predict](#predict): one page, one provider;
3. [benchmark](#benchmark): every page, every provider, resumable;
4. [providers](#providers): what you can run, and what each one takes;
5. [The dataset](#the-dataset): loading it, and exploring its tests;
6. [Asking a question](#asking-a-question): slicing the scores of several providers by tag, suite or
   test type; and
7. [What a benchmark writes](#what-a-benchmark-writes): the files, and what is in them.


## score

The base install. No network, no API keys, no vendor packages.

The scorer is `omni_parse_bench.scorers.unit_tests`, a package that owns the shape of its gold: what a
unit test is (`tests.py`) and how each test type is run (`runners.py`). `score`, `lines` and
`summarize` are also importable from `omni_parse_bench` itself.

```python
from omni_parse_bench.scorers import unit_tests

unit_tests.gold(page)  # a page's tests, from its gold file (`page.gt_path`), read and checked

unit_tests.score(
  pred,               # one page's prediction: {"html": str, "blocks": [...]}, an output None if it errored
  gold,               # the page's tests: unit_tests.gold(page), or unit_tests.tests.read("gold/<page_id>.json")
  unsupported=(),     # output types the provider can't produce, e.g. {"blocks"}
)                     # -> [Verdict(id, result, why), ...], one per test

unit_tests.lines(
  verdicts,           # one page's verdicts
  tests,              # the tests they grade, looked up by id
  page,               # the page they're on
)                     # -> [{page_id, suite, document, test_id, test_type, output_type, derivation, tags,
                      #      result, why}, ...]

unit_tests.summarize(
  lines,              # score lines: from `lines`, or a run's scores.jsonl, whole or any part of it
)                     # -> a dict of scores

unit_tests.check(pages)  # every page's tests, and the dataset as a whole, checked: for publishing
```

A score line is a verdict beside its page and its test. A run's `scores.jsonl` holds the same lines
(with the run and the scorer that graded them), so `summarize` reads it as it is.

The inputs:

- `pred["html"]` is the page as HTML, the format every test but layout reads. Markdown is
  converted to HTML by the adapters, so a provider's own format never reaches the scorer;
- `pred["blocks"]` is the page's layout: a list of `{"label", "bbox", "text"}`. `label` is one
  of `views.LABELS` (text, heading, page_furniture, list, caption, footnote, equation, code, table,
  form, figure); `bbox` is `[x0, y0, x1, y1]`, fractions of the page from its top left; and
- an output that is missing, None or malformed (html that isn't a string; a block whose label isn't
  in `views.LABELS` or whose box isn't four numbers from 0 to 1) fails its tests; an output in
  `unsupported` leaves its tests out of the score.

```json
{"html": "<p>42</p><p>ANDY HAMMERLINDL AND RAFAEL POTRIE</p>...",
 "blocks": [{"label": "page_furniture", "bbox": [0.202, 0.121, 0.220, 0.132], "text": "42"}, ...]}
```

The output of `score` is one verdict per test:

```python
[Verdict(id='2503.08077_pg42_math_000', result='fail', why="equation not found (17 symbols; the output's math has 51)"),
 Verdict(id='olmo_arxiv_math-2503.08077_pg42-p1_line0_kind', result='pass', why=''),
 ...]
```

`result` is `pass`, `fail`, `unsupported` or `error`, and `why` says what went wrong. `error` is an
exception raised in the scorer's own code on a well-formed output: it is ours, not the provider's,
so it is left out of the score like `unsupported`, and counted.

The output of `summarize`:

```json
{
  "headline": 0.905,
  "families": {"text": {"score": 0.871, "tests": 8515, "documents": 1791}, ...},
  "documents": 2343,
  "html": {"score": 0.878, "tests": 13901, "unsupported": 0, "errors": 0, "documents": 2343,
           "per_test_type": {"present": 0.867, "order": 0.892, "repeat": 0.829, "table_cell": 0.890},
           "per_tag": {"table": {"score": 0.887, "tests": 6164, "pages": 966, "documents": 843},
                       "tha": {"score": 0.846, "tests": 26, "pages": 11, "documents": 6},
                       ...}},
  "blocks": {"...": "the same shape"},
  "per_suite": {"docparsing_images": 0.977, "forms_documentcloud": 0.918, ...},
  "per_derivation": {"text_layer": 0.862, "publisher_markup": 0.892, ...}
}
```

- `headline` is the mean of the families' scores (text, tables, layout), over the families the
  verdicts' tests are in, so each family weighs the same however many tests it has. It is null
  when a family has no scored test, all unsupported or error (a provider with no blocks has no
  layout score), since a mean over fewer families isn't the same number;
- each output type has its `score` (the share of its tests passed), `per_test_type` and `per_tag`;
  and
- `documents` is how many source documents a score's tests are from. A document's
  tests pass or fail together, so a score over few documents says less than its test count suggests
  (the Thai row above: 26 tests, 6 documents).

From the command line, with the outputs in a JSON file:

```bash
opb score --pred outputs.json --gold gold/<page_id>.json [--unsupported blocks]
```
```json
[
  {"id": "2503.08077_pg42_math_000", "result": "fail", "why": "equation not found (17 symbols; the output's math has 51)"},
  {"id": "olmo_arxiv_math-2503.08077_pg42-p1_line0_kind", "result": "pass", "why": ""},
  ...
]
```

It prints what `score` returns to stdout, one verdict per test, so
`opb score ... | jq 'map(select(.result == "fail"))'` lists a page's failures. `--pred` is `pred`,
`--gold` is the page's gold file and `--unsupported` is `unsupported`. A score over many pages comes
from `summarize`, or from `summary.json` when `opb benchmark` grades a run.

The README has a [worked example](../README.md#score), and [`design.md`](./design.md) says how each
test type is graded.


## predict

Needs the harness extra.

```bash
uv pip install 'omni-parse-bench[harness]'
```

```python
from omni_parse_bench import harness

harness.predict(
  provider,           # a vendor name, or an OpenRouter model id
  page,               # path to the page: a one-page .pdf or a .png
  wants=None,         # the output types to produce, e.g. {"html", "blocks"}; None: all it supports
  timeout=900.0,      # seconds per vendor call
  **options,          # anything the provider takes, e.g. mode="accurate"
)                     # -> a record
```

Keys come from the environment and nowhere else: `DATALAB_API_KEY`, `REDUCTO_API_KEY`,
`OPENROUTER_API_KEY` and so on ([providers.md](./providers.md) lists them).

The record is the outputs and the evidence for them:

```python
record = harness.predict("datalab", "pages/<page_id>.pdf", {"html", "blocks"}, mode="balanced")
record["outputs"]       # {"html": "...", "blocks": [...]}: what score reads
record["errors"]        # {output: why} for each output that failed or is unsupported
record["calls"]         # one per vendor call: what was sent, cost, wall time, attempts, failure
record["raw"]           # the vendor's answer to each call, as received
record["settings"]      # the provider's whole resolved configuration
```

One call looks like this:

```json
{"outputs": ["blocks", "html"],
 "sent": {"mode": "balanced", "output_format": "html,chunks", "...": "..."},
 "usd": 0.004, "credits": null, "source": "cost_breakdown.final_cost_cents",
 "tokens_in": null, "tokens_out": null, "wall_s": 8.7, "attempts": 1, "timeout_s": 900.0, "failure": null,
 "job_id": "ly6T1xlBNwJzbQMn9Ikeaw"}
```

Score straight from it:

```python
unit_tests.score(record["outputs"], unit_tests.tests.read("gold/<page_id>.json"))
```

From the command line:

```bash
opb predict --provider datalab --page pages/<page_id>.pdf --wants html blocks --options '{"mode": "accurate"}'
```

It prints the record without `raw`; `--raw` keeps it. It exits 1 when an output failed.

These errors raise, since they are the same on every page:

```python
MissingCredential    # an unset API key
MissingDependency    # an adapter's SDK or binary isn't installed
AccountFailure       # the key is refused, or the account can't pay
FileNotFoundError    # no page at that path
ValueError           # an unknown provider or option
```

Everything else comes back in `record["errors"]`, with whatever outputs did arrive beside it.


## benchmark

Needs the benchmark extra.

```bash
uv pip install 'omni-parse-bench[benchmark]'
```

Running this costs money, and needs your API keys set.

```python
from omni_parse_bench import benchmark, data

p = benchmark.plan(
  providers,              # e.g. ["datalab", "openai/gpt-5.6-sol"]
  out="runs",             # where run directories go, a str or a Path
  dataset=data.DEFAULT_DATASET,        # a dataset folder, or hf://datasets/<repo>[@revision]
  suites=None,            # limit to these suites
  limit=0,                # first N pages
  sample=0,               # N pages spread over every suite, for a smoke test
  only=None,              # a set of page ids: run only these
  options=None,           # per provider: {"datalab": {"mode": "accurate"}}, or a list of dicts
  timeout=0,              # seconds per vendor call; 0: the default, 900
  workers=0,              # calls at once per adapter, shared by its runs: one number, or per adapter
                          # ({"datalab": 20, "llm": 3}); 0, or an adapter left out: `benchmark.WORKERS`
  score_only=False,       # grade what's recorded; call no vendor
  retry_failed=False,     # predict again outputs whose failure may not recur
)
print(benchmark.describe(p))          # the plan, with no vendor call
summaries = benchmark.execute(p)      # predict, then grade
summaries["datalab-f45991d3"]["headline"]   # e.g. 0.905
```

A plan has two levels:

```python
Plan    # the invocation: every Run, and the pages they cover
Run     # a provider plus its options, and the directory it writes to
```

Each page is asked for exactly the outputs its tests read, so a page with no layout tests is never
asked for blocks.

### From the CLI

```bash
opb benchmark --providers datalab openai/gpt-5.6-sol --out runs/ --limit 5
```

It shows the plan (each run, its settings, and how many pages it will predict and grade) and, in a
terminal, asks before calling any vendor; `-y` skips the question, and a script or pipe proceeds
without it. It prints each run's summary, by run name, as its summary.json holds it: the scores,
`pages` (graded), `pending` (never attempted) and how many pages `failed` (an output missing or null
that the provider can produce: `--retry-failed` may redo some, `opb reparse` re-reads answers that
arrived). While a run has pages pending its `headline` is null and its closing line shows `—`: a run
has a headline only once it is finished. It exits 2, with a warning, when a test's grading failed in our code (`errors` in a
summary's output type), since those tests are left out of the score. A mistake in what was asked, an
account failure or a missing key is printed in one line, `opb benchmark: ...`, and exits 1; Ctrl-C
exits 130. Either way, what was predicted is kept, and the same command resumes.

### At once

Concurrency is per adapter, not per run: every run of one adapter shares one pool, since a vendor's
rate limit is per account. Two datalab modes share datalab's pool, and every OpenRouter model id
shares the llm adapter's. Each adapter's pool size is in `benchmark.WORKERS` (datalab 10, extend,
mistral and llm 5, reducto, llamaparse and azure 3, tesseract the CPU count up to 8, others 5);
`--workers N` sets N for every adapter; `--workers '{"datalab": 20, "llm": 3}'` sets only the adapters
named, and the others keep their defaults. Keys are adapters, not providers or models: the limit is
the vendor account's, so 3 for `llm` is 3 in flight across every OpenRouter model id together. A
model id as a key is refused, naming its adapter. An adapter of yours is keyed by the name you filed or
declared it under (`add_adapter("mine", ...)` is `{"mine": 2}`). When one run hits an account failure
or a missing key, every run of its adapter stops at once; other adapters go on, the run is graded, and
the failure is then raised. An exception from an adapter that isn't a vendor's answer (a bug in it)
stops that adapter's runs the same way, naming the run, the page and the file, rather than being
recorded as the page's failure.

Inside one call, a 429 or 5xx is tried again after 20, 60 and then 120 seconds before it is recorded,
so a page a vendor throttles holds its worker for up to about 200 seconds plus the calls. A timeout is
not tried again within the call: that would spend a second whole budget.

### Settings per provider

`--options` can give a provider a list, and each entry is its own run:

```bash
opb benchmark --providers datalab --out runs/ \
  --options '{"datalab": [{"mode": "balanced"}, {"mode": "accurate"}]}'
```

That's 2 runs.

### Choosing the pages

- `--dataset`: a dataset folder, or `hf://datasets/<repo>[@revision]`. The default is ours,
  `hf://datasets/datalab-to/omni_parse_bench`, a private repository, so run `hf auth login`
  first. A Hugging Face dataset is downloaded whole (1.5 GB), once, into Hugging Face's cache;
- `--manifest`: which of the dataset's manifests, a parquet inside it (default `manifest.parquet`). A
  dataset may hold others: a sample (`manifests/sample40.parquet`), or the same pages with a gold of
  another kind (`gt_path` pointing at `transcripts/` instead of `gold/`), each naming its pages and
  where their gold is. `opb grade`, `opb check` and `opb tests` take it too. A run folder holds one
  manifest, as it holds one dataset: another `--manifest` into it is refused;
- `--suites`: only these suites;
- `--limit N`: the first N pages;
- `--sample N`: N pages spread over every suite, the same ones each time; N larger than the
  selection runs all of it, and with `--pages` it samples among those pages; and
- `--pages FILE`: the page ids in a file, one per line (blank lines and `#` comments are skipped). To
  run one tag's pages, see
  [Exploring the tests](#exploring-the-tests).

### Resuming

It's resumable, and safe to run twice.

- A page is predicted again only for the outputs its record doesn't hold; an output recorded as
  unsupported is held. The record is written last, so its presence means the prediction beside it
  is complete;
- a run folder assumes its pages don't change under it: a page with a record is not predicted again,
  and pages are pinned to a dataset commit and never edited in place. To predict again after a
  dataset's pages change, use a new `--out`;
- a record that isn't readable JSON counts as not predicted, and is logged;
- grading is fresh every time: every predicted page is graded again (no provider is called), and
  `scores.jsonl` and `summary.json` are written whole when grading finishes. So a run's scores are
  always one grading's, and a gold correction or a new scorer reaches a run on its next grading;
- grading covers every page the run has a prediction for, so `--limit` and `--suites` narrow what is
  predicted, never what is scored; and
- an interrupted grading writes nothing: both files are written beside the old ones and moved into place
  together at the end, so the last finished grading's pair stands.

A run folder holds one dataset and one manifest: an invocation with another `--dataset` or
`--manifest` into it is refused, and `--score-only` into a folder that was never predicted is too. A dataset
is downloaded at one commit, its pages and gold together. An invocation at another commit of the run's
dataset is warned about and carries on: its predictions are graded against the new commit's gold, which
is what a gold correction wants; if the pages changed too, pass another `--out`.

`--score-only` predicts nothing, and grades. `--retry-failed` predicts again
the outputs whose failure may not recur: a timeout, an outage, a 429 or 5xx (Cloudflare's 520 to 524
too), or a failure with no HTTP status. A 400, a vendor's failed job, or an LLM reply that was
truncated, refused or unusable is an answer, and is not retried. It decides from each failed call's
`class` and `status` in the record; a record's `transient` says something else, whether the call was
tried again within itself (a 429 or 5xx), which a timeout never is.

An output whose answer arrived but didn't parse is fixed for free: after a parsing fix,
`opb reparse RUN_DIR` reads every record's outputs again from its saved answers, and
`opb benchmark ... --score-only` grades the pages whose outputs changed.

### A loop of your own

`opb benchmark` is one loop over pages. To predict elsewhere (on another machine, on a GPU cluster, on
a scheduler) and still get the same run folder, keep the run with the functions `opb benchmark` uses
itself. A `benchmark.Run` is an address, as a `Path` is: what the run holds is whatever its folder
holds when it is read.

```python
from omni_parse_bench import benchmark, data, harness

p = benchmark.plan(["dots-mocr"], out="runs")
(run,) = p.runs
_, every = data.read_manifest(p.dataset)
benchmark.prepare(run, p.dataset, p.timeout)
for page in p.pages:
    if need := benchmark.needs(run, page):
        result = harness.predict(run.provider, page.doc_path, need, timeout=p.timeout, **run.options)  # wherever
        benchmark.record(run, page.page_id, result)
benchmark.grade(run, every)
```

- `prepare(run, dataset, timeout)` makes the folder and writes `settings.json`;
- `needs(run, page, retry_failed=False)` is the outputs to ask `predict` for, and is passed to it as
  they are. `page` is a manifest row; its `outputs` say what to predict (usually `["html"]` or
  `["html", "blocks"]`), and `needs` is the part of them the page's record doesn't settle:

  | the page's record | `needs` returns |
  | --- | --- |
  | none yet | all of its `outputs` |
  | without an output, never asked (a gold that added layout tests later; one of an LLM's separate calls cut short) | that output |
  | with an output failed in a way that may not recur (a timeout, an outage, a 429 or 5xx), with `retry_failed=True` | that output |
  | with an output recorded as unsupported | nothing for it |
  | holding all of its `outputs` | nothing, so the page is skipped |

  A page has several outputs, often from separate, paid calls, so the answer is a set, not a yes or no:
  a resume, `--retry-failed` or a new kind of test asks for what is missing only. A loop that asks for
  everything every time can skip `needs`; it is what makes a loop resumable;
- `record(run, page_id, result)` writes: it merges a new result (a record from `predict`) into what
  the run has for the page, writes it and its prediction, and returns what it kept;
- `recorded(run, page_id)` reads the page's record (its calls, for an audit), or None;
- `predicted(run, page_id)` reads the page's outputs, or None: what grading reads; and
- `grade(run, pages)` grades every page of `pages` (pass the whole manifest, `data.read_manifest(dataset, manifest)[1]`,
  so a smaller loop never shrinks a run's scores), fresh, writes `scores.jsonl` and `summary.json`
  whole, and returns the summary. A page with no prediction is pending only when the run never
  attempted it (no record either); otherwise all its tests fail. A run never prepared is refused;
- `read_scores(run)` reads the run's score lines back, in file order; `[]` for a run never graded, and
  a folder that doesn't exist is refused; and
- `owed(plan, run)` is `(to predict, to grade)`: how many of the plan's pages the run will predict,
  and how many of the manifest's pages it will then grade, as `describe` shows them.

Each page's tests are read from its gold file (`page.gt_path`) when it is graded, once per process: a
gold file edited in a process that has already graded it is not read again until the process
restarts.

The folder is then exactly one `opb benchmark` writes, so either can resume or grade it.

## providers

```bash
opb providers
```
```
azure
datalab
extend
...
tesseract
openai/gpt-5.6-sol
```

An excerpt: the real list is longer, and grows with the adapters installed. The model id is an
example: any OpenRouter `org/model` id works.

What each takes, and its defaults:

```bash
opb providers datalab
```
```
datalab
option          default
──────────────────────────────────────
mode            accurate                 conversion tier; the published runs use balanced and accurate
base_url        https://www.datalab.to
poll_interval   2.0

opb benchmark --providers datalab --options '{"datalab": {"mode": "..."}}'
```

The defaults are each vendor's top tier. In your code:

```python
from omni_parse_bench import harness

harness.PROVIDERS
harness.settings_for("datalab", {"mode": "balanced"})
# {'mode': 'balanced', 'base_url': 'https://www.datalab.to', 'poll_interval': 2.0}
```

[providers.md](./providers.md) says what each adapter sends and how it maps the vendor's output to
html and blocks. A provider of your own plugs in as an adapter: a module with the five names of
`harness/contract.py`, filed with `harness.add_adapter("mine", module)`, or declared by its package under
the entry-point group `omni_parse_bench.adapters` (`[project.entry-points."omni_parse_bench.adapters"]
mine = "my_package.my_adapter"`), and then named like any other provider. Or write its predictions to a
folder and run `opb grade` on it (see [Grading your own predictions](#grading-your-own-predictions)), or
loop over `score` (see [The dataset](#the-dataset)).


## The dataset

```
manifest.parquet        one row per page: page_id, document, suite, doc_path, gt_path, outputs; any other
                        column is kept on the page as page.extra, unread
pages/<page_id>.pdf     the page that gets sent (or .png)
gold/<page_id>.json     its tests: {"tests": [...]}
```

Paths are relative to the dataset's folder and stay inside it. A gold file is named for its page,
`<page_id>.json`, in any folder; a page file may have any name, and pages may share one. A page whose
suite is null or empty is in the suite `"other"` (`data.NO_SUITE`), with any real suite of that name.

A test is a JSON object with `id`, `test_type`, `output_type` (what the type reads), `derivation`,
`tags`, `args` and `settings`. One of each type:

```json
{"id": "t1", "test_type": "present", "output_type": "html", "derivation": "authored", "tags": ["math"],
 "args": {"content": {"latex": "f(0)"}}, "settings": {}}
{"id": "t2", "test_type": "order", "output_type": "html", "derivation": "authored", "tags": ["eng"],
 "args": {"before": {"text": "May 22nd, 1914.", "max_diffs": 0},
          "after": {"text": "Theodore Roosevelt", "max_diffs": 0}}, "settings": {}}
{"id": "t3", "test_type": "repeat", "output_type": "html", "derivation": "authored", "tags": ["table"],
 "args": {"content": {"text": "$ 422,091", "max_diffs": 0}}, "settings": {"expected_count": 3}}
{"id": "t4", "test_type": "table_cell", "output_type": "html", "derivation": "authored", "tags": ["table"],
 "args": {"cell": {"text": "5%", "max_diffs": 0}, "up": {"text": "7%", "max_diffs": 0}}, "settings": {}}
{"id": "t5", "test_type": "layout_kind", "output_type": "blocks", "derivation": "authored", "tags": ["table"],
 "args": {"content": {"text": "6.00", "max_diffs": 0, "place": [[0.303, 0.533, 0.314, 0.54]]}},
 "settings": {"kind": "table"}}
```

`opb check --dataset DIR [--manifest M]` says whether a dataset is one opb can run: its manifest, that
every file it names exists, and every gold (`unit_tests.check`); the first problem is printed, naming
its row. A dataset that passes prints `{"ok": true, "manifest": ..., "pages": N, "suites": N,
"inputs": N}`, `inputs` being the distinct page files (fewer than `pages` when pages share one).

The dataset is the source of truth: a correction is an edit to a gold file, and a dropped page is
removed with its files and its manifest row. The pages' licenses are in `licenses/`.

The dataset is read by `data`, and a page's tests by the scorer, `unit_tests.gold`:

```python
data.download_dataset(dataset)  # a local copy: an hf:// dataset downloaded whole; a folder as it is
data.read_manifest(dataset, manifest="manifest.parquet")  # (folder, pages): every page of that manifest,
                                # its file and gold as full local paths
data.select(pages, ...)         # the pages to run: by suite, by id, sampled or limited
unit_tests.gold(page)           # one page's tests, from its gold file (`page.gt_path`), checked
unit_tests.check(pages)         # every page's tests, and the dataset as a whole, checked: for publishing
```

Each needs the benchmark extra, for parquet. A manifest that breaks the dataset's rules raises
`data.ManifestError`, and a test that breaks them `unit_tests.GoldError`; each names what's wrong.

```python
from omni_parse_bench import data
from omni_parse_bench.scorers import unit_tests

_, pages = data.read_manifest("dataset/")
tests = unit_tests.gold(pages[0])
pages[0]
# Page(page_id='olmo_arxiv_math-2502.15977_pg21-p1', document='olmo_arxiv_math:2502.15977',
#      suite='olmo_arxiv_math', doc_path='/abs/path/dataset/pages/olmo_arxiv_math-2502.15977_pg21-p1.pdf',
#      gt_path='/abs/path/dataset/gold/olmo_arxiv_math-2502.15977_pg21-p1.json', outputs=('html',),
#      extra={})
tests[0]
# Test(id='2502.15977_pg21_math_003', page_id='olmo_arxiv_math-2502.15977_pg21-p1', test_type='present',
#      output_type='html', derivation='upstream_olmocr', tags=('math',),
#      params=Present(content=Latex(latex='\\theta_1 + ... + \\theta_n')))
```

Grading your own model is a loop over pages:

```python
xs = []
for p in pages:
    pred = my_model(p.doc_path, p.outputs)
    tests = unit_tests.gold(p)
    xs += unit_tests.lines(unit_tests.score(pred, tests), tests, p)
summary = unit_tests.summarize(xs)
```

`p.outputs` is what to predict for the page: the outputs its tests read (`unit_tests.tests.wants`). A
page whose manifest `outputs` disagree with its gold is refused. `unit_tests.tests.read(path)` reads one
gold file.

### Grading your own predictions

Write each page's outputs to `predictions/<page_id>.json`, as `{"html": ..., "blocks": ...}` (an
output your system failed on is `null`), and grade the folder:

```bash
opb grade mine/ --unsupported blocks      # mine/predictions/<page_id>.json, one per page you predicted
```

`--unsupported` names the outputs your system can't produce, once for the folder (`--unsupported` with
none for none); their tests are `unsupported` rather than failed. The folder's first grading that
succeeds writes `mine/settings.json` with the dataset, the manifest and `unsupported`, so a later
`opb grade mine/` needs no flags, and another `--dataset` or `--manifest` is refused; a grading that
fails writes nothing. `--unsupported` is refused on a run's folder, whose adapter says it. An output a page asks for
that its prediction leaves out fails, so leaving out a hard page's output can't take it out of the
score. A page with no prediction fails, every test of it: your folder is your submission, so a page
left out is one your system didn't answer. To grade part of the dataset on purpose, pass `--suites`.
The folder gets `scores.jsonl` and `summary.json`, as a run's does. Grading says how many files in
`predictions/` are named for no page of the manifest (left out), and how many couldn't be read or hold
no output type (graded as failed); keys other than output types are ignored. A prediction is read only
under its exact name, case too, so a folder grades the same on every disk.

A run's folder is graded against the dataset and manifest its `settings.json` names, so
`opb grade runs/<run>` needs no `--dataset`; another dataset or manifest than the run's is refused.
`--suites` on a folder already graded replaces its summary of every suite, and says so.

### Exploring the tests

`opb tests` writes every test as a JSON line, with its page's suite and document:

```bash
opb tests --dataset hf://datasets/datalab-to/omni_parse_bench > tests.jsonl
```
```json
{"id": "2502.15977_pg21_math_003", "page_id": "olmo_arxiv_math-2502.15977_pg21-p1",
 "suite": "olmo_arxiv_math", "document": "olmo_arxiv_math:2502.15977", "test_type": "present",
 "output_type": "html", "derivation": "upstream_olmocr", "tags": ["math"],
 "args": {"content": {"latex": "\\theta_1 + ... + \\theta_n"}}, "settings": {}}
```

Query it with DuckDB, polars or pandas:

```sql
select suite, count(*) from 'tests.jsonl' where list_contains(tags, 'handwriting') group by 1;
```
```python
import polars as pl
tests = pl.read_ndjson("tests.jsonl", infer_schema_length=None)   # args differ by test type: read every line
```

To run only a subset, collect its page ids and pass them to `--pages`:

```bash
duckdb -noheader -list -c "select distinct page_id from 'tests.jsonl' where list_contains(tags, 'handwriting')" > hw.txt
opb benchmark --providers datalab --pages hw.txt
```

Vendors bill per page, so a subset is a set of pages. Its pages' other tests are graded too at no
cost; slice the verdicts by tag afterwards.


## Asking a question

Comparing providers on a slice of the tests takes four steps.

1. Run the providers you want to compare. Each gets its own run folder, and the command is
   resumable:

   ```bash
   opb benchmark --out runs/ --providers datalab openai/gpt-5.6-sol reducto
   ```

2. Read each run's `summary.json` for the common questions. It holds the headline and each family,
   each output type's score per test type and per tag, and the scores per suite and per derivation;
   the families, the output types and the tags carry their test and document counts, and the
   summary its document count.
   So "how does each provider do on handwriting?" is already answered there:

   ```bash
   jq '.html.per_tag.handwriting' runs/*/summary.json
   ```

3. Query `scores.jsonl` for anything finer: a mix of tags, one suite's tables, one test type on
   scans. Every run's `scores.jsonl` is one line per test, with what the test is beside its verdict
   ([What a benchmark writes](#what-a-benchmark-writes)), so a question over all the runs is one
   query on their files, with no join. With DuckDB:

   ```sql
   select provider, run, count(*) as tests, avg((result = 'pass')::int) as score
   from read_json('runs/*/scores.jsonl')
   where result in ('pass', 'fail')
     and list_contains(tags, 'handwriting') and list_contains(tags, 'table')
   group by 1, 2 order by score desc;
   ```

   pandas and polars read the same files (`pd.read_json(path, lines=True)`). Keep only `pass` and
   `fail`, as every score does: `unsupported` and `error` are left out. A run graded by an older
   version has an older line format: grade it again first (`opb benchmark ... --score-only`).

4. Give a slice to `summarize` for the benchmark's own numbers on it. A query's average is the share
   of the selected tests passed: the right number for a slice, but not the headline (the mean of the
   families' scores). `summarize` gives the headline, the families and the document counts, over the
   lines you select:

   ```python
   from pathlib import Path

   from omni_parse_bench import benchmark
   from omni_parse_bench.scorers import unit_tests

   run = benchmark.Run("datalab", {}, Path("runs/datalab-f45991d3"))
   picked = [x for x in benchmark.read_scores(run) if {"handwriting", "table"} <= set(x["tags"])]
   s = unit_tests.summarize(picked)
   s["headline"], s["families"], s["documents"]
   ```

   A slice over few documents says little, whatever its test count: check `documents`.


## What a benchmark writes

One directory per run.

```
runs/
├── datalab-296b76d9/
│   ├── settings.json
│   ├── summary.json
│   ├── records/<page_id>.json
│   ├── predictions/<page_id>.json
│   └── scores.jsonl
├── datalab-f45991d3/
└── openai__gpt-5.6-sol-86e872e5/
```

Each is named for the provider and an eight-character digest of everything it sends, which keeps
two configurations of one provider apart: `datalab-296b76d9` is balanced, `datalab-f45991d3`
accurate. The digest isn't meant to be read; `settings.json` is.

### settings.json

What the run asks, written before the first page, so an interrupted run still says what it is. What
graded it is on each score line and in `summary.json`.

```json
{"run": "datalab-296b76d9", "provider": "datalab",
 "settings": {"mode": "balanced", "base_url": "https://www.datalab.to", "poll_interval": 2.0},
 "dataset": "hf://datasets/datalab-to/omni_parse_bench", "commit": "175cc91a9df1a8d1ee2339ad652d3dce20852911",
 "timeout_s": 900, "unsupported": []}
```

- `settings` is the whole resolved configuration, not just what you passed;
- `dataset` is the dataset's repo, or a folder's path: a later invocation with another is refused;
  `commit` is the Hugging Face commit the run reads;
- `timeout_s` is the latest invocation's; each call in a record keeps its own; and
- `unsupported` is the outputs the provider can't produce (from its adapter): their tests are
  `unsupported`, not failed. Grading refuses a folder that doesn't say it.

### summary.json

The `summarize` output over every graded page (see [score](#score)), plus what the run covered
and cost:

```json
{"headline": 0.905, "families": {"...": "..."}, "documents": 2343, "html": {"...": "..."}, "blocks": {"...": "..."},
 "per_suite": {"...": "..."}, "per_derivation": {"...": "..."},
 "scorer": "0.1.1+a09ce5ecf32a", "pages": 2937, "failed": 12, "pending": 0,
 "suites": {"olmo_arxiv_math": {"pages": 180, "failed": 1, "pending": 0}, "...": "..."},
 "usd": 13.668, "credits": null}
```

- `headline` is null while any page is `pending`: a run has a headline only once it is finished;
  the other scores stand, over the pages graded so far;
- `scorer` is the package version and a digest of its scoring code, which graded it;
- `pages` is how many pages were graded, `failed` how many of them have an output missing or null
  that the system can produce, and `pending` how many of the dataset's pages the run never attempted
  (no prediction and no record); `suites` counts the three per suite; and
- `usd` and `credits` are what the vendor said the calls cost; `credits` is null when no call
  reported any.

### records/&lt;page_id&gt;.json

Everything about one page's prediction, for an audit: the record `predict` returns (outputs, errors,
calls, raw answers, settings), with the time it was captured. Grading reads only its cost. Each call keeps its timeout (`timeout_s`) and its
failure (`class`, `status`, `transient`): `--retry-failed` reads its `class` and `status`, and
`transient` says whether the call was tried again within itself. The raw answers are what
`opb reparse` reads. A record from before this version may also hold `page_sha256`; it is ignored.

### predictions/&lt;page_id&gt;.json

The outputs alone, `{"html": ..., "blocks": ...}`, the same as `record["outputs"]`: all grading reads.
A folder of these, made by anything, is graded the same way (`opb grade`).

### scores.jsonl

One line per test, in manifest order: its verdict, what the test is, and the stamps of what graded it.

```json
{"run": "datalab-f45991d3", "provider": "datalab", "page_id": "olmo_arxiv_math-2502.15977_pg21-p1",
 "suite": "olmo_arxiv_math", "document": "olmo_arxiv_math:2502.15977",
 "test_id": "2502.15977_pg21_math_003", "test_type": "present", "output_type": "html",
 "derivation": "upstream_olmocr", "tags": ["math"], "result": "pass", "why": "",
 "scorer": "0.2.0+f5c5ce802b77"}
```

- `run` and `provider` name the run (its folder) and its provider; `settings.json` has the rest;
- `page_id` to `tags` say what the test is (`opb tests` writes the same, its id as `id`);
- `result` is `pass`, `fail`, `unsupported` or `error`, and `why` says what went wrong; and
- `scorer` says which scoring code graded the line.
