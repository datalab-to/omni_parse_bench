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

```python
from omni_parse_bench import gold, score, summarize

score(
  outputs,            # one page's outputs: {"html": str, "blocks": [...]}, an output None if it errored
  tests,              # the page's tests: gold.read("gold/<page_id>.json")
  unsupported=(),     # output types the provider can't produce, e.g. {"blocks"}
)                     # -> [Verdict(id, result, why), ...], one per test

summarize(
  verdicts,           # verdicts from any number of pages
  tests,              # the tests they grade, looked up by id: the dataset's tests will do
  pages=None,         # the pages, as gold.load gives them: adds per_suite and document counts
)                     # -> a dict of scores
```

The inputs:

- `outputs["html"]` is the page as HTML, the format every test but layout reads. Markdown is
  converted to HTML by the adapters, so a provider's own format never reaches the scorer;
- `outputs["blocks"]` is the page's layout: a list of `{"label", "bbox", "text"}`. `label` is one
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
  "headline": {"score": 0.905, "documents": 2343,
               "families": {"text": {"score": 0.871, "tests": 8515, "documents": 1791}, ...}},
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
- `documents`, given `pages`, is how many source documents a score's tests are from. A document's
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
`opb score ... | jq 'map(select(.result == "fail"))'` lists a page's failures. `--pred` is `outputs`,
`--gold` is the page's gold file and `--unsupported` is `unsupported`. A score over many pages comes
from `summarize`, or from `summary.json` when `opb benchmark` grades a run.

The README has a [worked example](../README.md#score), and [`design.md`](./design.md) says how each
test type is graded.


## predict

Needs the harness extra.

```bash
uv pip install 'omni-parse-bench[harness] @ git+https://github.com/datalab-to/omni_parse_bench'
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
score(record["outputs"], gold.read("gold/<page_id>.json"))
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
uv pip install 'omni-parse-bench[benchmark] @ git+https://github.com/datalab-to/omni_parse_bench'
```

Running this costs money, and needs your API keys set.

```python
from omni_parse_bench import benchmark

p = benchmark.plan(
  providers,              # e.g. ["datalab", "openai/gpt-5.6-sol"]
  out="runs",             # where run directories go, a str or a Path
  dataset=benchmark.DEFAULT_DATASET,   # a dataset folder, or hf://datasets/<repo>[@revision]
  suites=None,            # limit to these suites
  limit=0,                # first N pages
  sample=0,               # N pages spread over every suite, for a smoke test
  only=None,              # a set of page ids: run only these
  options=None,           # per provider: {"datalab": {"mode": "accurate"}}, or a list of dicts
  timeout=0,              # seconds per vendor call; 0: the default, 900
  workers=0,              # calls at once per adapter, shared by its runs; 0: `benchmark.WORKERS`
  rescore=False,          # grade every page again
  score_only=False,       # grade what's recorded; call no vendor
  retry_failed=False,     # predict again outputs whose failure may not recur
)
print(benchmark.describe(p))          # the plan, with no vendor call
summaries = benchmark.execute(p)      # predict, then grade
summaries["datalab-f45991d3"]["headline"]["score"]   # e.g. 0.905
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
without it. It prints each run's scores with `pages` (graded) and `pages_pending` (no record yet)
beside them. It exits 2, with a warning, when a test's grading failed in our code (`errors` in a
summary's output type), since those tests are left out of the score.

### At once

Concurrency is per adapter, not per run: every run of one adapter shares one pool, since a vendor's
rate limit is per account. Two datalab modes share datalab's pool, and every OpenRouter model id
shares the llm adapter's. Each adapter's pool size is in `benchmark.WORKERS` (datalab 10, extend,
mistral and llm 5, reducto, llamaparse and azure 3, tesseract the CPU count up to 8, others 5);
`--workers N` sets N for every adapter. When one run hits an account failure or a missing key,
every run of its adapter stops at once; other adapters go on, the run is graded, and the failure is
then raised.

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
  first. From Hugging Face only the manifest and the gold files are fetched up front; each page
  file is fetched when it is first predicted;
- `--suites`: only these suites;
- `--limit N`: the first N pages;
- `--sample N`: N pages spread over every suite, the same ones each time; and
- `--pages FILE`: the page ids in a file, one per line. To run one tag's pages, see
  [Exploring the tests](#exploring-the-tests).

### Resuming

It's resumable, and safe to run twice.

- A page is predicted again only for the outputs its record doesn't hold; an output recorded as
  unsupported is held. The record is written last, so its presence means the prediction beside it
  is complete;
- a page whose file has changed since its record (the record's `page_sha256`) is predicted again
  whole; a record from before page digests is trusted;
- a record that isn't readable JSON counts as not predicted, and is logged;
- a page is graded again when its lines in `scores.jsonl` are missing, unreadable or out of date: its
  record, the gold or the scorer version differs, or the page's test ids have changed;
- grading covers every page the run has a record for, so `--limit` and `--suites` narrow what is
  predicted, never what is scored; and
- scores are written however grading ends, so an interrupt keeps what was graded.

A run folder holds one dataset: an invocation with another `--dataset` into it is refused. A change
of gold (a new commit of the same dataset) is allowed, regrades the run and is kept in
`settings.json`. Pages are fetched at the commit the gold was read at.

`--rescore` grades every page again. `--score-only` predicts nothing. `--retry-failed` predicts again
the outputs whose failure may not recur: a timeout, an outage, a 429 or 5xx (Cloudflare's 520 to 524
too), or a failure with no HTTP status. A 400, a vendor's failed job, or an LLM reply that was
truncated, refused or unusable is an answer, and is not retried.

An output whose answer arrived but didn't parse is fixed for free: after a parsing fix,
`opb reparse RUN_DIR` reads every record's outputs again from its saved answers, and
`opb benchmark ... --score-only --rescore` grades them.


## providers

```bash
opb providers
```
```
azure
datalab
extend
llamaparse
mistral
reducto
tesseract
openai/gpt-5.6-sol
```

The model id is an example: any OpenRouter `org/model` id works.

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
html and blocks. A provider of your own can't be plugged into `benchmark` yet; to grade your own model,
loop over `score` (see [The dataset](#the-dataset)).


## The dataset

```
manifest.parquet        one row per page: page_id, document, suite, doc_path, gt_path
pages/<page_id>.pdf     the page that gets sent (or .png)
gold/<page_id>.json     its tests: {"tests": [...]}
```

The dataset is the source of truth: a correction is an edit to a gold file, and a dropped page is
removed with its files and its manifest row. The pages' licenses are in `licenses/`.

`gold.load` reads it all, checked (it needs the benchmark extra, for parquet):

```python
from omni_parse_bench import gold, score, summarize

pages, tests = gold.load("dataset/")
pages[0]
# Page(page_id='olmo_arxiv_math-2502.15977_pg21-p1', document='olmo_arxiv_math:2502.15977',
#      suite='olmo_arxiv_math', doc_path='pages/olmo_arxiv_math-2502.15977_pg21-p1.pdf',
#      gt_path='gold/olmo_arxiv_math-2502.15977_pg21-p1.json')
tests[0]
# Test(id='2502.15977_pg21_math_003', page_id='olmo_arxiv_math-2502.15977_pg21-p1', test_type='present',
#      output_type='html', derivation='upstream_olmocr', tags=('math',),
#      params=Present(content=Latex(latex='\\theta_1 + ... + \\theta_n')))
```

Grading your own model is a loop over pages:

```python
by_page = gold.by_page(tests)
verdicts = []
for p in pages:
    outputs = my_model("dataset/" + p.doc_path, gold.wants(by_page[p.page_id]))
    verdicts += score(outputs, by_page[p.page_id])
summary = summarize(verdicts, tests, pages)
```

`gold.wants` is the set of outputs a page's tests read. `gold.read(path)` reads one gold file.

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
   headline its document count.
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
   verdicts you select:

   ```python
   import json
   from omni_parse_bench import benchmark, gold, metric

   pages, tests = gold.load(benchmark.dataset_root(benchmark.DEFAULT_DATASET))
   lines = [json.loads(x) for x in open("runs/datalab-f45991d3/scores.jsonl")]
   picked = [x for x in lines if {"handwriting", "table"} <= set(x["tags"])]
   verdicts = [metric.Verdict(x["test_id"], x["result"], x["why"]) for x in picked]
   metric.summarize(verdicts, tests, pages)["headline"]   # score, families, documents
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

What the run is, written before the first page, so an interrupted run still says what it is.

```json
{"run": "datalab-296b76d9", "provider": "datalab",
 "settings": {"mode": "balanced", "base_url": "https://www.datalab.to", "poll_interval": 2.0},
 "dataset": "hf://datasets/datalab-to/omni_parse_bench", "gold": "857550728dd99df40d2139946d99f711568ed529",
 "timeout_s": 900}
```

- `settings` is the whole resolved configuration, not just what you passed;
- `dataset` is the dataset's repo, or a folder's path: a later invocation with another is refused;
- `gold` is the gold last graded against, and `golds`, once it has changed, every one in order; and
- `timeout_s` is the latest invocation's; each call in a record keeps its own.

### summary.json

The `summarize` output over every graded page (see [score](#score)), plus what the run covered
and cost:

```json
{"headline": {"...": "..."}, "html": {"...": "..."}, "blocks": {"...": "..."},
 "per_suite": {"...": "..."}, "per_derivation": {"...": "..."},
 "gold": "857550728dd99df40d2139946d99f711568ed529",
 "scorer": "0.0.1+a09ce5ecf32a", "pages": 2937, "pages_pending": 0, "usd": 13.668,
 "credits": 0}
```

- `gold` is the gold it was graded against: the Hugging Face commit, or a digest of a folder's
  manifest and gold files;
- `scorer` is the package version and a digest of its scoring code, which graded it;
- `pages` is how many pages were graded, and `pages_pending` how many of the dataset's pages have
  no record yet; and
- `usd` and `credits` are what the vendor said the calls cost.

### records/&lt;page_id&gt;.json

Everything about one page's prediction: the record `predict` returns (outputs, errors, calls, raw
answers, settings), with the time it was captured, and `page_sha256`, the digest of the page file it
read. Each call keeps its timeout (`timeout_s`) and its failure (`class`, `status`, `transient`),
which `--retry-failed` reads. The raw answers are what `opb reparse` reads.

### predictions/&lt;page_id&gt;.json

The outputs alone, `{"html": ..., "blocks": ...}`: what `score` reads, and the same thing as
`record["outputs"]`.

### scores.jsonl

One line per test, in manifest order: its verdict, what the test is, and the stamps of what graded it.

```json
{"run": "datalab-f45991d3", "provider": "datalab", "page_id": "olmo_arxiv_math-2502.15977_pg21-p1",
 "suite": "olmo_arxiv_math", "document": "olmo_arxiv_math:2502.15977",
 "test_id": "2502.15977_pg21_math_003", "test_type": "present", "output_type": "html",
 "derivation": "upstream_olmocr", "tags": ["math"], "result": "pass", "why": "",
 "record": "5f0c...", "gold": "857550728dd99df40d2139946d99f711568ed529", "scorer": "0.0.1+a09ce5ecf32a"}
```

- `run` and `provider` name the run (its folder) and its provider; `settings.json` has the rest;
- `page_id` to `tags` say what the test is (`opb tests` writes the same, its id as `id`);
- `result` is `pass`, `fail`, `unsupported` or `error`, and `why` says what went wrong; and
- `record`, `gold` and `scorer` stamp what was graded and by what: a line whose stamps are out of
  date is graded again on the next `opb benchmark`.
