# Omni Parse Bench

[![test](https://github.com/datalab-to/omni_parse_bench/actions/workflows/test.yml/badge.svg)](https://github.com/datalab-to/omni_parse_bench/actions/workflows/test.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://github.com/datalab-to/omni_parse_bench/blob/main/pyproject.toml)
[![Code: Apache 2.0](https://img.shields.io/badge/code-Apache%202.0-blue)](https://github.com/datalab-to/omni_parse_bench/blob/main/LICENSE)
[![Data: per source](https://img.shields.io/badge/data-per%20source-lightgrey)](https://github.com/datalab-to/omni_parse_bench/tree/main/licenses)
[![Dataset on Hugging Face](https://img.shields.io/badge/%F0%9F%A4%97%20dataset-omni__parse__bench-yellow)](https://huggingface.co/datasets/datalab-to/omni_parse_bench)


This repository contains a way to run our document-parsing benchmark using our dataset on [HuggingFace](https://huggingface.co/datasets/datalab-to/omni_parse_bench) or your own dataset. It also provides lower-level primitives (score and predict) to run in your own pipelines however you like. Every test is a yes/no question about one page: is this text in the output, in this order, in a table cell under these headings, etc. The README is split up into the following table of contents.



- [The design](#the-design)
- [Install](#install)
- [Run the benchmark](#run-the-benchmark)
- [Grade](#grade)
- [Score](#score)
- [Predict](#predict)
- [Documentation](#documentation)
- [License](#license)
- [Citation](#citation)

## The design

![The benchmark's design: headline, families, tests, args and tags](https://raw.githubusercontent.com/datalab-to/omni_parse_bench/main/docs/assets/design.svg)

The headline is the mean of three family scores: text, tables and layout. A family is a group of test
types:

| test type | checks | family |
|---|---|---|
| `present` | this text, number or equation appears | text |
| `order` | text A comes before text B | text |
| `repeat` | this line appears exactly N times | text |
| `table_cell` | this cell sits under these headings and beside these neighbors | tables |
| `layout_kind` | the block holding this line is a heading, text or table | layout |

A test checks one or more args, each of which is the content at one place on the page. Each arg is
tagged:

- structure: `table`, `math`, `form` and `multi_column`;
- rendering: `handwriting`, `tiny`, `rotated` and `degraded`;
- role: `heading`, `caption`, `footnote`, `list`, `code`, `figure` and `header_footer`;
- script: ISO 15924 codes (`Latn`, `Hani`, `Deva`, ...); and
- language: ISO 639-3 codes (`eng`, `fra`, `tha`, ...).

A test's tags are the union of its args' tags. Tags never decide whether a test passes or what the
headline is. It is only used to query tests and rerank. 

## Install

```bash
uv pip install omni-parse-bench                 # score and grade: no network, no API keys
uv pip install 'omni-parse-bench[harness]'      # + the systems' adapters, to predict
uv pip install 'omni-parse-bench[benchmark]'    # [harness] + the Hugging Face client, to download the dataset
```

The base install scores pages, and grades and checks a dataset folder on disk (`opb grade`, `opb check`).
Reading the published dataset (`hf://...`) needs the Hugging Face client, which `[benchmark]` brings.
`[benchmark]` includes `[harness]`, so it is the one extra to install to run the benchmark end to end.
Python 3.12 or newer.

## Run the benchmark

With `[benchmark]` installed, set the system's key, then run it on the dataset (5 pages here, spread over
the suites):

```bash
export DATALAB_API_KEY=...
opb run --system datalab --options '{"mode": "accurate"}' --out runs/ --sample 5
```

The first run downloads the whole dataset once (about 1.5 GB, 5,903 files) into the Hugging Face cache, even
for 5 pages, because grading needs it; later runs read the copy. Tip: set `HF_TOKEN` (or run
`hf auth login`) to download faster and avoid the Hub's rate limits.

`opb run` shows the plan and asks before calling any system; with no terminal to ask (a pipe, a notebook,
CI) it goes ahead without asking, so a script runs as written. It then predicts, showing a live table of
the run's progress, and grades it. The grading is JSON on stdout, and in the run's folder.

A run is one system. A run folder answers one exact question: the system, its options, the dataset, the
manifest and the pages chosen. Asking another question uses another folder; asking the same one again
resumes the same folder and pays for no page twice. So each setting of a system is its own run.

A run is one system, so to compare systems, or settings of one system, run one command per system, with
the same choice of pages (`opb run` given several systems runs nothing, and raises a `ValueError` whose
message is these commands):

```bash
export OPENROUTER_API_KEY=...
opb run --system datalab --options '{"mode": "accurate"}' --out runs/ --sample 5 -y
opb run --system openai/gpt-5.6-sol --out runs/ --sample 5 -y
```

Choosing pages:

- `--sample N`: N pages evenly spaced over the manifest; two systems run with the same N get the same pages;
- `--limit N`: the first N pages; and
- `--only FILE`: only the page ids in a file, one per line. To run one suite, list its pages (`opb tests`
  gives each test's page and suite).

`--dataset` picks the dataset: a folder, or `hf://datasets/<repo>[@revision]` (ours by default). Each
page asks a system for the outputs its tests read, limited to those the system can produce; a system that
draws no layout blocks (such as `tesseract`, `nanonets-ocr` and `olmocr`) runs the same way, and
[Grade](#grade) says how to read its results. `opb run --help` has every option and its default.

What happens when something goes wrong (a page the system refuses, a timeout, a missing key, a model
server that isn't running, a bug in an adapter, Ctrl-C) follows one rule, the same for every system:

    A page counts 0 only when code says, on purpose, that the system failed, by raising `SystemFailed`.
    Any other exception stops the run and is raised as it is.

The table in [omni-bench-core's "The rules"](https://github.com/datalab-to/omni-bench-core/blob/main/OVERVIEW.md#the-rules) says, case by case, what you see, how the
page counts, and what to do. In short:

- a failure that is the system's (`SystemFailed`, or its kinds `SystemTimeout` and `SystemUnreachable`)
  counts 0. Its record keeps the error with a `traceback`, which shows the line that decided the system
  failed;
- an answer the adapter says it can't read is recorded as `Unreadable` and counts 0, keeping the raw
  answer;
- a bug in an adapter or in the scorer stops the run with its traceback. When it is in reading an
  answer, the answer is kept, unread (`"unread": true` in its record), and running the same command again
  after the fix reads it with no call;
- a failure of the setup stops the run with nothing recorded for that page, so the same command resumes
  it. Each is a native exception: a missing key is a `ValueError`, an account that can't pay a
  `PermissionError`, and a model server that isn't running the connection error itself, with a note saying
  how to start it;
- after a fix to an adapter that read answers wrongly without raising, `opb reread RUN_DIR` reads the
  saved answers again with no call, and `opb grade RUN_DIR` grades the run again; and
- a run that stopped part way isn't graded until it is finished.

Each system's key, read from the environment (`opb systems NAME` says the same):

| system | environment variable |
| --- | --- |
| `datalab` | `DATALAB_API_KEY` |
| `reducto` | `REDUCTO_API_KEY` |
| `extend` | `EXTEND_API_KEY`, and `EXTEND_WORKSPACE_ID` when the key spans several workspaces |
| `llamaparse` | `LLAMA_CLOUD_API_KEY` |
| `azure` | `AZURE_CU_KEY`, and its resource as the `endpoint` option |
| `mistral` | `MISTRAL_API_KEY` |
| any OpenRouter model id, e.g. `openai/gpt-5.6-sol` | `OPENROUTER_API_KEY` (or `OPENAI_API_KEY`); none with another `base_url` |
| `tesseract` | none; it runs locally |
| a model you serve (`chandra-ocr`, `mineru`, `olmocr`, ...) | none; `OPB_ENDPOINT_KEY`, if set, is sent to your server as its bearer token |

A key that is missing stops the run before any call, and says which `export` to type.

In Python, the same run is:

```python
from omni_parse_bench import benchmark, harness

if __name__ == "__main__":
    b = benchmark.default()                    # the published dataset, every test graded
    b.run(harness.system("datalab", {"mode": "accurate"}), out="runs", sample=5)
```

`b.run(system, ...)` takes one system, and returns its grading, whose `run` is the run folder's name. With
the adapter class itself, it is `b.run(Datalab(mode="accurate"), out="runs", sample=5)` (`from
omni_parse_bench.harness.providers.datalab import Datalab`). To compare systems, call it once per system
with the same `sample` (or `limit`, `only`).

Every Python snippet that runs a benchmark here sits under `if __name__ == "__main__":`. A scorer or an
executor that works in several processes starts each one by importing your script again (on macOS and
Windows), and the guard keeps that import from starting the run a second time.

The loop (planning, predicting, resuming, grading) is [omni-bench-core](https://github.com/datalab-to/omni-bench-core)'s;
its [OVERVIEW](https://github.com/datalab-to/omni-bench-core/blob/main/OVERVIEW.md) explains it from the start.

## Grade

Grading compares saved answers with the tests, and calls no system. `opb run` grades its run when it
finishes; to grade again, or to grade predictions you made yourself:

```bash
opb grade runs/datalab-1a2b3c4d            # a run: graded on the pages it chose
opb grade mine/                            # your own: mine/predictions/<page_id>.json, every page
opb grade runs/datalab-1a2b3c4d --partial  # an unfinished run, its missing pages counted as 0
```

A run is graded only when it is finished: every page it chose has an answer or a recorded failure.
Otherwise `opb grade` refuses and names the pages; run the same `opb run` command again to finish them, or
grade with `--partial`, which counts them as 0 and says how many in the summary under `partial`. A folder of
your own is graded over the whole manifest, and a missing prediction is refused the same way.

Every test of a page is graded. Each run's grading is written to `<run>/unit_tests-<digest>/`:
`summary.json`, `scores.jsonl` (one line per page) and `details/<page_id>.jsonl` (one line per test). A
summary looks like this:

```json
{
  "scorer": "unit_tests",
  "options": {},
  "run": "datalab-1a2b3c4d",
  "headline": 0.648,
  "headline_is": "scored.headline × coverage",
  "rows": 5,
  "failed": 1,
  "coverage": 0.8,
  "scored": {
    "headline": 0.81,
    "headline_is": "the mean of the families' scores",
    "families": {
      "text": {"score": 0.9, "tests": 96, "documents": 4},
      "tables": {"score": 0.74, "tests": 32, "documents": 2},
      "layout": {"score": 0.79, "tests": 24, "documents": 4}
    }
  }
}
```

`coverage` is the share of pages that didn't fail. Everything under `scored` is over the pages that didn't
fail: the families, and their mean, `scored.headline`. The headline at the top is that mean times
coverage, so a page that failed counts as 0. The families are always in this order.

How to read a system that produces html only (such as `tesseract`, `nanonets-ocr` and `olmocr`): the
families map onto outputs (html: text and tables; blocks: layout). Such a system is never asked for
blocks, and a page whose tests read blocks alone is not sent to it. Its blocks tests fail as "no blocks
output", which is not a failed page, so coverage stays as it is. So its layout family is 0, and its
headline is at most two thirds. Compare it with other systems on its text and tables families, which say
how well it reads the page. Any other breakdown (by tag, test type, suite, derivation)
comes from the files: each test's verdict, with its test type, tags and derivation, is in
`details/<page_id>.jsonl`, and `opb tests` lists every test with its page and suite
([docs/API.md](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/API.md#a-slice-of-the-benchmark)).

To grade another way, write your own scorer: a frozen dataclass with `gold(row)` and `score(pred, gold)`.
[omni-bench-core's OVERVIEW](https://github.com/datalab-to/omni-bench-core/blob/main/OVERVIEW.md#scorer) shows how, and how to run it beside `UnitTests`.

## Score

Here is one page with three tests. It is written inline with `unit_tests.tests.parse` so the gold
file's shape is visible. `unit_tests` is the benchmark's scorer: it owns what a test is, and how one is
graded.

```python
from omni_parse_bench import data
from omni_parse_bench.scorers import unit_tests

tests = unit_tests.tests.parse("example-p1", {"tests": [
    {
        "id": "t1",
        "test_type": "present",
        "output_type": "html",
        "derivation": "text_layer",
        "tags": ["Latn", "eng"],
        "args": {"content": {"text": "Quarterly revenue rose 12%", "max_diffs": 1}},
        "settings": {},
    },
    {
        "id": "t2",
        "test_type": "order",
        "output_type": "html",
        "derivation": "text_layer",
        "tags": ["Latn", "eng", "heading"],
        "args": {
            "before": {"text": "Summary", "max_diffs": 0},
            "after": {"text": "Outlook", "max_diffs": 0},
        },
        "settings": {},
    },
    {
        "id": "t3",
        "test_type": "table_cell",
        "output_type": "html",
        "derivation": "publisher_markup",
        "tags": ["table"],
        "args": {
            "cell": {"text": "4.2", "max_diffs": 0},
            "top_heading": {"text": "Q3", "max_diffs": 0},
        },
        "settings": {},
    },
]})

pred = {
    "html": (
        "<h2>Summary</h2>"
        "<p>Quarterly revenue rose 12% on the year.</p>"
        "<table>"
        "<tr><th>Q2</th><th>Q3</th></tr>"
        "<tr><td>3.9</td><td>4.1</td></tr>"
        "</table>"
        "<h2>Outlook</h2>"
    ),
}
verdicts = unit_tests.score(pred, tests)
```

```python
>>> verdicts
[Verdict(id='t1', result='pass', why=''),
 Verdict(id='t2', result='pass', why=''),
 Verdict(id='t3', result='fail', why="no cell matching '4.2' in any table")]

>>> page = data.Page("example-p1", "example", "example", "pages/example-p1.pdf", "gold/example-p1.json", ("html",))
>>> lines = unit_tests.lines(verdicts, tests, page)
>>> unit_tests.summarize(lines)
{'headline': 0.5, 'families': {'text': {'score': 1.0, 'tests': 2, 'documents': 1},
                               'tables': {'score': 0.0, 'tests': 1, 'documents': 1}}}
>>> unit_tests.summarize([x for x in lines if "table" in x["tags"]])   # one tag: the same summary on a slice
{'headline': 0.0, 'families': {'tables': {'score': 0.0, 'tests': 1, 'documents': 1}}}
```

A verdict is `pass` or `fail`, with `why` saying what went wrong. A test whose output is missing fails. A test whose grading raises is a bug in our scorer: it is raised, naming the page and the test, not scored.

From the command line:

```bash
opb score --pred outputs.json --gold gold/<page_id>.json
```

It prints the verdicts. 

A score is a number over many pages: `summarize` in your code, or `summary.json` from `opb run` and
`opb grade` ([Grade](#grade)).

## Predict

With `[harness]` installed, predict with our adapters for each system:

```python
from pathlib import Path

from omni_bench_core import adapter
from omni_parse_bench import harness
from omni_parse_bench.scorers import unit_tests

system = harness.system("datalab", {"mode": "balanced"})
record = adapter.predict(system, harness.Input(Path("pages/<page_id>.pdf"), frozenset({"html", "blocks"})))
record["output"]        # {"html": "...", "blocks": [...]}
record["error"]         # why the page failed (type, status, message, traceback), or None
record["cost"]          # what it cost, its wall time and attempts

unit_tests.score(record["output"], unit_tests.tests.read("gold/<page_id>.json"))
```

From the command line:

```bash
opb predict --system openai/gpt-5.6-sol --page pages/<page_id>.pdf --outputs html   # html alone: one call
opb systems           # every system, its outputs and its key
opb systems datalab   # one system's options, and the environment it needs
```

To check a dataset, or to list its tests as JSON lines for querying: `opb check --dataset <folder>` and
`opb tests --dataset <folder> > tests.jsonl` ([docs/API.md](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/API.md#the-dataset)).

Every system gets the same time per page and its most accurate settings by default. 

## Documentation

- [`docs/API.md`](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/API.md): every function and command, the dataset, and what a run writes;
- [`docs/design.md`](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/design.md): each test type, tag and derivation, and the data layout;
- [`docs/building-tests.md`](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/building-tests.md): how the tests were built, and where each
  one's answer comes from;
- [`docs/providers.md`](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/providers.md): the adapter for each system; and
- [`docs/tagging.md`](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/tagging.md): how the tests' tags were made.

Found a test that's wrong, or a page you hold rights in? [Open an issue](https://github.com/datalab-to/omni_parse_bench/issues).

## License

The code is Apache 2.0: see [`LICENSE`](https://github.com/datalab-to/omni_parse_bench/blob/main/LICENSE), and [`NOTICE`](https://github.com/datalab-to/omni_parse_bench/blob/main/NOTICE) for the third-party
code it includes (KaTeX, MIT; a rewrite of olmOCR-bench's table parser, Apache 2.0).

The data's licenses are per source. Each source of the pages, its license and the credit it
requires are in [`licenses/`](https://github.com/datalab-to/omni_parse_bench/tree/main/licenses), one file per source. The tests are CC BY 4.0, except
those converted from olmOCR-bench (ODC-BY 1.0) and fr-bench-pdf2md (MIT), and those quoting
Wikipedia on three handwriting pages (CC BY-SA 4.0).

## Citation

```bibtex
@misc{omniparsebench2026,
  title        = {Omni Parse Bench: A Document-Parsing Benchmark},
  author       = {{Datalab}},
  year         = {2026},
  howpublished = {\url{https://github.com/datalab-to/omni_parse_bench}},
}
```

Please also cite the upstream datasets whose pages or tests this benchmark uses; they are listed
in [`licenses/`](https://github.com/datalab-to/omni_parse_bench/tree/main/licenses).
