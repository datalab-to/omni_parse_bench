# API

The public functions and commands of omni-parse-bench. It is built on
[omni-bench-core](https://github.com/datalab-to/omni-bench-core), which runs the loop: planning, predicting,
resuming and grading. This package adds what is particular to parsing: the rows (`data.Page`), the task
(`task.Parse`), the adapters (`harness`) and the scorer (`scorers.unit_tests`).

Contents:

1. [Run](#run): one system on a dataset, from a config;
2. [Resume](#resume): a run that stopped part way;
3. [Grade](#grade): a run again, or predictions of your own;
4. [Score](#score): one page's outputs against its tests;
5. [Predict](#predict): one page through one system;
6. [Adapters](#adapters): the systems, and your own;
7. [The dataset](#the-dataset): its folder, its manifest and its tests;
8. [Your own scorer](#your-own-scorer): grading another way; and
9. [What a run writes](#what-a-run-writes): the files, and slicing them.

## Run

```bash
opb init datalab > datalab.yaml                                   # a config at the system's defaults, on our dataset
opb run --config datalab.yaml --set rows.sample=20 --out runs/    # predict, then grade: a new run
opb run --config datalab.yaml --set 'rows.only=[<page_id>, <page_id>]'
opb run --config datalab.yaml --set dataset=my-dataset/           # another dataset
opb run --config runs/<run>/config.yaml                           # the same question again, as a new run
```

A config has every key written out, and nothing has a default:

- `dataset`: a folder, or `hf://datasets/<repo>[@<revision>]`;
- `manifest`: a manifest inside the dataset;
- `scorers`: `unit_tests: {}`;
- `rows`: `sample` N evenly spaced, `limit` the first N (0 for every page), or `only` these ids;
- `timeout`: seconds each page may take;
- `workers`: pages in flight at once, 0 for the system's default; and
- `system`: one system and every option it has.

`--set path=value` changes one value the file has, read as YAML. A path the file hasn't is refused, with the
nearest one it has. A missing key, an unknown one or a value of the wrong kind is refused at its key.

`opb run` shows the plan and asks before calling any system; `-y`, or no terminal, skips the question. Any answer
but yes prints "not run" and exits 1. It shows a live table of the run's progress, and prints the grading as JSON,
`{"run", "cost", "scorers"}`, whose `run` is the run folder's name.

A run works in three stages:

1. plan: checks the options, the keys, every page and every gold before any call;
2. predict: calls the system on every page the run has no record of; and
3. grade: grades the run, when it is finished.

Each page asks for the outputs its tests read (its manifest row's `outputs`), and a system is asked only for those
it can produce (`SUPPORTS`). A page that wants none of them isn't sent; its tests fail as "no <output> output",
which doesn't lower coverage.

The dataset is downloaded whole the first time (about 1.5 GB) into the Hugging Face cache, even for a few pages.
Set `HF_TOKEN` (or run `hf auth login`) to download faster.

In Python:

```python
from omni_parse_bench import benchmark, harness

if __name__ == "__main__":
    b = benchmark.default()                                  # or benchmark.default("my-dataset/", manifest)
    g = b.run(harness.system("datalab", {"mode": "accurate"}), out="runs", sample=20)
```

`run` takes one adapter, and `sample`, `limit` and `only`, `timeout` and `workers`, as a config does.

Code that runs or grades a benchmark goes under `if __name__ == "__main__":`. A scorer or an executor that works in
several processes imports your script again in each one on macOS and Windows, and the guard keeps that from
starting the run a second time.

Some commands and flags from before 1.0 still work, and each prints what replaced it: `opb providers`
(`opb systems`), `opb reparse` (`opb reread`), and `--provider` and `--wants` on `opb predict`.

## Resume

```bash
opb resume runs/<run>                                       # continue where it stopped
opb resume runs/<run> --retry-failed                        # also ask again for timeouts, outages, 429s and 5xx
opb resume runs/<run> --retry-failed --set timeout=1800     # more time per page
opb reread runs/<run>                                       # read saved answers again after a fix to `parse`
```

A run folder answers one question: the system and its options (`served` included), the dataset, the manifest,
the task and `rows`. A resume reads the run's own `config.yaml`, and asks only for the pages with no record.
`--set` may change `timeout` and `workers`, which aren't part of the question; a change to anything else is
refused, naming the keys that differ. A model server's address, `base_url`, may change between attempts.

A failed page has a record, so it is asked again only with `--retry-failed`, and only when its failure may not
recur: a timeout, a system that couldn't be reached, a 429 or a 5xx. A refusal or an answer that couldn't be read
stays failed.

`opb reread` reads every saved answer of a run again, with no call, after a fix to a `parse` that gave wrong
outputs without raising. It rebuilds the system from the run's settings.json. Grade the run again afterwards.

In Python, `b.run(system, out="runs", resume="<run>", retry_failed=True)` and `b.reread(folder, system)`.

## Grade

```bash
opb grade runs/<run>                                # the dataset and manifest its settings.json names
opb grade mine/ --dataset my-dataset/               # your own predictions/<page_id>.json
opb grade runs/<run> --partial                      # an unfinished run: what's missing counts as 0
```

```python
if __name__ == "__main__":
    benchmark.default().grade("runs/<run>")
    benchmark.default("my-dataset/").grade("mine/", partial=True)
```

A run is graded over the pages it chose, on every test of those pages, and only when it is finished: every page
has an answer or a recorded failure. Otherwise grading refuses and names the pages. `--partial` counts them as 0,
and the summary counts them under `partial`.

For your own predictions, write one file per page, `predictions/<page_id>.json`, each
`{"pages": [{"html": ..., "blocks": [...]}]}`, as a system's output is. Such a folder is graded over the whole
manifest; a page whose file lacks an output fails that output's tests. Without `--dataset`, it is graded against
our dataset. `--manifest` picks another manifest inside the dataset.

A prediction that isn't `{"pages": [one object of outputs]}` is the system's failure: the page counts 0. An
output of the wrong shape inside it fails only that output's tests.

The summary's top `headline` is `scored.headline` times `coverage`, the share of pages that didn't fail, so a page
that failed counts as 0. Under `scored`, the headline and the families are over the scored pages only.

## Score

```python
unit_tests.score(pred, tests) -> [Verdict(id, result, why)]   # pred: one page's {"html": ..., "blocks": [...]}
unit_tests.lines(verdicts, tests, page) -> [test line]        # each verdict beside its page and its test
unit_tests.summarize(lines) -> {"headline", "families"}       # any number of test lines
unit_tests.UnitTests()                                        # the same, as an omni-bench-core scorer
```

```bash
opb score --pred outputs.json --gold gold/<page_id>.json     # outputs.json: one page's {"html": ..., "blocks": [...]}
```

A verdict is `pass` or `fail`, with `why`. A test whose output is missing or malformed fails. A summary holds
`headline`, the mean of the families' scores, and `families`, always in the order text, tables, layout: each
family's `score` (the share of its tests passed), `tests` and `documents` (the source documents its tests are
from). `summarize` of a slice of lines (one tag, one suite) is that slice's summary.

## Predict

```python
from pathlib import Path

from omni_parse_bench import harness
from omni_parse_bench.scorers import unit_tests

datalab = harness.system("datalab", {"mode": "accurate"})
record = harness.predict(datalab, harness.Input(Path("pages/<page_id>.pdf"), frozenset({"html", "blocks"})))
record["output"]                             # {"pages": [{"html": ..., "blocks": [...]}]}: one entry per page

unit_tests.score(record["output"]["pages"][0], unit_tests.tests.read("gold/<page_id>.json"))
```

```bash
opb predict --system datalab --page pages/<page_id>.pdf [--outputs html] [--options JSON] [--timeout 900] [--raw]
```

`harness.predict` sends one page under the rules a run uses: one time budget, transient failures retried, other
failures recorded as the page's answer. It returns the record ([What a run writes](#what-a-run-writes)). A
missing key is refused before the call.

`opb predict` prints the record as JSON, without the raw answers unless `--raw`, and exits 1 when the page
failed. A page file has no manifest row, so it asks for every output the system supports, or for `--outputs`:
html alone tries a page with fewer calls. `--options` takes the system's options, or the same keyed by the
system's name.

## Adapters

```bash
opb systems              # every system, the outputs it can produce, and its key
opb systems datalab      # one system's options, their defaults, and its environment
```

```python
harness.ADAPTERS                       # name -> adapter class
harness.system(name, options)          # an adapter at its options, checked; a model id is the LLM adapter
```

### Your own adapter

Subclass `harness.Parser` as a frozen dataclass whose fields are its options. It is written for one page:

- `SUPPORTS`: the outputs it can produce, `html` and `blocks`;
- `keys`: the environment variables it needs, checked before any call;
- `requests(wants)`: the calls that produce `wants`, a non-empty subset of `SUPPORTS`;
- `send(page, request, *, timeout)`: makes one call and returns its answer as received; and
- `parse(raw, request)`: the outputs in one answer, and why any is missing.

`Parser` turns these into a document's call: it splits a PDF into its pages, makes each page's requests in order
within the document's one time budget, and keeps each answer whole. `send` runs on several threads at once, so a
library that isn't thread-safe needs a lock (render a PDF with `raster`, which holds pdfium's). A model you serve
subclasses `harness.Served`: its `served` option names the weights and their revision, and before any call the
server must say the same at its `/served` route.

Give an instance to `benchmark.default().run(...)`, or declare the class under the entry-point group
`omni_parse_bench.adapters` so a config finds it by name.

A page counts 0 only when code raises `SystemFailed` on purpose. Any other exception stops the run, and resuming
after the fix costs nothing for the pages already answered. So:

- in `send`, raise `harness.errors.SystemFailed` for a refusal, an error status or an unusable answer, and read
  the system's fields (a job id, a status) inside `omni_bench_core.adapter.reading`, which turns a `ValueError`,
  `KeyError`, `IndexError`, `TypeError` or `AttributeError` into a `SystemFailed`;
- in `parse`, raise `SystemFailed` (or read inside `reading`) when the answer holds no usable page: the page is
  recorded as `Unreadable` and keeps its raw answer. For one output it can't read, leave it out and give the
  reason in the second value, so only that output's tests fail;
- a model server that refuses the connection stops the run, with a note saying how to start it; and
- anything else is a bug: the run stops, and a bug in `parse` keeps the answer unread, so resuming after the fix
  reads it with no call.

[`providers.md`](./providers.md) describes each adapter, and `harness.Parser`'s docstring has the rest.

## The dataset

```
my-dataset/
  manifest.parquet        one row per page: page_id, document, suite, doc_path, gt_path, outputs
  pages/<page_id>.pdf     the page that is sent (or .png)
  gold/<page_id>.json     its tests: {"tests": [...]}
```

Paths are relative to the dataset's folder and stay inside it. A gold file is named for its page, `<page_id>.json`,
in any folder; pages may share one page file. Any other manifest column is kept on the page as `page.extra`,
unread.

A test is a JSON object with `id`, `test_type`, `output_type`, `derivation`, `tags`, `args` and `settings`. A
test's `id` is unique across its dataset, and every page has at least one test. One of each type:

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

```python
data.read_manifest(dataset, manifest="manifest.parquet")  # (folder, pages): every page, with full local paths
unit_tests.gold(page)                                    # one page's tests, checked
unit_tests.check(pages)                                  # every page's tests, and the dataset as a whole
unit_tests.tests.read(path)                              # one gold file
```

None needs the harness; an `hf://` dataset needs the Hugging Face client (`[benchmark]`). A manifest or a test
that breaks the dataset's rules is a `ValueError` naming what's wrong. A page's `outputs` must be what its tests
read.

Grading your own model is a loop over pages:

```python
from omni_parse_bench import data
from omni_parse_bench.scorers import unit_tests

_, pages = data.read_manifest("my-dataset/")
xs = []
for p in pages:
    pred = my_model(p.doc_path, p.outputs)          # one page's {"html": ..., "blocks": [...]}
    tests = unit_tests.gold(p)
    xs += unit_tests.lines(unit_tests.score(pred, tests), tests, p)
unit_tests.summarize(xs)
```

```bash
opb check --dataset my-dataset/ [--manifest M]                  # is it a dataset opb can run? no call
opb tests --dataset my-dataset/ [--manifest M] > tests.jsonl    # every test as a JSON line
```

`opb check` stops at the first problem, naming its row. A dataset that passes prints
`{"ok": true, "manifest", "pages", "suites", "inputs"}`, `inputs` being the distinct page files. `opb tests` writes
every test with its page's `page_id`, `suite` and `document`: a flat table to query with DuckDB, polars or pandas.

## Your own scorer

A scorer is a frozen dataclass with `gold(row)`, `score(pred, gold)` and `summarize(lines)`. To grade with one
beside `UnitTests`, build the benchmark directly with `omni_bench_core.benchmark.Benchmark(task.Parse(), dataset,
[unit_tests.UnitTests(), Mine()])`. Scorers aren't part of a run's question, so grading a run you already have
adds the new scorer's folder beside `unit_tests/`. omni-bench-core's
[overview](https://github.com/datalab-to/omni-bench-core/blob/main/OVERVIEW.md#scorer) explains scorers.

## What a run writes

```
runs/datalab-20261021-160012-3f9a/       <system>-<YYYYMMDD-HHMMSS>-<4 hex>
  config.yaml                            the config as run, every --set applied and every option written out
  settings.json                          the question it answers, and the launch
  server.json                            for a model you serve: what its server said it serves, at each launch
  records/<page_id>.json                 what the system returned for each page
  predictions/<page_id>.json             each page's outputs alone; all grading reads
  unit_tests/
    summary.json                         the grade
    scores.jsonl                         one line per page: id, status, row.document, tests, passed, per_family
    details/<page_id>.jsonl              one line per test: page_id, suite, document, test_id, test_type,
                                         output_type, derivation, tags, result and why
```

`settings.json` is written before the first call. A resume is checked against it, and you don't edit it. It holds
`run`, `system`, `options`, `dataset`, `manifest`, `task` (`"parse"`), `rows`, `dataset_commit` (for an `hf://`
dataset), `timeout_s`, `located` (where a model you serve was, as of the latest launch), `started` and `launch`.

A record holds `system`, `options`, `package`, `output` (null on a failure), `raw` (each call's answer, so a
fixed `parse` can read it again), `sent`, `error` (its `type`, `status`, `transient`, `message` and `traceback`),
`cost`, `job_id`, `timeout_s`, `captured_at`, and `unread: true` for an answer a bug in `parse` left unread.

### A slice of the benchmark

The summary holds the headline and the families only. Every other breakdown (by tag, test type, suite,
derivation) comes from the files: each test's verdict is in `details/<page_id>.jsonl`. With DuckDB, the
handwriting tests of every run:

```sql
select regexp_extract(filename, '([^/]+)/unit_tests/details/', 1) as run,
       avg((result = 'pass')::int) as score, count(*) as tests
from read_json('runs/**/unit_tests/details/*.jsonl', filename = true)
where list_contains(tags, 'handwriting') group by 1 order by score desc;
```

and one run's pass rate per suite:

```sql
select suite, avg((result = 'pass')::int) as score, count(*) as tests
from read_json('runs/<run>/unit_tests/details/*.jsonl')
group by 1 order by 1;
```

`unit_tests.summarize` gives the benchmark's own numbers on a slice:

```python
import glob, json
from omni_parse_bench.scorers import unit_tests

lines = [json.loads(x) for f in glob.glob("runs/<run>/unit_tests/details/*.jsonl") for x in open(f)]
unit_tests.summarize([x for x in lines if x["suite"] == "tables"])
```

A failed page has no details, so a slice leaves it out: its headline has no coverage factor, and can be higher
than the run's.
