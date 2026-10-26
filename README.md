# Omni Parse Bench

[![test](https://github.com/datalab-to/omni_parse_bench/actions/workflows/test.yml/badge.svg)](https://github.com/datalab-to/omni_parse_bench/actions/workflows/test.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://github.com/datalab-to/omni_parse_bench/blob/main/pyproject.toml)
[![Code: Apache 2.0](https://img.shields.io/badge/code-Apache%202.0-blue)](https://github.com/datalab-to/omni_parse_bench/blob/main/LICENSE)
[![Data: per source](https://img.shields.io/badge/data-per%20source-lightgrey)](https://github.com/datalab-to/omni_parse_bench/tree/main/licenses)
[![Dataset on Hugging Face](https://img.shields.io/badge/%F0%9F%A4%97%20dataset-omni__parse__bench-yellow)](https://huggingface.co/datasets/datalab-to/omni_parse_bench)

Omni Parse Bench measures how well a system parses a document page: its text, its tables and its layout. A system
is sent a page, and returns its html and, if it can, its layout blocks. The answer is graded by unit tests: each
test is a yes/no question about the page, such as whether this text is in the output, or this cell sits under
these headings.

This repository holds:

- the scorer, which works on its own: one page's output and its tests in, a verdict per test out;
- the benchmark: our dataset on [Hugging Face](https://huggingface.co/datasets/datalab-to/omni_parse_bench), or
  your own, run through a system and graded; and
- the adapters: one per vendor, one for any model on OpenRouter, and one per open model, with a folder to serve
  it on a GPU.

Contents:

- [How scoring works](#how-scoring-works): tests, families, the headline and tags;
- [Results](#results): every system we ran on the published dataset;
- [Install](#install): the scorer alone, or with the adapters and the dataset;
- [Run the benchmark](#run-the-benchmark): one system on the dataset, from a config;
- [Grade](#grade): a run again, or predictions of your own, and how to read a summary;
- [Score one page](#score-one-page): the scorer on its own, in code or from the command line;
- [Predict one page](#predict-one-page): one page through one system;
- [Documentation](#documentation);
- [License](#license); and
- [Citation](#citation).

## How scoring works

![The benchmark's design: headline, families, tests, args and tags](https://raw.githubusercontent.com/datalab-to/omni_parse_bench/main/docs/assets/design.svg)

A test is a yes/no question about one page. There are five types of test, and each type belongs to one of three
families:

| test type | checks | family |
|---|---|---|
| `present` | this text, number or equation appears | text |
| `order` | text A comes before text B | text |
| `repeat` | this line appears exactly N times | text |
| `table_cell` | this cell sits under these headings and beside these neighbors | tables |
| `layout_kind` | the block holding this line is a heading, text or table | layout |

A family's score is the share of its tests that pass. The headline is the mean of the three family scores.

A test checks one or more args, each of which is the content at one place on the page. Each arg is tagged:

- structure: `table`, `math`, `form` and `multi_column`;
- rendering: `handwriting`, `tiny`, `rotated` and `degraded`;
- role: `heading`, `caption`, `footnote`, `list`, `code`, `figure` and `header_footer`;
- script: ISO 15924 codes (`Latn`, `Hani`, `Deva`, ...); and
- language: ISO 639-3 codes (`eng`, `fra`, `tha`, ...).

A test's tags are the union of its args' tags. Tags never decide whether a test passes, or the headline. They are
only for slicing the results, such as the score on handwriting alone.

## Results

Every system on the published dataset (revision `961c0f89`, plus Nemotron 3.5 Parse; omni-parse-bench 0.1.2 or
newer). Datalab's two rows are from a rerun of its production API on 2026-10-23. The scores per tag
(handwriting, math, tables, forms, rotated pages, ...), how parameters are counted and how each open model is
served are in [`docs/results.md`](./docs/results.md). Every verdict is in the dataset's `results.parquet`
(Nemotron 3.5 Parse's and the Datalab rerun's once the dataset update that adds them is merged).

| parser | weights | parameters | headline | text | tables | layout |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Datalab accurate | closed |  | 94.1 | 92.0 | 94.2 | 96.0 |
| Gemini 3.8 Flash * | closed |  | 92.9 | 91.3 | 95.2 | 92.2 |
| Datalab balanced | closed |  | 92.6 | 90.1 | 91.6 | 96.2 |
| Reducto | closed |  | 90.8 | 85.4 | 91.2 | 95.8 |
| LlamaParse | closed |  | 90.4 | 88.2 | 92.6 | 90.4 |
| chandra-ocr-2 (Datalab) | open | 4.5B | 90.1 | 87.4 | 87.4 | 95.4 |
| Mistral OCR | closed |  | 89.5 | 82.8 | 91.9 | 93.8 |
| Claude Sonnet 5.5 * | closed |  | 88.7 | 93.1 | 95.4 | 77.5 |
| dots.mocr | open | 3.0B | 87.9 | 82.5 | 88.6 | 92.5 |
| GPT-5.6 Sol | closed |  | 87.8 | 85.4 | 91.6 | 86.5 |
| MinerU2.5-Pro | open | 1.2B | 87.1 | 77.4 | 92.1 | 91.7 |
| Infinity-Parser2-Pro | open | 35.1B (MoE) | 87.0 | 83.3 | 84.1 | 93.5 |
| Extend | closed |  | 83.3 | 64.1 | 92.5 | 93.4 |
| Surya OCR 2 (Datalab) | open | 0.67B | 83.1 | 80.6 | 74.3 | 94.3 |
| Azure | closed |  | 83.0 | 74.6 | 81.7 | 92.8 |
| LightOnOCR-3-4B | open | 4.5B | 82.9 | 83.9 | 70.8 | 94.0 |
| LightOnOCR-3-0.8B | open | 0.85B | 81.6 | 81.1 | 72.1 | 91.7 |
| GLM-OCR | open | 1.3B | 81.5 | 71.0 | 84.2 | 89.3 |
| Nemotron 3.5 Parse | open | 0.63B | 80.0 | 72.4 | 77.3 | 90.2 |
| Unlimited-OCR | open | 3.3B | 79.3 | 70.2 | 76.5 | 91.1 |
| PaddleOCR-VL-1.6 | open | 0.96B | 78.7 | 61.7 | 83.7 | 90.7 |
| Infinity-Parser2-Flash | open | 2.2B | 78.4 | 78.4 | 66.5 | 90.4 |
| DeepSeek-OCR-2 | open | 3.4B | 75.2 | 64.2 | 70.0 | 91.4 |
| Indra OCR (Datalab) | open | about 12M † | 69.5 | 60.3 | 58.1 | 90.1 |
| HunyuanOCR-1.5 | open | 1.0B | 64.6 | 50.5 | 61.9 | 81.4 |
| olmOCR-2 | open | 8.3B | none | 71.3 | 56.6 | unsupported |
| Nanonets-OCR2-3B | open | 3.8B | none | 68.2 | 62.6 | unsupported |
| Tesseract | open | n/a | none | 17.6 | 0.0 | unsupported |

\* Used in creating and verifying at least some tests. † See [`docs/results.md`](./docs/results.md). A system with
no layout blocks has no layout score, so no headline; [Grade](#grade) says how to read it.

## Install

```bash
uv pip install omni-parse-bench                 # score and grade: no network, no API keys
uv pip install 'omni-parse-bench[harness]'      # + the systems' adapters, to predict
uv pip install 'omni-parse-bench[benchmark]'    # [harness] + the Hugging Face client, to download the dataset
```

The base install scores pages, and grades and checks a dataset folder on disk (`opb grade`, `opb check`).
Reading the published dataset (`hf://...`) needs the Hugging Face client, which `[benchmark]` brings.
`[benchmark]` includes `[harness]`, so it is the one extra to install to run the benchmark end to end. Python 3.12
or newer.

## Run the benchmark

A run is one system on one dataset. It works in three stages:

1. Plan: check the config, the system's keys and the dataset's files, before any call;
2. Predict: send each page to the system and save each answer in the run's folder; and
3. Grade: score the saved answers. Grading calls no system, so it can be done again for free.

### A config

A run is one config: a YAML file with every key written out. `opb init` writes one for a system, every option at
its default, on our dataset:

```bash
opb init datalab > datalab.yaml
```

```yaml
dataset: hf://datasets/datalab-to/omni_parse_bench
manifest: manifest.parquet
scorers:
  unit_tests: {}
rows:            # sample N evenly spaced, or limit to the first N (0 for every page), or only these ids
  sample: 0
  limit: 0
  only: null
timeout: 900.0   # seconds each page may take
workers: 0       # pages in flight at once; 0 for the system's own
system:
  datalab:
    mode: accurate
    ...
```

`--set path=value` changes one value the file has, read as YAML, and refuses a path it hasn't. This runs Datalab
on 5 pages, spread over the suites:

```bash
export DATALAB_API_KEY=...
opb run --config datalab.yaml --set rows.sample=5 --out runs/
```

`opb run` shows the plan and asks before calling any system. With no terminal to ask (a pipe, a notebook, CI), it
goes ahead without asking, so a script runs as written; `-y` skips the question at a terminal too. It then
predicts, showing a live table of the run's progress, and grades. The grading is JSON on stdout, and in the run's
folder.

Every system gets the same time per page, and its most accurate settings by default. `opb systems <name>` prints
a system's options and their defaults.

### Keys

Calling a system costs money, and each system reads its key from the environment:

| system | environment variable |
| --- | --- |
| `datalab` | `DATALAB_API_KEY` |
| `reducto` | `REDUCTO_API_KEY` |
| `extend` | `EXTEND_API_KEY`, and `EXTEND_WORKSPACE_ID` when the key spans several workspaces |
| `llamaparse` | `LLAMA_CLOUD_API_KEY` |
| `azure` | `AZURE_CU_KEY`, and its resource as the `endpoint` option |
| `mistral` | `MISTRAL_API_KEY` |
| any OpenRouter model id, such as `openai/gpt-5.6-sol` | `OPENROUTER_API_KEY` (or `OPENAI_API_KEY`); none with another `base_url` |
| `tesseract` | none; it runs locally |
| a model you serve (`chandra-ocr`, `mineru`, `olmocr`, ...) | none; `OPB_ENDPOINT_KEY`, if set, is sent to your server as its bearer token |

A missing key stops the run before any call, and says which `export` to type. `opb systems` lists every system,
its outputs and its key.

### Choosing the pages

`dataset` is a folder, or `hf://datasets/<repo>[@revision]` (ours, as `opb init` writes it). The first run
downloads the whole dataset once (about 1.5 GB, 5,903 files) into the Hugging Face cache, even for 5 pages,
because grading needs it; later runs read the copy. Set `HF_TOKEN` (or run `hf auth login`) to download faster
and avoid the Hub's rate limits. `manifest` picks which of the dataset's pages a run can ask about.

`rows` picks which of the manifest's pages this run asks about:

- `sample: N`: N pages evenly spaced over the manifest; two systems run with the same N get the same pages;
- `limit: N`: the first N pages; and
- `only: [ids]`: only these page ids. To run one suite, list its pages (`opb tests` gives each test's page and
  suite).

Each page asks a system for the outputs its tests read, limited to those the system can produce. A system that
draws no layout blocks (such as `tesseract`, `nanonets-ocr` and `olmocr`) runs the same way.

To check a dataset of your own before a run, or to list its tests as JSON lines for querying:
`opb check --dataset <folder>` and `opb tests --dataset <folder> > tests.jsonl`
([docs/API.md](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/API.md#the-dataset)).

### Comparing systems

A run is one system. To compare systems, or two settings of one system, write one config per system, with the
same `rows`, so they answer the same pages:

```bash
export OPENROUTER_API_KEY=...
opb init openai/gpt-5.6-sol > gpt.yaml
opb run --config datalab.yaml --set rows.sample=5 --out runs/ -y
opb run --config gpt.yaml --set rows.sample=5 --out runs/ -y
```

### The run folder

Each run is a folder under `--out`, named after its system and a run id: `datalab-20261021-160012-3f9a`. It holds:

- `config.yaml`: the config, every `--set` applied and every option written out, so
  `opb run --config runs/<run>/config.yaml` asks the same question again;
- `settings.json`: the question the run answers (the system and its options, the dataset, the manifest and the
  pages chosen), and when and how it was launched;
- `server.json`, for a model you serve: what its server said it serves, at each launch;
- `records/` and `predictions/`: each page's answer as the system gave it, and as it is graded; and
- `unit_tests/`: the grading.

A run folder answers one exact question. So:

- every `opb run` is a new run in a new folder, so a system redeployed since an earlier run is never mixed into it;
  and
- `--resume <a run's folder name>` continues that run, and pays for no page twice. It refuses a run of another
  question.

### Models you serve

Each open model has a folder, `omni_parse_bench/harness/providers/serve/<model>/`, that serves it on any GPU host.
Which weights answer is part of the run: the system's `served` option names the weights and their revision, and
before any call opb asks the server what it serves and refuses a run whose server serves something else.
[`docs/providers.md`](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/providers.md#serving-an-open-model)
says how to start one and point a run at it.

### When something goes wrong

One rule decides what counts as 0, the same for every system:

    A page counts 0 only when code says, on purpose, that the system failed, by raising `SystemFailed`.
    Any other exception stops the run and is raised as it is.

Case by case, what you see, how the page counts, and what to do:

- a failure that is the system's (`SystemFailed`, or its kinds `SystemTimeout` and `SystemUnreachable`) counts 0.
  Its record keeps the error with a `traceback`, which shows the line that decided the system failed;
- an answer the adapter says it can't read is recorded as `Unreadable` and counts 0, keeping the raw answer;
- a bug in an adapter or in the scorer stops the run with its traceback. When it is in reading an answer, the
  answer is kept, unread (`"unread": true` in its record), and resuming the run (`--resume`) after the fix reads
  it with no call;
- a failure of the setup stops the run with nothing recorded for that page, so resuming the run continues it. Each
  is a native exception: a missing key is a `ValueError`, an account that can't pay a `PermissionError`, and a
  model server that isn't running the connection error itself, with a note saying how to start it;
- after a fix to an adapter that read answers wrongly without raising, `opb reread RUN_DIR` reads the saved
  answers again with no call, and `opb grade RUN_DIR` grades the run again; and
- a run that stopped part way isn't graded until it is finished.

### In Python

```python
from omni_parse_bench import benchmark, harness

if __name__ == "__main__":
    b = benchmark.default()                    # the published dataset, every test graded
    b.run(harness.system("datalab", {"mode": "accurate"}), out="runs", sample=5)
```

`b.run(system, ...)` takes one system, and returns its grading, whose `run` is the run folder's name. With the
adapter class itself, it is `b.run(Datalab(mode="accurate"), out="runs", sample=5)`
(`from omni_parse_bench.harness.providers.datalab import Datalab`). To compare systems, call it once per system
with the same `sample` (or `limit`, `only`).

Every Python snippet that runs a benchmark here sits under `if __name__ == "__main__":`. A scorer or an executor
that works in several processes starts each one by importing your script again (on macOS and Windows), and the
guard keeps that import from starting the run a second time.

## Grade

Grading compares saved answers with the tests, and calls no system. `opb run` grades its run when it finishes; to
grade again, or to grade predictions you made yourself:

```bash
opb grade runs/datalab-20261021-160012-3f9a            # a run: graded on the pages it chose
opb grade mine/                                        # your own: mine/predictions/<page_id>.json, every page
opb grade runs/datalab-20261021-160012-3f9a --partial  # an unfinished run, its missing pages counted as 0
```

A run is graded only when it is finished: every page it chose has an answer or a recorded failure. Otherwise
`opb grade` refuses and names the pages. Resume the run to finish them, or grade with `--partial`, which counts
them as 0 and says how many in the summary under `partial`. A folder of your own is graded over the whole
manifest, and a missing prediction is refused the same way.

Every test of a page is graded. The grading is written to `<run>/unit_tests/`: `summary.json`, `scores.jsonl`
(one line per page) and `details/<page_id>.jsonl` (one line per test). A summary looks like this:

```json
{
  "scorer": "unit_tests",
  "options": {},
  "run": "datalab-20261021-160012-3f9a",
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

It reads in three parts:

- `coverage` is the share of pages that didn't fail;
- everything under `scored` is over the pages that didn't fail: each family's score, and their mean,
  `scored.headline`; and
- the `headline` at the top is that mean times coverage, so a page that failed counts as 0.

A system that produces html only (such as `tesseract`, `nanonets-ocr` and `olmocr`) is read differently. The
families map onto outputs: html gives text and tables, and blocks give layout. Such a system is never asked for
blocks, and a page whose tests read blocks alone is not sent to it. Its blocks tests fail as "no blocks output",
which is not a failed page, so coverage stays as it is. So its layout family is 0, and its headline is at most
two thirds. Compare it with other systems on its text and tables families, which say how well it reads the page.

Any other breakdown (by tag, test type, suite, derivation) comes from the files: each test's verdict, with its
test type, tags and derivation, is in `details/<page_id>.jsonl`, and `opb tests` lists every test with its page
and suite ([docs/API.md](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/API.md#a-slice-of-the-benchmark)).

To grade another way, write your own scorer: a frozen dataclass with `gold(row)`, `score(pred, gold)` and
`summarize(lines)`, given to the benchmark beside `UnitTests`.

## Score one page

`unit_tests` is the benchmark's scorer: it owns what a test is, and how one is graded. Here is one page with three
tests, written inline with `unit_tests.tests.parse` so the gold file's shape is visible:

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

A verdict is `pass` or `fail`, with `why` saying what went wrong. A test whose output is missing fails. A test
whose grading raises is a bug in our scorer: it is raised, naming the page and the test, not scored.

From the command line, this prints the verdicts:

```bash
opb score --pred outputs.json --gold gold/<page_id>.json
```

A score over many pages is `summarize` in your code, or `summary.json` from `opb run` and `opb grade`
([Grade](#grade)).

## Predict one page

With `[harness]` installed, `harness.system` makes a system's adapter from its name and options, and
`harness.predict` sends one page under the same rules a run uses (one time budget, retries, failures recorded) and
returns its record:

```python
from pathlib import Path

from omni_parse_bench import harness
from omni_parse_bench.scorers import unit_tests

system = harness.system("datalab", {"mode": "balanced"})
record = harness.predict(system, harness.Input(Path("pages/<page_id>.pdf"), frozenset({"html", "blocks"})))
record["output"]        # {"pages": [{"html": "...", "blocks": [...]}]}: one entry per page of the document
record["error"]         # why the page failed (type, status, message, traceback), or None
record["cost"]          # what it cost, its wall time and attempts

unit_tests.score(record["output"], unit_tests.tests.read("gold/<page_id>.json"))
```

From the command line:

```bash
opb predict --system openai/gpt-5.6-sol --page pages/<page_id>.pdf --outputs html   # html alone: one call
```

## Documentation

- [`docs/API.md`](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/API.md): every function and
  command, the dataset, and what a run writes;
- [`docs/design.md`](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/design.md): each test type, tag
  and derivation, and the data layout;
- [`docs/results.md`](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/results.md): every system's
  scores, by family and by tag;
- [`docs/building-tests.md`](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/building-tests.md): how
  the tests were built, and where each one's answer comes from;
- [`docs/providers.md`](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/providers.md): the adapter
  for each system, and how to serve each open model; and
- [`docs/tagging.md`](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/tagging.md): how the tests'
  tags were made.

Found a test that's wrong, or a page you hold rights in?
[Open an issue](https://github.com/datalab-to/omni_parse_bench/issues).

## License

The code is Apache 2.0: see [`LICENSE`](https://github.com/datalab-to/omni_parse_bench/blob/main/LICENSE), and
[`NOTICE`](https://github.com/datalab-to/omni_parse_bench/blob/main/NOTICE) for the third-party code it includes
(KaTeX, MIT; a rewrite of olmOCR-bench's table parser, Apache 2.0).

The data's licenses are per source. Each source of the pages, its license and the credit it requires are in
[`licenses/`](https://github.com/datalab-to/omni_parse_bench/tree/main/licenses), one file per source. The tests
are CC BY 4.0, except those converted from olmOCR-bench (ODC-BY 1.0) and fr-bench-pdf2md (MIT), and those quoting
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

Please also cite the upstream datasets whose pages or tests this benchmark uses; they are listed in
[`licenses/`](https://github.com/datalab-to/omni_parse_bench/tree/main/licenses).
