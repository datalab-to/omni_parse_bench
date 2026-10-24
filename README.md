# Omni Parse Bench

[![test](https://github.com/datalab-to/omni_parse_bench/actions/workflows/test.yml/badge.svg)](https://github.com/datalab-to/omni_parse_bench/actions/workflows/test.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](./pyproject.toml)
[![Code: Apache 2.0](https://img.shields.io/badge/code-Apache%202.0-blue)](./LICENSE)
[![Data: per source](https://img.shields.io/badge/data-per%20source-lightgrey)](./licenses)
[![Dataset on Hugging Face](https://img.shields.io/badge/%F0%9F%A4%97%20dataset-omni__parse__bench-yellow)](https://huggingface.co/datasets/datalab-to/omni_parse_bench)


This repository contains a way to run our document-parsing benchmark using our dataset on [HuggingFace](https://huggingface.co/datasets/datalab-to/omni_parse_bench) or your own dataset. It also provides lower-level primitives (score and predict) to run in your own pipelines however you like. Every test is a yes/no question about one page: is this text in the output, in this order, in a table cell under these headings, etc. The README is split up into the following table of contents.



- [The design](#the-design)
- [Results](#results)
- [Install](#install)
- [Run the benchmark](#run-the-benchmark)
- [Score](#score)
- [Predict](#predict)
- [Documentation](#documentation)
- [License](#license)
- [Citation](#citation)

## The design

![The benchmark's design: headline, families, tests, args and tags](./docs/assets/design.svg)

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

## Results

Every system on the published dataset (revision `961c0f89`, plus Nemotron 3.5 Parse; omni-parse-bench 0.1.2 or newer).
Datalab's two rows are from a rerun of its production API on 2026-10-23. The
scores per tag (handwriting, math, tables, forms, rotated pages, ...), how parameters are counted and how
each open model is served are in [`docs/results.md`](./docs/results.md); every verdict is in the dataset's
`results.parquet` (Nemotron 3.5 Parse's and the Datalab rerun's once the dataset update that adds them is merged).

| parser | weights | parameters | headline | text | tables | layout |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| **Datalab accurate** | closed |  | 94.1 | 92.0 | 94.2 | 96.0 |
| Gemini 3.8 Flash* | closed |  | 92.9 | 91.3 | 95.2 | 92.2 |
| **Datalab balanced** | closed |  | 92.6 | 90.1 | 91.6 | 96.2 |
| Reducto | closed |  | 90.8 | 85.4 | 91.2 | 95.8 |
| LlamaParse | closed |  | 90.4 | 88.2 | 92.6 | 90.4 |
| **chandra-ocr-2** | open | 4.5B | 90.1 | 87.4 | 87.4 | 95.4 |
| Mistral OCR | closed |  | 89.5 | 82.8 | 91.9 | 93.8 |
| Claude Sonnet 5.5* | closed |  | 88.7 | 93.1 | 95.4 | 77.5 |
| dots.mocr | open | 3.0B | 87.9 | 82.5 | 88.6 | 92.5 |
| GPT-5.6 Sol | closed |  | 87.8 | 85.4 | 91.6 | 86.5 |
| MinerU2.5-Pro | open | 1.2B | 87.1 | 77.4 | 92.1 | 91.7 |
| Infinity-Parser2-Pro | open | 35.1B (MoE) | 87.0 | 83.3 | 84.1 | 93.5 |
| Extend | closed |  | 83.3 | 64.1 | 92.5 | 93.4 |
| **Surya OCR 2** | open | 0.67B | 83.1 | 80.6 | 74.3 | 94.3 |
| Azure | closed |  | 83.0 | 74.6 | 81.7 | 92.8 |
| LightOnOCR-3-4B | open | 4.5B | 82.9 | 83.9 | 70.8 | 94.0 |
| LightOnOCR-3-0.8B | open | 0.85B | 81.6 | 81.1 | 72.1 | 91.7 |
| GLM-OCR | open | 1.3B | 81.5 | 71.0 | 84.2 | 89.3 |
| Nemotron 3.5 Parse | open | 0.63B | 80.0 | 72.4 | 77.3 | 90.2 |
| Unlimited-OCR | open | 3.3B | 79.3 | 70.2 | 76.5 | 91.1 |
| PaddleOCR-VL-1.6 | open | 0.96B | 78.7 | 61.7 | 83.7 | 90.7 |
| Infinity-Parser2-Flash | open | 2.2B | 78.4 | 78.4 | 66.5 | 90.4 |
| DeepSeek-OCR-2 | open | 3.4B | 75.2 | 64.2 | 70.0 | 91.4 |
| **Indra OCR** | open | about 12M † | 69.5 | 60.3 | 58.1 | 90.1 |
| HunyuanOCR-1.5 | open | 1.0B | 64.6 | 50.5 | 61.9 | 81.4 |
| olmOCR-2 | open | 8.3B | none | 71.3 | 56.6 | unsupported |
| Nanonets-OCR2-3B | open | 3.8B | none | 68.2 | 62.6 | unsupported |
| Tesseract | open | n/a | none | 17.6 | 0.0 | unsupported |

\* Used in creating and verifying at least some tests. Datalab's own systems are in bold. † See
[`docs/results.md`](./docs/results.md).

## Install

```bash
uv pip install omni-parse-bench                 # score(): no network, no API keys
uv pip install 'omni-parse-bench[harness]'      # + vendor adapters, to predict
uv pip install 'omni-parse-bench[benchmark]'    # + dataset access, to run the benchmark
```

## Run the benchmark

With `[benchmark]` installed, run vendors on the dataset (5 pages here):

```bash
opb benchmark --out runs/ --limit 5 --providers datalab openai/gpt-5.6-sol
```

It shows the plan and asks before calling any vendor; with no terminal to ask (a pipe, a notebook, CI) it goes ahead without asking, so a script runs as written. A run is resumable. Each setting of a provider is its own run. For example here we have two:

```bash
opb benchmark --out runs/ --limit 5 --providers datalab \
  --options '{"datalab": [{"mode": "balanced"}, {"mode": "accurate"}]}'
```

`--dataset` picks the dataset: a folder, or `hf://datasets/<repo>[@revision]` (ours by default).
`--suites`, `--sample` and `--pages` choose pages. [`docs/API.md`](./docs/API.md#benchmark) has
every option.

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
>>> s = unit_tests.summarize(unit_tests.lines(verdicts, tests, page))["html"]
>>> s["score"], s["per_test_type"], s["per_tag"]["table"]
(0.6666666666666666, {'present': 1.0, 'order': 1.0, 'table_cell': 0.0}, {'score': 0.0, 'tests': 1, 'pages': 1, 'documents': 1})
```

A verdict is `pass`, `fail` or `unsupported`, with `why` saying what went wrong. `unsupported` verdicts are left out of every score. A test whose grading raises is a bug in our scorer: it is raised, naming the page and the test, not scored.

From the command line:

```bash
opb score --pred outputs.json --gold gold/<page_id>.json
```

It prints the verdicts. 

A score is a number over many pages: `summarize` in your code, or
`summary.json` from `opb benchmark`. 

To grade predictions you brought on the benchmark see [Grading your own predictions](./docs/API.md#grading-your-own-predictions).

## Predict

With `[harness]` installed, predict with our provider adapters:

```python
from omni_parse_bench import harness
from omni_parse_bench.scorers import unit_tests

record = harness.predict("datalab", "pages/<page_id>.pdf", {"html", "blocks"}, mode="balanced")
record["outputs"]       # {"html": "...", "blocks": [...]}
record["errors"]        # {output: why} for anything that failed
record["calls"]         # what was sent, cost, wall time

unit_tests.score(record["outputs"], unit_tests.tests.read("gold/<page_id>.json"))
```

From the command line:

```bash
opb predict --provider openai/gpt-5.6-sol --page pages/<page_id>.pdf --wants html
opb providers        # every provider, and its options
```

Every provider gets the same timeout per call and its most accurate settings by default. 

## Documentation

- [`docs/API.md`](./docs/API.md): every function and command, the dataset, and what a run writes;
- [`docs/design.md`](./docs/design.md): each test type, tag and derivation, and the data layout;
- [`docs/results.md`](./docs/results.md): every system's scores, by family and by tag;
- [`docs/building-tests.md`](./docs/building-tests.md): how the tests were built, and where each
  one's answer comes from;
- [`docs/providers.md`](./docs/providers.md): the provider adapters; and
- [`docs/tagging.md`](./docs/tagging.md): how the tests' tags were made.

Found a test that's wrong, or a page you hold rights in? [Open an issue](https://github.com/datalab-to/omni_parse_bench/issues).

## License

The code is Apache 2.0: see [`LICENSE`](./LICENSE), and [`NOTICE`](./NOTICE) for the third-party
code it includes (KaTeX, MIT; a rewrite of olmOCR-bench's table parser, Apache 2.0).

The data's licenses are per source. Each source of the pages, its license and the credit it
requires are in [`licenses/`](./licenses), one file per source. The tests are CC BY 4.0, except
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
in [`licenses/`](./licenses).
