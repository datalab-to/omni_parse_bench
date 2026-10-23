# API

This is the public API of omni-parse-bench. It is built on [omni-bench-core](https://github.com/datalab-to/omni-bench-core),
which runs the loop: planning, predicting, resuming and grading. This package adds what is opb's: the parse
task, its adapters, and the unit-test scorer. The CLI is a thin wrapper.

1. [Run the benchmark](#run-the-benchmark): every page, one system per run, resumable;
2. [Score](#score): one page's outputs against its tests;
3. [Adapters](#adapters): what you can run, what each takes, and writing one;
4. [The dataset](#the-dataset): loading it, and its tests;
5. [Grading](#grading): a run, or your own predictions; and
6. [What a run writes](#what-a-run-writes), and asking questions of it.

What happens in each case (a failed page, a missing key, a server that isn't running, an unfinished run)
is the core's three rules, the same for every benchmark built on it: see the table in
[omni-bench-core's "The rules"](https://github.com/datalab-to/omni-bench-core/blob/main/OVERVIEW.md#the-rules).
The one that decides how a page counts:

    A page counts 0 only when code says, on purpose, that the system failed, by raising
    `omni_bench_core.errors.SystemFailed`. Any other exception stops the run and is raised as it is.

The failures a record can hold are `SystemFailed` and its kinds: `SystemTimeout`, `SystemUnreachable` and
`Unreadable` (an answer `read` said it can't read). Each record's `error` holds its `type`, `status`,
`transient`, `message` and `traceback`.


## Run the benchmark

```python
from omni_parse_bench import benchmark, harness
from omni_parse_bench.harness.providers.datalab import Datalab

if __name__ == "__main__":
    b = benchmark.default(dataset="hf://datasets/datalab-to/omni_parse_bench")
    g = b.run(Datalab(mode="accurate"), out="runs", sample=20)       # plan, predict, grade: the grading
    b.run(harness.system("openai/gpt-5.6-sol"), out="runs", sample=20)  # another system: another run
    b.grade(f"runs/{g['run']}")                                      # grade a run again, with no call
```

Code that runs a benchmark goes under `if __name__ == "__main__":`. A scorer or an executor that works in
several processes starts each one by importing your script again (on macOS and Windows), and the guard
keeps that import from starting the run a second time.

`benchmark.default(dataset, manifest)` is an omni-bench-core `Benchmark`: the `Parse` task, the dataset,
and `UnitTests()`. Each page asks for the outputs its tests read (its manifest row's `outputs`), and a
system is asked only for those it can produce (`SUPPORTS`). A page that wants none of them is not sent;
its tests fail as "no <output> output", which doesn't lower coverage. Every test is graded, so a system
that draws no layout blocks scores 0 on the layout family ([README](https://github.com/datalab-to/omni_parse_bench/blob/main/README.md#grade)
says how to read its results). `Benchmark.plan` refuses, before any call, a system whose key isn't set
(`Adapter.keys`).

`Benchmark.plan` takes `limit`, `sample` and `only` (page ids) to choose pages, `timeout` (seconds
per page), `workers` (pages at once; 0, the default, for the adapter's own) and `retry_failed`. `sample` takes pages evenly
spaced over the manifest, and `limit` takes the first ones; give one or the other. A run's folder is named for the whole
question: the system and its options, the dataset, the manifest, the task and the pages chosen, then a run id. Every launch is a new run in a new folder;
`resume=<a run's name>` continues that run instead, for the same question only: a page is predicted only when its run
has no record of it, and an answer is never paid for twice.

A run is one system: `Benchmark.plan` and `Benchmark.run` take one adapter, and refuse a list. To compare
systems, or settings of one system, run each with the same choice of pages (`sample`, `limit`,
`only`), so every run is graded on the same pages. `Benchmark.run` grades the run once it is predicted, and
returns the grading: `run` (the run folder's name), `cost` and `scorers`. A run that stops part way (a
missing key, an account that can't pay, a model server that isn't running, a bug in an adapter, Ctrl-C)
isn't graded: resume it (`resume=`, `--resume`) to finish it. A bug in an adapter's `parse` stops the run with
the answer kept, unread (`"unread": true` in its record); resuming after the fix reads it with no
call. `Benchmark.reread(folder, system)` reads every saved answer of a run again, with no call, after a fix
to a `parse` that gave wrong outputs without raising; `opb reread RUN_DIR` does the same from the command
line, rebuilding the system from the run's `settings.json`, and reports a `parse` that still raises as a
bug. Grade the run again afterwards.

The dataset is downloaded whole the first time (about 1.5 GB, 5,903 files), into the Hugging Face cache,
even for a few pages. Set `HF_TOKEN` (or run `hf auth login`) to download faster and avoid the Hub's rate
limits.

From the command line:

```bash
opb init datalab > datalab.yaml                     # a config: one run, every key written out
opb init openai/gpt-5.6-sol > gpt.yaml
opb run --config datalab.yaml --set system.datalab.mode=accurate --set rows.sample=20
opb run --config gpt.yaml --set rows.sample=20       # the same pages: the two runs compare
opb run --config runs/<run>/config.yaml             # the same question again, as a new run
```

A run is one config, omni-bench-core's (its `config` module): `dataset`, `manifest`, `scorers`, `rows`
(`sample` N evenly spaced, `limit` the first N, 0 for every page, or `only` these ids), `timeout`, `workers`
and `system`, one system and every option it has. Nothing has a default and nothing comes from another file,
so the file says the whole run; a missing key, an unknown one or a value of the wrong kind is refused at its
key. `opb init <system>` writes one with every option at its default (`--dataset` and `--manifest` for another
dataset). `--set path=value` changes one value the file has, read as YAML; a path it hasn't is refused, with the
nearest one it has. The run folder keeps the config, every `--set` applied, as `config.yaml`.

`opb run` also takes `--out`, `--resume RUN` and `--retry-failed` (with `--resume`). It shows the plan and asks
before calling a system, unless given `-y` or run with no terminal; any answer but yes (Ctrl-D too) prints "not
run" and exits 1. It then shows a live table of the run's progress, and prints its grading as JSON. `opb
--version` prints the version.

Some flags from before 1.0 still work, and each prints what replaced it: `opb providers` (`opb systems`), `opb
reparse` (`opb reread`), `--provider` (`--system`) and `--wants` (`--outputs`) on `opb predict`. `--outputs` on
`opb grade` and `opb score`, and `--unsupported`, are accepted and ignored, with a warning: each page asks for
the outputs its tests read, and every test is graded.


## Score

```python
unit_tests.score(pred, tests) -> [Verdict(id, result, why)]   # pred: {"html": ..., "blocks": [...]}
unit_tests.lines(verdicts, tests, page) -> [test line]        # each verdict beside its page and its test
unit_tests.summarize(lines) -> summary                        # any number of test lines
unit_tests.UnitTests()                                        # the same, as an omni-bench-core Scorer
```

A verdict is `pass` or `fail`. A test whose output is missing or malformed fails. `opb score --pred
outputs.json --gold gold/<page_id>.json` prints one page's verdicts, one per test.

The summary holds `headline`, the mean of the families' scores, and `families`, always in the order
text, tables, layout: each family's `score` (the share of its tests passed), `tests` and `documents` (the source documents its
tests are from). `summarize` of a slice of test lines (one tag, one suite) is that slice's summary. In a
benchmark's summary, the scorer's headline (with `headline_is`, "the mean of the families' scores") and
families sit under `scored`, over the scored pages only. A page whose call failed counts as 0 in the top
headline, `scored.headline` times the share of pages that didn't fail (`coverage`), so a run where every
page failed has headline 0 and `scored` null.


## Adapters

```bash
opb systems              # every system, the outputs it can produce, and its key
opb systems datalab      # one system's options, their defaults and what each does, and its environment
opb predict --system datalab --page pages/<page_id>.pdf [--outputs html] [--options JSON] [--raw]
opb reread runs/datalab-1a2b3c4d     # read a run's saved answers again after a fix to `parse`; no call
```

`opb predict` sends one page through one system and prints its record as JSON (`omni_bench_core.adapter.predict`):
the outputs, the error if the page failed, what was sent, and the cost. The raw answers are left out unless
`--raw`. It exits 1 when the page failed. A page file has no manifest row, so it asks for every output
the system supports, or for `--outputs`: asking for html alone tries a page with fewer calls (the LLM
adapter makes one call per output). An adapter that crashes is reported as a bug, naming its package. `--options` takes the system's options, `{"mode": "fast"}`, or the same keyed by the system's name. The keys each system needs are in the
[README's table](https://github.com/datalab-to/omni_parse_bench/blob/main/README.md#run-the-benchmark).

```python
harness.ADAPTERS                       # name -> adapter class
harness.system(name, options)          # an adapter at its options, checked; a model id is the LLM adapter
```

An adapter is a `harness.Parser`: a frozen dataclass whose fields are its options, with `SUPPORTS` (the
outputs it can produce), `keys` (the environment variables it needs, checked by the core before any call, in
a run and in `opb predict`), `requests(wants)`, `send(page, request, *, timeout)` and `parse(raw, request)`.
`requests` is never given an empty set: a page that wants nothing the system supports is not sent. `send` is
called from `workers` threads at once, so a library that isn't thread-safe (pdfium is one) needs a lock. Its
docstring says how to write one, and
[providers.md](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/providers.md) describes each.
An adapter of your own is declared by its package under the entry-point group `omni_parse_bench.adapters`,
pointing at its class.

`send` and `parse` follow the one rule:

- `send` raises `harness.errors.SystemFailed` for a refusal, an error status or an unusable answer, and
  reads what the system sent back (a job id, a status) inside `omni_bench_core.adapter.reading`, which
  turns a `ValueError`, `KeyError`, `IndexError`, `TypeError` or `AttributeError` inside into
  `SystemFailed`;
- `parse` raises `SystemFailed` when the answer holds no usable page, and reads the system's own
  structures inside `reading`: the page is recorded as `Unreadable`, which counts 0, says where it was
  raised and keeps the raw answer. An output it can't read (malformed blocks) is left out, with its reason
  in its second value, so only that output's tests fail; and
- anything else either raises is a bug, and stops the run. A bug in `parse` keeps the answer unread, and
  resuming the run after the fix reads it with no call.

`harness.errors.SystemFailed` and its kinds are the core's own classes, which `reading` raises too. A
failed call's reply goes in the error's `body`, which the record keeps as `raw`. A
model server that refuses the connection (nothing listens at `base_url`) stops the run instead of failing
every page: the connection error is raised as it is, with a note saying how to start the server
(`harness.errors.no_server`).


## The dataset

```
manifest.parquet        one row per page: page_id, document, suite, doc_path, gt_path, outputs; any other
                        column is kept on the page as page.extra, unread
pages/<page_id>.pdf     the page that gets sent (or .png)
gold/<page_id>.json     its tests: {"tests": [...]}
```

Paths are relative to the dataset's folder and stay inside it. A gold file is named for its page,
`<page_id>.json`, in any folder; a page file may have any name, and pages may share one. A page's suite,
where it comes from, is a non-empty string. It is opb's own column: omni-bench-core doesn't read it.

A test is a JSON object with `id`, `test_type`, `output_type` (what the type reads), `derivation`,
`tags`, `args` and `settings`. A test's `id` is unique across its dataset, and every page has at least
one test (`unit_tests.check` checks both). One of each type:

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

The dataset is the source of truth: a correction is an edit to a gold file, and a dropped page is
removed with its files and its manifest row. The pages' licenses are in `licenses/`.

The dataset is read by `data`, and a page's tests by the scorer, `unit_tests.gold`:

```python
data.read_manifest(dataset, manifest="manifest.parquet")  # (folder, pages): every page of that manifest,
                                # its file and gold as full local paths
unit_tests.gold(page)           # one page's tests, from its gold file (`page.gt_path`), checked
unit_tests.check(pages)         # every page's tests, and the dataset as a whole, checked: for publishing
```

None needs the harness; an `hf://` dataset needs the Hugging Face client (`[benchmark]`). A manifest that breaks the dataset's rules raises
a `ValueError`, and so does a test that breaks them; each names what's wrong and the fix.

```python
from omni_parse_bench import data
from omni_parse_bench.scorers import unit_tests

_, pages = data.read_manifest("dataset/")
tests = unit_tests.gold(pages[0])
pages[0]
# Page(page_id='olmo_arxiv_math-2502.15977_pg21-p1', document='olmo_arxiv_math:2502.15977',
#      suite='olmo_arxiv_math',
#      doc_path=PosixPath('/abs/path/dataset/pages/olmo_arxiv_math-2502.15977_pg21-p1.pdf'),
#      gt_path=PosixPath('/abs/path/dataset/gold/olmo_arxiv_math-2502.15977_pg21-p1.json'), outputs=('html',),
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

Two commands work on a dataset as a whole:

```bash
opb check --dataset <folder or hf://...> [--manifest M]
opb tests --dataset <folder or hf://...> [--manifest M] > tests.jsonl
```

`opb check` says whether a dataset is one opb can run (`Benchmark.check`): its manifest, that every page
file it names exists, and every gold (`unit_tests.check`). The first problem is printed, naming its row. A
dataset that passes prints `{"ok": true, "manifest": ..., "pages": N, "suites": N, "inputs": N}`, `inputs`
being the distinct page files (fewer than `pages` when pages share one).

`opb tests` writes every test as a JSON line, with its page's `page_id`, `suite` and `document`: a flat table
to query with DuckDB, polars or pandas. To run only some pages, collect their ids into the config's
`rows.only`.


## Grading

```bash
opb grade runs/datalab-1a2b3c4d [--partial]
opb grade mine/ [--dataset ...] [--manifest ...] [--partial]
```

```python
if __name__ == "__main__":
    benchmark.default().grade("mine/")
    benchmark.default().grade("runs/datalab-1a2b3c4d", partial=True)
```

A run is graded over the pages it chose (its `settings.json`), on every test of those pages. Its dataset
and manifest come from there too.

`UnitTests.prediction` reads each page's prediction. Under the one rule, a prediction that isn't an object
of outputs is the system's failure: it raises `SystemFailed`, the page counts 0, and its line of
`scores.jsonl` has the error and its `traceback`. An output of the wrong shape inside it fails only that
output's tests. Anything else `prediction` raises is a bug in the scorer, and stops grading.

For your own predictions, put your system's outputs in a folder, one file per page,
`predictions/<page_id>.json`, each `{"pages": [{"html": ..., "blocks": [...]}]}`, as a system's output is. Such a folder is graded over the whole
manifest, on every test; a page whose file lacks an output fails that output's tests. Grading writes
nothing into it but the scorer's results. A folder none of whose files names a page is refused.

Grading reports only a finished run. A page with no answer and no recorded failure (never predicted, or
with no file in a folder of your own) makes grading refuse, naming the pages. Finish them (run the same
`opb run` command again, or add the files), or grade with `--partial` (`partial=True`): those pages count
as 0, and the summary counts them, `"partial": {"no_answer": 7, "not_scored": 0, "e.g.": [...]}`; each is a
failed line in scores.jsonl.

To grade another way, write your own scorer and pass it to `omni_bench_core.benchmark.Benchmark` beside
`UnitTests`: [omni-bench-core's OVERVIEW](https://github.com/datalab-to/omni-bench-core/blob/main/OVERVIEW.md#scorer) shows how.


## What a run writes

A run is one system at one setting, on one question, in its own folder under `out`, named for the system
and a digest of its options and the question. omni-bench-core writes it:

```
runs/datalab-1a2b3c4d/
  settings.json                 the system, its options, the dataset, its commit, the manifest, the task,
                                the pages chosen, and the timeout
  records/<page_id>.json        what each page's calls returned: the outputs, the raw answers, the error
                                with its traceback, the cost, and the adapter's package and version; and
                                `"unread": true` for an answer a bug in `parse` left unread
  predictions/<page_id>.json    each page's outputs alone, which is all that grading reads
  unit_tests-<digest>/          the scorer's results
    scores.jsonl                one line per page: id, status, row.document, tests, passed and
                                per_family; or a failed page's error, with a traceback when the scorer
                                said the prediction is unusable
    summary.json                the summary: scorer, options, run, headline, headline_is, rows, failed,
                                coverage, partial when graded with --partial, and scored: the headline
                                and families over the scored pages
    details/<page_id>.jsonl     one line per test, a test line (`unit_tests.lines`): page_id, suite,
                                document, test_id, test_type, output_type, derivation, tags, result and why
```

The page's source document is in its line's `row.document`, not at the top level.

### A slice of the benchmark

The summary holds the headline and the families only. Every other breakdown (by tag, test type, suite,
derivation, output type) is computed from the files: each test's verdict is in `details/<page_id>.jsonl`,
beside its page's id, suite and document, and `opb tests` gives each test's args and settings. With DuckDB,
the handwriting tests of every run:

```sql
select regexp_extract(filename, '([^/]+)/unit_tests/details/', 1) as run,
       avg((result = 'pass')::int) as score, count(*) as tests
from read_json('runs/**/unit_tests/details/*.jsonl', filename = true)
where list_contains(tags, 'handwriting') group by 1 order by score desc;
```

and one run's pass rate per suite:

```sql
select suite, avg((result = 'pass')::int) as score, count(*) as tests
from read_json('runs/datalab-1a2b3c4d/unit_tests/details/*.jsonl')
group by 1 order by 1;
```

`unit_tests.summarize` gives the benchmark's own numbers (the headline and the families) on a slice: give
it the details lines you select, or test lines you made (`unit_tests.lines`):

```python
import glob, json
from omni_parse_bench.scorers import unit_tests

lines = [json.loads(x) for f in glob.glob("runs/datalab-1a2b3c4d/unit_tests/details/*.jsonl")
         for x in open(f)]
unit_tests.summarize([x for x in lines if x["suite"] == "tables"])
```

A slice built from details leaves out the pages that failed, because a failed page has no details. So it
has no coverage factor, and its headline can be higher than the run's headline, which counts each failed
page as 0.
