# API

This is the public API of omni-parse-bench. It is built on [omni-bench-core](https://github.com/datalab-to/omni-bench),
which runs the loop: planning, predicting, resuming and grading. This package adds what is opb's: the parse
task, its adapters, and the unit-test scorer. The CLI is a thin wrapper.

1. [Run the benchmark](#run-the-benchmark): every page, every provider, resumable;
2. [Score](#score): one page's outputs against its tests;
3. [Adapters](#adapters): what you can run, what each takes, and writing one;
4. [The dataset](#the-dataset): loading it, and its tests;
5. [Grading your own predictions](#grading-your-own-predictions); and
6. [What a run writes](#what-a-run-writes), and asking questions of it.


## Run the benchmark

```python
from omni_parse_bench import benchmark, harness

b = benchmark.default(dataset="hf://datasets/datalab-to/omni_parse_bench", outputs=("blocks", "html"))
systems = [harness.system("datalab", {"mode": "balanced"}), harness.system("openai/gpt-5.6-sol")]
b.run(systems, out="runs", sample=20)      # plan, predict, grade; returns each run's grading
b.grade("runs/datalab-f45991d3")           # grade a run again, with no call
```

`benchmark.default(dataset, manifest, outputs)` is an omni-bench-core `Benchmark`: the `Parse` task, the
dataset, and `UnitTests(outputs)`. `outputs` is what is asked for and graded: a system that draws no
layout blocks is graded with `outputs=("html",)`. `Benchmark.plan` refuses, before any call, a system that
can't produce an output being graded (`Parse.check`), because its tests would all fail.

`Benchmark.plan` takes `suites`, `limit`, `sample` and `only` (page ids) to choose pages, `timeout` (seconds
per page), `workers` (pages at once per adapter) and `retry_failed`. A page is predicted only when its run
has no record of it, so a stopped run resumes and an answer is never paid for twice. `Benchmark.reread(run)`
reads a run's saved answers again after a fix to an adapter's `parse`, with no call.

From the command line:

```bash
opb run --providers datalab openai/gpt-5.6-sol --sample 20
opb run --providers tesseract --outputs html --limit 5
opb run --providers datalab --options '{"datalab": [{"mode": "balanced"}, {"mode": "accurate"}]}'
```

`opb run` takes `--dataset`, `--manifest`, `--out`, `--outputs`, `--suites`, `--limit`, `--sample`, `--pages`
(a file of page ids), `--timeout`, `--workers` and `--retry-failed`. It shows the plan and asks before
calling a system, unless given `-y` or run with no terminal. It prints each run's grading as JSON.


## Score

```python
unit_tests.score(pred, tests) -> [Verdict(id, result, why)]   # pred: {"html": ..., "blocks": [...]}
unit_tests.lines(verdicts, tests, page) -> [test line]        # each verdict beside its page and its test
unit_tests.summarize(lines) -> summary                        # any number of test lines
unit_tests.UnitTests(outputs=...)                             # the same, as an omni-bench-core Scorer
```

A verdict is `pass` or `fail`. A test whose output is missing or malformed fails. `opb score --pred
outputs.json --gold gold/<page_id>.json [--outputs html]` prints one page's verdicts.

The summary's `headline` is the mean of the families' scores (text, tables, layout). In a benchmark, a
page whose call failed counts as 0: the headline is the families' score over the graded pages, times the
share of pages graded, and it is null while any page is pending.


## Adapters

```bash
opb providers              # every provider, and the outputs it can produce
opb providers datalab      # one provider's options, their defaults and what each does
opb predict --provider datalab --page pages/<page_id>.pdf [--wants html] [--options JSON] [--raw]
```

`opb predict` sends one page through one system and prints its record as JSON (`omni_bench_core.adapter.predict`):
the outputs, the error if the page failed, what was sent, and the cost. The raw answers are left out unless
`--raw`. It exits 1 when the page failed.

```bash
```

```python
harness.ADAPTERS                       # name -> adapter class
harness.system(name, options)          # an adapter at its options, checked; a model id is the LLM adapter
```

An adapter is a `harness.PageAdapter`: a frozen dataclass whose fields are its options, with `SUPPORTS`
(the outputs it can produce), `requests(wants)`, `send(page, request, *, timeout)` and `parse(raw,
request)`. Its docstring says how to write one, and [providers.md](./providers.md) describes each. An
adapter of your own is declared by its package under the entry-point group `omni_parse_bench.adapters`,
pointing at its class.


## The dataset

```
manifest.parquet        one row per page: page_id, document, suite, doc_path, gt_path, outputs; any other
                        column is kept on the page as page.extra, unread
pages/<page_id>.pdf     the page that gets sent (or .png)
gold/<page_id>.json     its tests: {"tests": [...]}
```

Paths are relative to the dataset's folder and stay inside it. A gold file is named for its page,
`<page_id>.json`, in any folder; a page file may have any name, and pages may share one. A page whose
suite is null or empty is in the suite `"other"` (`omni_bench_core.data.NO_SUITE`), with any real suite of that name.

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
data.download_dataset(dataset)  # a local copy: an hf:// dataset downloaded whole; a folder as it is
data.read_manifest(dataset, manifest="manifest.parquet")  # (folder, pages): every page of that manifest,
                                # its file and gold as full local paths
data.select(pages, suites=None, limit=0, sample=0, only=None)   # the pages to run (omni-bench-core's)
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
to query with DuckDB, polars or pandas. To run only some pages, collect their ids into a file and pass it to
`opb run --pages`.

### Grading your own predictions

Put your system's outputs in a folder, one file per page, `predictions/<page_id>.json`, each `{"html":
..., "blocks": [...]}`, and grade it:

```bash
opb grade mine/ [--dataset ...] [--outputs html]
```

```python
benchmark.default(outputs=("html",)).grade("mine/")
```

A page with no file fails. A folder none of whose files names a page is refused. Its first grading
writes the dataset into `mine/settings.json`, so it is never graded on another dataset by mistake.


## What a run writes

A run is one provider at one setting, in its own folder under `out`, named for its provider and a digest
of its options. omni-bench-core writes it:

```
runs/datalab-f45991d3/
  settings.json                 the provider, its options, the timeout, the dataset, its commit and manifest
  records/<page_id>.json        what each page's calls returned: the outputs, the raw answers, the error, the cost
  predictions/<page_id>.json    each page's outputs alone, which is all that grading reads
  unit_tests-<digest>/          the scorer's results, one folder per set of outputs graded
    scores.jsonl                one line per page: its id, suite, document, status, tests, passed and verdicts
    summary.json                the summary, with the counts of pages graded, failed and pending
    details/<page_id>.jsonl     each test's verdict and why
```

Each page's line in `scores.jsonl` holds its verdicts without their reasons, so a question over every
run is one query. With DuckDB:

```sql
select run, avg((v.result = 'pass')::int) as score, count(*) as tests
from (select filename as run, unnest(verdicts) as v from read_json('runs/*/unit_tests-*/scores.jsonl'))
where list_contains(v.tags, 'handwriting') group by 1 order by score desc;
```

`unit_tests.summarize` gives the benchmark's own numbers on a slice: give it the test lines you select.
